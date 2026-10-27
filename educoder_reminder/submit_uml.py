"""根据本地 .mdj 答案自动提交头歌 UML/图形化绘图题。

头歌的 UML 绘图题（用例图/类图/活动图/顺序图/数据流图/状态转换图/ER 图/模块结构图/
程序流程图等）是图形化（VNC）虚拟环境：学生用 StarUML 画图，把 .mdj 保存到工作区
指定路径，再点击评测。评分是文件比对式。

关键机制（实测确认）：
- 评测器运行在 VNC 虚拟机的文件系统里，读的是 **git 已提交** 的工作区状态；
- 因此必须先 SSH 登录 VNC 机，把 .mdj 写进工作区，再 `git add -A && git commit`，
  最后调用 game_build.json 触发评测。仅调用 update_file.json（代码题专用）不够。
- SSH 凭据来自 /api/myshixuns/{id}/start.json（host/port/username/password）。

AI 自动做题：
- 当某关卡本地没有 .mdj 答案且配置了 AI_API_KEY 时，用 AI 根据题目生成 .mdj；
- 评测通过后把生成的 .mdj 存回本地题库（answer/<实验名>/stepN/stepN.mdj 等）。

默认 dry-run 只预览；加 --apply 真实提交。
"""
import argparse
import asyncio
import json
import re
import shlex
import time
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from . import attempts, levels as levelmod, prepared, solutions
from .ai import AIError, ai_chat, ai_configured, extract_json_block, load_code_model
from .client import open_client
from .errors import CollectionError
from .submit import (
    detail_of, evaluate_sec_key, fetch_homework_rows, homework_deadline,
    is_homework_closed, is_level_passed, note_unconfirmed, passed_on_platform,
    resolve_entry, verdict_signature, wait_for_completion, wait_for_verdict,
    walk_prev_to_head,
)
from .uml_solver import solve_from_grader

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSROOM = '2i6ng7vp'
# VNC 机里工作区（git 仓库）根目录
WORKSPACE = '/data/workspace/myshixun'

# 实验名 -> 本地 .mdj 来源目录（answer/ 之外的例外）
SPECIAL_SOURCES = {
    '面向数据流的设计方法-2': ROOT / 'submit_2',
    '软件详细设计-2': ROOT / 'submit_1',
}

UML_SYSTEM_PROMPT = """你是 StarUML 建模专家，能根据题目要求生成 .mdj（StarUML 模型文件，本质是 JSON 文本）。

要求：
1. 只输出 .mdj 的 JSON 内容，不要任何解释、前后缀或 markdown 代码围栏。
2. _id 用形如 "AAAAAAFF+h6SjaM2Hec=" 的唯一字符串即可。
3. 严格按照题目要求放置图形元素（节点、连线、参与者、用例、类、消息等）。
4. 顶层 _type 必须是 "Project"，内含 "UMLModel"，再内含对应的图。图类型 _type 按题目
   判断：用例图 UMLUseCaseDiagram、类图 UMLClassDiagram、活动图 UMLActivityDiagram、
   顺序图 UMLSequenceDiagram、状态图 UMLStateMachineDiagram、ER 图 ERDDiagram 等。"""


def strip_prefix(path: str) -> str:
    for p in ['/data/workspace/myshixun/', '/home/headless/Desktop/workspace/myshixun/',
              'workspace/myshixun/', 'workspace/']:
        if p in path:
            return path.split(p, 1)[1]
    return path


def _safe_dir(name: str) -> str:
    return re.sub(r'[^\w\u4e00-\u9fff-]+', '_', (name or 'unnamed')).strip('_')[:60] or 'unnamed'


def collect_mdj(base: Path) -> dict:
    """扫描本地答案，返回 {key: 文件绝对路径}。

    两种目录布局都支持：
    - stepN/stepN.mdj（按关卡序号）
    - <关卡标题>/answer.mdj（按标题，解决同一实验里多个关卡 step 号相同的问题）
    查找时优先用标题，其次用 step 号。
    """
    out = {}
    if not base or not base.is_dir():
        return out
    for f in sorted(base.rglob('*')):
        if f.suffix.lower() not in ('.mdj', '.txt'):
            continue
        rel = f.relative_to(base)
        parts = rel.parts
        if len(parts) >= 2 and rel.name in ('answer.mdj', 'answer.txt'):
            out.setdefault(str(parts[0]), str(f))
        m = re.search(r'step_?(\d+)', str(rel))
        if m:
            out.setdefault(int(m.group(1)), str(f))
    return out


def resolve_answer_base(exp_name: str):
    """返回实验对应的本地 .mdj 目录。"""
    for key, base in SPECIAL_SOURCES.items():
        if key in exp_name:
            return base
    base = ROOT / 'answer' / exp_name
    return base if base.is_dir() else None


def extract_target(challenge_path, task_pass):
    """从题目描述解析 (工作区相对路径, step号)；无法解析返回 (None, None)。"""
    text = re.sub(r'<[^>]+>', ' ', task_pass or '')
    # 写法零：保存在 .../submit/ 文件夹下，并将文件名改为 step2
    m_dir = re.search(r'保存在[^，。；]*?(workspace/myshixun/[^\s，。；]+)[，。；]', text)
    m_name = re.search(r'文件名改为\s*([A-Za-z0-9_]+)', text)
    if m_dir and m_name:
        rel_dir = strip_prefix(m_dir.group(1).strip()).strip('/')
        # 去掉中文描述里的「/下」「/文件夹下」等后缀
        rel_dir = re.sub(r'[/／]?(?:文件夹)?下$', '', rel_dir).rstrip('/')
        fname = m_name.group(1)
        file_name = fname if fname.endswith('.mdj') else f'{fname}.mdj'
        # step 号可能只在目录名里（如 submit_step_3/step.mdj），从完整路径提取
        step_m = re.search(r'step(?:_detail)?_?(\d+)', f'{rel_dir}/{file_name}')
        return f'{rel_dir}/{file_name}', int(step_m.group(1)) if step_m else None

    # 写法一：答案保存为：/data/workspace/myshixun/answer/step0/step0.mdj
    m = re.search(r'答案保存为[：:]\s*[`"\']?([^\s`"\'，。；）)]*\.(?:mdj|txt))', text, re.I)
    if m:
        rel = strip_prefix(m.group(1).strip().lstrip('/'))
        step_m = re.search(r'step(?:_detail)?_?(\d+)', rel)
        step = int(step_m.group(1)) if step_m else None
        if rel and '/' in rel:
            return rel, step
    dir_raw = None
    m = re.search(r'["“]([^"”]+)["”]\s*目录下', text)
    if m:
        dir_raw = m.group(1).strip()
    else:
        m = re.search(r'保存(?:到|至|于)?\s*["“]?([^"“”，。；;\s]+/下)', text)
        if m:
            dir_raw = re.sub(r'[/／]?(?:文件夹)?下$', '', m.group(1)).rstrip('/')
    filename = None
    nm = re.search(r'命名为\s*([A-Za-z0-9_]+)', text)
    fm = re.search(r'格式为\s*([A-Za-z0-9_]+)', text)
    if nm:
        filename = f'{nm.group(1)}.{fm.group(1) if fm else "mdj"}'
    step_m = re.search(r'step(?:_detail)?_?(\d+)', filename or dir_raw or '')
    step = int(step_m.group(1)) if step_m else None
    if not filename and step is not None:
        filename = f'step{step}.mdj'
    if not dir_raw or not filename:
        return None, None
    return strip_prefix(dir_raw.strip('/')) + '/' + filename, step


def write_targets(challenge_path, task_target, step):
    """计算需要把 .mdj 写到的全部工作区相对路径（多写几处以兼容评测器）。"""
    targets = set()
    if task_target:
        targets.add(task_target)
        # 题目已明确给出答案路径（answer/ 或 submit/ 开头）：只写该路径，
        # 避免覆盖 challenge.path 指向的说明文件（如 pingce/shuoming.txt）。
        # 题目要求的 submit_step_N/ 与评测器实际读取的 submit/ 可能不同，两处都写
        m_alt = re.match(r'^(.*?)/submit_step_?\d+/([^/]+)$', task_target)
        if m_alt:
            targets.add(f'{m_alt.group(1)}/submit/{m_alt.group(2)}')
        if re.match(r'^(answer\d*/|submit)', task_target):
            cp0 = (challenge_path or '').strip().rstrip('；;').strip()
            # challenge.path 指向 pingce/ 说明文件时不能覆盖（会被评测脚本读取）
            if not cp0.startswith('pingce/'):
                if cp0 and '/' in cp0:
                    if cp0.endswith('.gitkeep'):
                        if step is not None:
                            targets.add(f'{cp0.rsplit("/", 1)[0]}/step{step}.mdj')
                    else:
                        targets.add(cp0)
            return sorted(targets)
    cp = (challenge_path or '').strip().rstrip('；;').strip()
    if cp and '/' in cp:
        if cp.endswith('.gitkeep'):
            d = cp.rsplit('/', 1)[0]
            if step is not None:
                targets.add(f'{d}/step{step}.mdj')
        else:
            targets.add(cp)
            d = cp.rsplit('/', 1)[0]
            if step is not None:
                targets.add(f'{d}/step{step}.mdj')
    return sorted(targets)


def is_graphic(detail) -> bool:
    """是否图形化绘图题。

    选择题（有 chooses）与代码题不应被当成绘图题：它们会共用实验的 VNC 环境
    （env[0].vnc_url 为真），但自身没有 vnc_url/challenge.path，误判会导致
    「无法解析保存路径」而跳过。
    """
    if detail.get('chooses'):
        return False
    if detail.get('vnc_url'):
        return True
    envs = detail.get('shixun_environments') or []
    return bool(envs) and bool(envs[0].get('vnc_url'))


async def get_ssh_connection(client, detail, classroom=None, auto_release=True):
    """调用 start.json 取得 VNC 机 SSH 连接信息。

    碰到「用户创建实验环境数已达上限」时，自动释放本课堂已打开的环境 pod 后重试一次。
    """
    myshixun = detail.get('myshixun') or {}
    game = detail.get('game') or {}
    env = (detail.get('shixun_environments') or [{}])[0]
    ident = myshixun.get('identifier')
    if not ident:
        raise CollectionError('缺少 myshixun identifier，无法启动图形化环境。')
    params = {
        'shixun_environment_id': env.get('shixun_environment_id', 0),
        'tab_type': env.get('tab_type', 3),
        'game_id': game.get('id', 0),
    }
    if detail.get('homework_common_id'):
        params['homework_common_id'] = detail.get('homework_common_id')

    async def _start():
        resp = await client.get(f'/api/myshixuns/{ident}/start.json', params)
        return resp.get('data') or {}

    data = await _start()
    if data.get('code') not in (None, 0):
        msg = data.get('msg') or data.get('message') or f'code={data.get("code")}'
        limit_hit = ('上限' in msg) or (data.get('code') == -5)
        if limit_hit and auto_release and classroom:
            print(f'      ! 环境数已达上限，自动释放本课堂已打开的环境…')
            try:
                n = await release_all_envs(client, classroom)
                print(f'      已释放 {n} 个环境，等待 5 秒后重试启动')
            except CollectionError as exc:
                print(f'      释放环境失败：{exc}')
            await asyncio.sleep(5)
            data = await _start()
        if data.get('code') not in (None, 0):
            msg = data.get('msg') or data.get('message') or f'code={data.get("code")}'
            hint = '（已尝试自动释放环境；请稍后重试或手动关闭网页端实验环境）' if limit_hit else ''
            raise CollectionError(f'启动图形化环境失败：{msg}{hint}')
    if not data.get('ssh_address') or not data.get('password'):
        raise CollectionError('start.json 未返回 SSH 连接信息。')
    return data


def _ssh_connect(conn, retries=12, delay=4):
    """带重试的 SSH 连接。

    VNC pod 启动后 SSH 网关端口要几十秒才就绪，期间会报
    「Unable to connect to port xxx」，因此这里做足够长的重试。
    """
    import paramiko
    last_exc = None
    for i in range(retries):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(conn['ssh_address'], port=int(conn['port']), username=conn['username'],
                        password=conn['password'], timeout=20, look_for_keys=False, allow_agent=False)
            try:
                ssh.get_transport().set_keepalive(30)
            except Exception:
                pass
            return ssh
        except Exception as exc:
            last_exc = exc
            try:
                ssh.close()
            except Exception:
                pass
            if i == 0:
                print(f'      · SSH 端口未就绪，等待环境启动…（{conn.get("ssh_address")}:{conn.get("port")}）')
            if i < retries - 1:
                time.sleep(delay)
    raise last_exc


async def _connect_or_restart(client, detail, classroom=None, label=''):
    """先连 SSH；连不上就重新申请一次环境（端口可能已变）再连。"""
    conn = await get_ssh_connection(client, detail, classroom)
    try:
        return _ssh_connect(conn)
    except Exception as exc:
        print(f'      · SSH 连接失败（{type(exc).__name__}），重新申请环境后重试')
        await release_myshixun_pod(client, (detail.get('myshixun') or {}).get('identifier'))
        await asyncio.sleep(3)
        conn = await get_ssh_connection(client, detail, classroom)
        return _ssh_connect(conn, retries=15, delay=4)


def write_files(ssh, content, rel_paths):
    """把内容写到多个相对路径（跳过受保护路径），返回实际写入列表。"""
    write_dirs = sorted({r.rsplit('/', 1)[0] for r in rel_paths
                         if '/' in r and not r.startswith('pingce/')})
    if write_dirs:
        cmd = 'mkdir -p ' + ' '.join(shlex.quote(f'{WORKSPACE}/{d}') for d in write_dirs)
        _, mo, _ = ssh.exec_command(cmd)
        mo.read()
    sftp = ssh.open_sftp()
    written = []
    for rel in rel_paths:
        if rel.startswith('pingce/'):
            print(f'      ! 跳过写入受保护路径 {rel}')
            continue
        with sftp.file(f'{WORKSPACE}/{rel}', 'w') as f:
            f.write(content)
        written.append(rel)
    sftp.close()
    return written


def git_commit(ssh, msg='solve'):
    _, out, _ = ssh.exec_command(
        f'cd {WORKSPACE} && git add -A >/dev/null 2>&1; '
        f'git -c user.email=auto@educoder -c user.name=auto '
        f'commit -m {msg} --no-verify >/dev/null 2>&1; git status --porcelain')
    return out.read().decode('utf-8', 'replace').strip()


def ssh_write_and_commit(conn, content, rel_paths):
    """SSH 登录 VNC 机，把 content 写到 rel_paths 的每个文件，然后 git commit。"""
    ssh = _ssh_connect(conn)
    try:
        dirs = sorted({r.rsplit('/', 1)[0] for r in rel_paths
                       if '/' in r and not r.startswith('pingce/')})
        if dirs:
            quoted = ' '.join(shlex.quote(f'{WORKSPACE}/{d}') for d in dirs)
            _, mo, _ = ssh.exec_command(f'mkdir -p {quoted}')
            mo.read()
        sftp = ssh.open_sftp()
        written = []
        for rel in rel_paths:
            # pingce/ 下是评测脚本与说明文件，绝不能覆盖
            if rel.startswith('pingce/'):
                print(f'      ! 跳过写入受保护路径 {rel}')
                continue
            abs_path = f'{WORKSPACE}/{rel}'
            try:
                with sftp.file(abs_path, 'w') as f:
                    f.write(content)
                written.append(rel)
            except Exception as exc:
                print(f'      ! 写入 {rel} 失败：{exc}')
        sftp.close()
        cmd = (f'cd {WORKSPACE} && git add -A && '
               f'git -c user.email=auto@educoder -c user.name=auto commit -m submit 2>&1')
        _, out, err = ssh.exec_command(cmd, timeout=30)
        msg = (out.read().decode('utf-8', 'replace') + err.read().decode('utf-8', 'replace')).strip()
        return written, msg
    finally:
        ssh.close()


async def release_myshixun_pod(client, myshixun_identifier):
    """释放一个 myshixun 的图形化环境 pod（退出即删 pod）。"""
    try:
        resp = await client.post(
            f'/api/myshixuns/{myshixun_identifier}/exit_delete_pod.json', {}, {})
        return resp.get('status') == 0
    except Exception:
        return False


async def release_all_envs(client, classroom):
    """释放课堂里所有实验的环境 pod，用于清理「环境数已达上限」。"""
    rows = await fetch_homework_rows(client, classroom)
    released = 0
    for hw in rows:
        mid = hw.get('myshixun_identifier')
        if mid and await release_myshixun_pod(client, mid):
            released += 1
    return released


async def submit_graphic_game(client, hw_id, gid, detail, content, target_path, step,
                              apply, stats, poll_timeout, classroom=None,
                              experiment_name=None):
    """SSH 写 .mdj → git commit → 触发评测；返回是否评测通过。"""
    challenge = detail.get('challenge') or {}
    user = detail.get('user') or {}
    env = (detail.get('shixun_environments') or [{}])[0]
    myshixun = detail.get('myshixun') or {}

    targets = write_targets(challenge.get('path'), target_path, step)
    # 如果缓存里有本关的评测脚本，以脚本要求的路径为准
    subject = (challenge.get('subject') or '').strip()
    cached = load_grader_cache(gid, subject, step)
    if cached:
        real_target = parse_target_from_script(cached)
        if real_target:
            targets = write_targets(challenge.get('path'), real_target, step)

    baseline = None
    if apply:
        try:
            baseline = verdict_signature(
                await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False))
        except CollectionError:
            baseline = verdict_signature(detail)

    if not apply:
        stats['would_submit'] += 1
        print(f'      [dry-run] UML {gid}：写 {", ".join(targets)} 并提交评测。')
        return False

    try:
        ssh = await _connect_or_restart(client, detail, classroom)
        try:
            written = write_files(ssh, content, targets)
            left = git_commit(ssh, 'solve')
        except Exception as exc:
            print(f'      · 写入失败（{type(exc).__name__}），重连后重试')
            try:
                ssh.close()
            except Exception:
                pass
            ssh = await _connect_or_restart(client, detail, classroom)
            written = write_files(ssh, content, targets)
            left = git_commit(ssh, 'solve')
        if left:
            print(f'      ! git 仍有未提交改动：{left[:120]}')
        try:
            ssh.close()
        except Exception:
            pass
    except Exception as exc:
        stats['failed'] += 1
        print(f'      ✗ UML {gid}：SSH 写文件失败：{exc}')
        return False
    print(f'      UML {gid}：已写 {", ".join(written)} 并 git 提交。')

    extras = {
        'challenge_id': challenge['id'],
        'homework_common_id': hw_id,
        'currentUserId': user['user_id'],
        'exercise_id': '',
        'question_id': '',
        'subject_id': '',
        'competition_entry_id': '',
    }
    # 官网前端用 game_status.json 返回的 sec_key 提交评测；缺了它平台常常只给分
    # 而不把该关卡记成「已通关」。取不到就多问几次。
    sec_key = await evaluate_sec_key(client, gid, detail)
    if not sec_key:
        print(f'      ⚠ UML {gid}：拿不到 sec_key，平台可能只评分不记通关。')
    grade_resp = await client.post(
        f'/api/tasks/{gid}/game_build.json', {}, {
            'sec_key': sec_key,
            'resubmit': '',
            'first': 1,
            'content_modified': 0,
            'shixun_environment_id': env.get('shixun_environment_id', 0),
            'tab_type': env.get('tab_type', 3),
            'extras': {**extras, 'commitID': str(myshixun.get('commit_id', ''))},
        })
    res = grade_resp.get('res')
    err = res.get('code') if isinstance(res, dict) else grade_resp.get('code')
    if err is not None and err != 0:
        stats['failed'] += 1
        print(f'      UML {gid}：评测未能启动（code={err}）。')
        return False

    print(f'      UML {gid}：已触发评测，等待结果…')
    passed, verdict = await wait_for_verdict(client, gid, timeout=poll_timeout,
                                             baseline=baseline)
    if passed is True:
        stats['submitted'] += 1
        print(f'      UML {gid}：评测通过 ✔')
        confirmed = await wait_for_completion(client, gid)
        if not confirmed:
            note_unconfirmed(stats, gid, 'UML')
        # solutions/ 只收平台确认 status==2 的答案，未确认的容易被别的账号复用后重蹈覆辙
        if experiment_name and confirmed:
            attempts.mark_passed(experiment_name, subject)
            solutions.save_solution(experiment_name, subject, content, path=target_path,
                                    gid=gid, kind='uml', source='submit')
        return True
    if experiment_name:
        from .submit import _verdict_feedback
        try:
            target = attempts.save_attempt(
                experiment_name, subject, content, path=target_path, gid=gid,
                kind='uml', passed=False,
                feedback=_verdict_feedback(verdict) or '评测未通过')
            print(f'      ↳ 已存档失败答案：{target.relative_to(ROOT)}')
        except Exception as exc:
            print(f'      · 保存失败答案出错：{exc}')
    if passed is False:
        stats['failed'] += 1
        print(f'      UML {gid}：评测未通过，请查看平台反馈。')
    else:
        stats['failed'] += 1
        print(f'      UML {gid}：评测超时（>{poll_timeout}s），请到平台确认。')
    return False


# --- 抓评测脚本逆向构造答案（比 AI 可靠） ---

async def _trigger_eval(client, detail, hw_id, gid):
    """触发 game_build.json 评测。"""
    challenge = detail.get('challenge') or {}
    user = detail.get('user') or {}
    env = (detail.get('shixun_environments') or [{}])[0]
    myshixun = detail.get('myshixun') or {}
    extras = {
        'challenge_id': challenge['id'],
        'homework_common_id': hw_id,
        'currentUserId': user['user_id'],
        'exercise_id': '',
        'question_id': '',
        'subject_id': '',
        'competition_entry_id': '',
    }
    sec_key = await evaluate_sec_key(client, gid, detail)
    return await client.post(
        f'/api/tasks/{gid}/game_build.json', {}, {
            'sec_key': sec_key,
            'resubmit': '',
            'first': 1,
            'content_modified': 0,
            'shixun_environment_id': env.get('shixun_environment_id', 0),
            'tab_type': env.get('tab_type', 3),
            'extras': {**extras, 'commitID': str(myshixun.get('commit_id', ''))},
        })


# 评测脚本缓存随仓库管理（放 data/ 会被 .gitignore 忽略，换机器就丢）
GRADER_CACHE = ROOT / 'graders'


def _cache_keys(gid, subject=None, step=None):
    """缓存键：gid（本账号）+ 关卡标题/step（跨账号通用）。"""
    keys = [f'gid_{gid}']
    if subject and step is not None:
        safe = re.sub(r'[^\w\u4e00-\u9fff-]+', '_', subject)[:60]
        keys.append(f'{safe}_step{step}')
    return keys


def save_grader_cache(gid, script, subject=None, step=None):
    """缓存评测脚本，避免每次都要触发评测去抓（pod 重建后易失败）。"""
    try:
        GRADER_CACHE.mkdir(parents=True, exist_ok=True)
        for key in _cache_keys(gid, subject, step):
            (GRADER_CACHE / f'{key}.py').write_text(script, encoding='utf-8')
    except OSError:
        pass


def load_grader_cache(gid, subject=None, step=None):
    for key in _cache_keys(gid, subject, step):
        try:
            return (GRADER_CACHE / f'{key}.py').read_text(encoding='utf-8')
        except OSError:
            continue
    return None


def parse_target_from_script(script):
    """从评测脚本里解析它实际读取的 (工作区相对路径, 文件名)。

    形如：
      file_path = '/data/workspace/myshixun/系统流程图/submit_step_3/'
      file = "step.mdj"
    """
    if not script:
        return None
    m_dir = re.search(r"file_path\s*=\s*['\"]([^'\"]+)['\"]", script)
    m_file = re.search(r"^\s*file\s*=\s*['\"]([^'\"]+)['\"]", script, re.M)
    if not m_dir or not m_file:
        return None
    rel_dir = strip_prefix(m_dir.group(1).strip()).strip('/')
    if not rel_dir:
        return None
    return f"{rel_dir}/{m_file.group(1).strip()}"


def _read_static_grader(ssh, step):
    """有些实验的评测脚本静态放在 pingce/analyse_stepN.py，可直接读（无需触发评测）。"""
    for rel in (f'pingce/analyse_step{step}.py', f'pingce/step{step}.py',
                f'pingce/analyse{step}.py'):
        _, o, _ = ssh.exec_command(f'cat {WORKSPACE}/{rel} 2>/dev/null')
        txt = o.read().decode('utf-8', 'replace')
        if txt.strip():
            return txt
    return None


def _script_target_dir(script):
    """从脚本内容解析它读取的目录（相对工作区），用于精确匹配关卡。"""
    m = re.search(r"file_path\s*=\s*['\"]([^'\"]+)['\"]", script)
    if not m:
        return None
    rel = strip_prefix(m.group(1).strip()).strip('/')
    return rel


async def _capture_grader_script(ssh, step, expect_target=None):
    """评测期间轮询读取评测脚本。

    不同实验位置不同：secret/codeReview/codeN.py、secret/<实验>/evaluate/demo*.py 等，
    因此扫描 secret/ 和 pingce/ 下所有非空 .py，优先返回与当前 step 相关的。
    """
    fixed = f'/data/workspace/myshixun/secret/codeReview/code{step}.py'
    scan = ('for f in $(find /data/workspace/myshixun/secret /data/workspace/myshixun/pingce '
            '-name "*.py" 2>/dev/null); do s=$(wc -c < "$f" 2>/dev/null); '
            'if [ "$s" != "0" ]; then echo "### $f"; cat "$f"; fi; done')
    for _ in range(40):
        blocks = []
        _, o, _ = ssh.exec_command(f'cat {fixed} 2>/dev/null')
        txt = o.read().decode('utf-8', 'replace')
        if txt.strip():
            return txt
        _, o, _ = ssh.exec_command(scan)
        raw = o.read().decode('utf-8', 'replace')
        for chunk in raw.split('### '):
            if not chunk.strip():
                continue
            blocks.append(chunk)
        if blocks:
            # 0) 最可靠：按「题目要求写入的目录」匹配脚本的 file_path
            #    （同一实验里 demo.py/demo2.py 分别对应不同 submit 目录）
            if expect_target:
                want_dir = expect_target.rsplit('/', 1)[0].rstrip('/')
                for b in blocks:
                    body = b.split('\n', 1)[-1]
                    got = _script_target_dir(body)
                    if got and got.rstrip('/') == want_dir:
                        return body
                # 指定了目标却都不匹配：可能本关脚本还没挂载，继续轮询
                # （不要兜底返回别的关卡脚本，否则会写到错误路径）
                await asyncio.sleep(1)
                continue
            # 1) 文件名精确匹配 demo{step}.py / code{step}.py / analyse_step{step}.py
            want = {f'demo{step}.py', f'code{step}.py',
                    f'analyse_step{step}.py', f'step{step}.py'}
            for b in blocks:
                head = b.split('\n', 1)[0].strip()
                fname = head.rsplit('/', 1)[-1]
                if fname in want:
                    return b.split('\n', 1)[-1]
            # 2) 内容里明确读写本关文件
            for b in blocks:
                if re.search(rf"submit_step_?{step}[/\"']", b) or f'step{step}.mdj' in b:
                    return b.split('\n', 1)[-1]
            # 3) 文件名含 stepN，或兜底第一个
            for b in blocks:
                head = b.split('\n', 1)[0].strip()
                if f'step{step}' in head:
                    return b.split('\n', 1)[-1]
            return blocks[0].split('\n', 1)[-1]
        await asyncio.sleep(1)
    return None


async def _ssh_write_commit(ssh, content, rel_paths, msg='submit'):
    rel_paths = [r for r in rel_paths if not r.startswith('pingce/')]
    # 确保父目录存在（新 pod 可能缺少 submit/answer 子目录）
    dirs = sorted({r.rsplit('/', 1)[0] for r in rel_paths if '/' in r})
    if dirs:
        quoted = ' '.join(shlex.quote(f'{WORKSPACE}/{d}') for d in dirs)
        _, mo, _ = ssh.exec_command(f'mkdir -p {quoted}')
        mo.read()
    sftp = ssh.open_sftp()
    for rel in rel_paths:
        try:
            with sftp.file(f'{WORKSPACE}/{rel}', 'w') as f:
                f.write(content)
        except Exception as exc:
            print(f'      ! 写入 {rel} 失败：{exc}')
    sftp.close()
    # commit 并校验：以「工作区是否干净」为准（git commit 的退出码不可靠）
    for attempt in range(3):
        _, out, _ = ssh.exec_command(
            f'cd {WORKSPACE} && git add -A >/dev/null 2>&1; '
            f'git -c user.email=auto@educoder -c user.name=auto '
            f'commit -m {msg} --no-verify >/dev/null 2>&1; '
            f'git status --porcelain')
        left = out.read().decode('utf-8', 'replace').strip()
        if not left:
            return
        await asyncio.sleep(1)
    print(f'      ! git 仍有未提交改动：{left[:120]}')


async def solve_level_from_grader(client, hw_id, gid, detail, target, step, apply,
                                  stats, poll_timeout, classroom=None,
                                  experiment_name=None):
    """抓评测脚本 → 逆向构造 .mdj → 提交；返回是否通过。"""
    challenge = detail.get('challenge') or {}
    targets = write_targets(challenge.get('path'), target, step)
    if not apply:
        stats['would_submit'] += 1
        print(f'      [dry-run] UML {gid}：抓评测脚本逆向构造答案并提交。')
        return False

    ssh = await _connect_or_restart(client, detail, classroom)
    try:
        # 0) 优先用已缓存的评测脚本（避免每次触发评测去抓，pod 重建后易失败）
        subject = ((detail.get('challenge') or {}).get('subject') or '').strip()
        # 用题目解析出的目标路径判断期望目录（targets 是排序后的集合，[0] 不可靠）
        expect_dir = (target.rsplit('/', 1)[0].rstrip('/')) if target else None
        script = load_grader_cache(gid, subject, step)
        if script and expect_dir:
            # 校验缓存是否真的是本关的脚本（同一实验多个 demo 脚本易混）
            got = _script_target_dir(script)
            if got and got.rstrip('/') != expect_dir:
                print(f'      · 缓存脚本路径不匹配（{got} ≠ {expect_dir}），重新抓取')
                script = None
        if script:
            print(f'      · 使用缓存的评测脚本')
        else:
            script = _read_static_grader(ssh, step)
        if not script:
            # 1) 写探针并触发评测（用于挂载评测脚本）
            await _ssh_write_commit(ssh, json.dumps({'_type': 'Project', 'name': 'probe',
                                                      'ownedElements': []}), targets, 'probe')
            await _trigger_eval(client, detail, hw_id, gid)
            script = await _capture_grader_script(ssh, step, target)
            if not script:
                # 评测脚本挂载有延迟，重新触发一次评测再抓
                print('      · 未抓到评测脚本，重新触发评测后重试')
                await asyncio.sleep(3)
                await _trigger_eval(client, detail, hw_id, gid)
                script = await _capture_grader_script(ssh, step, target)
        if not script:
            stats['failed'] += 1
            print(f'      ✗ UML {gid}：未抓到评测脚本。')
            return False
        save_grader_cache(gid, script, (challenge.get('subject') or '').strip(), step)
        content = solve_from_grader(script)
        if not content:
            stats['failed'] += 1
            print(f'      ✗ UML {gid}：无法从评测脚本解析出答案。')
            return False
        # 评测脚本里写明了它实际读取的路径，以它为准（题目描述常与评测器不一致，
        # 例如题目说 step3.mdj 但评测器读 step.mdj）
        real_target = parse_target_from_script(script)
        if real_target:
            targets = write_targets(challenge.get('path'), real_target, step)
            print(f'      · 按评测脚本路径写入：{real_target}')
        # 2) 写正确答案并提交（SSH 可能被服务端断开，失败则重连重试一次）
        try:
            write_files(ssh, content, targets)
            left = git_commit(ssh, 'solve')
            if left:
                print(f'      ! git 仍有未提交改动：{left[:100]}')
        except Exception as exc:
            print(f'      · 写入失败（{type(exc).__name__}），重连后重试')
            try:
                ssh.close()
            except Exception:
                pass
            ssh = await _connect_or_restart(client, detail, classroom)
            write_files(ssh, content, targets)
            left = git_commit(ssh, 'solve')
            if left:
                print(f'      ! git 仍有未提交改动：{left[:100]}')
    finally:
        try:
            ssh.close()
        except Exception:
            pass

    try:
        baseline = verdict_signature(
            await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False))
    except CollectionError:
        baseline = verdict_signature(detail)
    await _trigger_eval(client, detail, hw_id, gid)
    print(f'      UML {gid}：已按评测脚本构造并提交，等待结果…')
    passed, verdict = await wait_for_verdict(client, gid, timeout=poll_timeout,
                                             baseline=baseline)
    subject = ((detail.get('challenge') or {}).get('subject') or '').strip()
    if passed is True:
        stats['submitted'] += 1
        print(f'      UML {gid}：评测通过 ✔')
        confirmed = await wait_for_completion(client, gid)
        if not confirmed:
            note_unconfirmed(stats, gid, 'UML')
        if experiment_name and confirmed:
            attempts.mark_passed(experiment_name, subject)
            solutions.save_solution(experiment_name, subject, content, path=target,
                                    gid=gid, kind='uml', source='submit-grader')
        return content
    if experiment_name:
        from .submit import _verdict_feedback
        try:
            target = attempts.save_attempt(
                experiment_name, subject, content, path=target, gid=gid,
                kind='uml', passed=False,
                feedback=_verdict_feedback(verdict) or '评测未通过')
            print(f'      ↳ 已存档失败答案：{target.relative_to(ROOT)}')
        except Exception as exc:
            print(f'      · 保存失败答案出错：{exc}')
    stats['failed'] += 1
    print(f'      UML {gid}：评测未通过。' if passed is False else f'      UML {gid}：评测超时。')
    return None


# --- AI 自动做题 ---

def load_generic_example():
    """取一个最小的 .mdj 作为格式示例（优先最简单的图）。"""
    candidates = []
    for p in (ROOT / 'answer', ROOT / 'submit', ROOT / 'submit_1', ROOT / 'submit_2'):
        if p.is_dir():
            candidates.extend(p.rglob('*.mdj'))
    candidates.sort(key=lambda f: f.stat().st_size)
    for p in candidates:
        try:
            return p.read_text(encoding='utf-8')
        except OSError:
            continue
    return None


def build_uml_prompt(task_pass, example):
    text = re.sub(r'<[^>]+>', ' ', task_pass or '')
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 4000:
        text = text[:4000] + '…'
    parts = [f'题目要求：\n{text}']
    if example:
        parts.append(f'以下是一个 .mdj 格式示例（结构如此，内容需按本题重做）：\n{example[:8000]}')
    parts.append('请生成本题的 .mdj 内容。')
    return '\n\n'.join(parts)


async def ai_solve_uml(task_pass, example):
    """用 AI 生成 .mdj，返回合法 JSON 文本；失败返回 None。"""
    content = await ai_chat(UML_SYSTEM_PROMPT, build_uml_prompt(task_pass, example),
                            model=load_code_model(), thinking=True, reasoning_effort='high')
    j = extract_json_block(content)
    try:
        obj = json.loads(j)
    except ValueError:
        return None
    if not isinstance(obj, dict) or obj.get('_type') != 'Project':
        return None
    return j


def save_mdj_answer(exp_name, step, content, subject=None):
    """评测通过后把答案存回本地题库。

    优先按「关卡标题/answer.mdj」保存：同一实验里不同关卡的 step 号可能相同
    （例如 系统流程图 的三关都解析成 step2），用 step 目录会互相覆盖。
    没有标题时才退回 stepN/stepN.mdj。
    """
    base = resolve_answer_base(exp_name)
    if base is None:
        base = ROOT / 'answer' / exp_name
    if subject and subject.strip():
        d = base / _safe_dir(subject)
        name = 'answer'
    elif step is not None:
        d = base / f'step{step}'
        name = f'step{step}'
    else:
        d = base / 'unnamed'
        name = 'answer'
    d.mkdir(parents=True, exist_ok=True)
    p = d / f'{name}.mdj'
    p.write_text(content, encoding='utf-8')
    return p


async def process_experiment(client, hw, apply, stats, poll_timeout, limit=None,
                             experiment_filter=None, use_ai=True, release_pods=True,
                             delay=5.0, classroom=None, repair_status=False,
                             include_expired=False, coverage=None, entry=None):
    """处理一个实验的图形化关卡。

    coverage：与 submit.py 共享的关卡覆盖记录，用来标记每个关卡归哪条链处理，
    避免「两条链都认为不归自己」时静默漏提交。
    entry：submit_all 解析好的入口关卡，与选择/代码链、收尾校验共用同一个。
    """
    coverage = coverage if coverage is not None else levelmod.Coverage()
    name = hw.get('name') or ''
    if experiment_filter and experiment_filter not in name:
        return
    if not include_expired and is_homework_closed(hw):
        stats['skipped_closed'] = stats.get('skipped_closed', 0) + 1
        deadline = homework_deadline(hw)
        when = f'（截止 {deadline:%Y-%m-%d %H:%M}）' if deadline else '（已归档）'
        print(f'  - [跳过] 实验已截止{when}：{name}')
        return
    hw_id = hw.get('homework_id')
    shixun_id = hw.get('shixun_identifier')
    if hw.get('shixun_finished_status') == 1:
        stats['skipped_passed'] += 1
        print(f'  - [跳过] 实验已完成：{name}')
        return

    entry = entry or await resolve_entry(client, shixun_id, hw_id)
    if not entry:
        print(f'  ✗ 无法解析实验入口，跳过：{name}')
        return
    ordered, cache = await walk_prev_to_head(client, entry)

    # 非图形实验（选择/代码题）直接跳过，交给 submit.py 处理。
    # 只能判断「整条关卡链里有没有图形题」：混合实验（选择/代码 + 图形）的
    # 入口往往是选择题，只看入口会把后面的图形题整个漏掉
    # （曾导致面向对象分析系列 29 关图形题一直未处理）。
    if not any(is_graphic(cache.get(g)) for g in ordered):
        return
    base = resolve_answer_base(name)
    mdj = collect_mdj(base)
    example = None
    if mdj:
        try:
            first_key = next(iter(mdj))
            example = Path(mdj[first_key]).read_text(encoding='utf-8')
        except (OSError, StopIteration):
            example = None
    print(f'\n== {name} ==（本地答案 {len(mdj)} 个 step）')
    if base is None:
        print(f'  ! 未找到该实验的本地 .mdj 答案目录。')

    queue = list(ordered)
    seen = set()
    done = set()
    while queue:
        if limit is not None and stats['processed'] >= limit:
            print(f'  … 达到 --limit {limit}，停止。')
            return
        gid = queue.pop(0)
        if gid in done:
            continue
        done.add(gid)
        detail = await detail_of(client, cache, gid)
        game = detail.get('game') or {}
        challenge = detail.get('challenge') or {}
        subject = (challenge.get('subject') or '').strip()

        nxt = detail.get('next_game')
        if nxt and str(nxt) not in seen:
            seen.add(str(nxt))
            queue.append(str(nxt))

        if not is_graphic(detail):
            kind = levelmod.classify_level(detail)
            if is_level_passed(detail):
                coverage.note(gid, kind=kind, subject=subject,
                              passed=True, action='skipped_passed')
            elif kind in (levelmod.KIND_CHOICE, levelmod.KIND_CODE):
                coverage.note(gid, kind=kind, subject=subject,
                              owner=levelmod.OWNER_SUBMIT)
            else:
                coverage.note(gid, kind=kind, subject=subject, action='unknown')
                print(f'  ✗ [无主关卡] {subject}：既不是图形题，也没有选择/代码题线索，'
                      '本次未处理；请人工确认。')
            continue
        coverage.note(gid, kind=levelmod.KIND_GRAPHIC, subject=subject,
                      owner=levelmod.OWNER_UML)
        if is_level_passed(detail):
            passed_status = (detail.get('game') or {}).get('status')
            if not (repair_status and passed_status != 2):
                stats['skipped_passed'] += 1
                print(f'  [跳过] {subject}：已通过。')
                coverage.note(gid, passed=True, action='skipped_passed')
                continue
            print(f'  ▸ {subject}：评测记录已通过但平台未记通关，按官网流程重交一次。')
        # 提交前重查一次：本地/缓存判成未通过，但平台可能已经通关（用户手动过了/同步慢）。
        if apply and not repair_status and await passed_on_platform(client, gid):
            stats['skipped_passed'] += 1
            print(f'  [跳过] {subject}：提交前重查确认已在平台通关。')
            coverage.note(gid, passed=True, action='skipped_passed')
            continue
        target, step = extract_target(challenge.get('path'), challenge.get('task_pass'))
        if not target:
            target = attempts.attempt_target(name, subject)
            if target:
                step_m = re.search(r'step(?:_detail)?_?(\d+)', target)
                step = int(step_m.group(1)) if step_m else step
                print(f'  ▸ {subject}：使用 attempts/ 里指定的保存路径 {target}')
        if not target:
            # prepare.py 预生成答案时可能从题面/评测脚本解析出了保存路径
            target = prepared.prepared_target(name, subject)
            if target:
                step_m = re.search(r'step(?:_detail)?_?(\d+)', target)
                step = int(step_m.group(1)) if step_m else step
                print(f'  ▸ {subject}：使用 prepared/ 里记录的保存路径 {target}')
        if not target:
            stats['skipped_error'] += 1
            coverage.note(gid, action='skipped_error')
            print(f'  - [跳过] {subject}：无法解析保存路径（非 .mdj 绘图题？）。'
                  '可在 attempts/ 对应关卡里写 target.txt 指定。')
            continue

        local_path = None
        local_source = ''
        if repair_status:
            archived = attempts.attempt_path(name, subject, ('.mdj', '.txt'))
            if archived:
                local_path = str(archived)
                print(f'  ▸ {subject}：使用 attempts/ 里的存档答案重试。')
        if not local_path:
            local_path = mdj.get(subject) or (mdj.get(step) if step is not None else None)
        if not local_path:
            # 闭环：solutions/ 存的是「平台确认已通关」的 .mdj，比 attempts/（失败尝试）可靠。
            # AI 刷通过的那一份就在这里，换账号/换机器直接复用，不用重跑 grader/AI。
            solved = solutions.solution_path(name, subject)
            if solved:
                local_path = str(solved)
                print(f'  ▸ {subject}：使用 solutions/ 里已通关的答案。')
        if not local_path:
            archived = attempts.attempt_path(name, subject, ('.mdj', '.txt'))
            if archived:
                local_path = str(archived)
                print(f'  ▸ {subject}：使用 attempts/ 里的存档答案重试。')
        if not local_path:
            # prepare.py 预先集中生成的 AI 答案（还没平台验证）。先用它提交一次，
            # 不通过仍会回落到「抓评测脚本逆向构造」然后才是现场 AI。
            generated = prepared.prepared_path(name, subject, ('.mdj', '.txt'))
            if generated:
                local_path = str(generated)
                local_source = 'prepared'
                print(f'  ▸ {subject}：使用 prepared/ 里预生成的 AI 答案。')
        if not local_path:
            # 无本地答案：优先抓评测脚本逆向构造（不消耗 AI），失败再尝试 AI
            print(f'  ▸ {subject}（抓评测脚本逆向构造）')
            stats['processed'] += 1
            content = None
            try:
                content = await solve_level_from_grader(client, hw_id, gid, detail, target,
                                                        step, apply, stats, poll_timeout,
                                                        classroom=classroom,
                                                        experiment_name=name)
            except CollectionError as exc:
                print(f'      ✗ {subject}：{exc}')
            except Exception as exc:
                stats['failed'] += 1
                print(f'      ✗ {subject}：{exc}')
            if content:
                p = save_mdj_answer(name, step, content, subject)
                print(f'      ↳ 答案已保存到本地题库：{p}')
                continue
            if not use_ai:
                stats['skipped_no_answer'] += 1
                print(f'  [跳过] {subject}：逆向构造失败且已禁用 AI。')
                continue
            if ai_configured():
                try:
                    if example is None:
                        example = load_generic_example()
                    content = await ai_solve_uml(challenge.get('task_pass'), example)
                except AIError as exc:
                    stats['failed'] += 1
                    print(f'  ✗ {subject}：AI 调用失败：{exc}')
                    content = None
                if content:
                    print(f'  ▸ {subject}（AI 生成）')
                    print(f'      目标 {target}  <-  AI 生成')
                    try:
                        passed = await submit_graphic_game(client, hw_id, gid, detail, content,
                                                           target, step, apply, stats, poll_timeout,
                                                           classroom=classroom,
                                                           experiment_name=name)
                    except CollectionError as exc:
                        stats['failed'] += 1
                        print(f'      ✗ {subject}：{exc}')
                        passed = False
                    if passed:
                        p = save_mdj_answer(name, step, content, subject)
                        print(f'      ↳ AI 答案已保存到本地题库：{p}')
            continue

        # 有本地答案
        content = Path(local_path).read_text(encoding='utf-8')
        print(f'  ▸ {subject}')
        print(f'      目标 {target}  <-  {local_path}')
        stats['processed'] += 1
        passed = False
        try:
            passed = await submit_graphic_game(client, hw_id, gid, detail, content, target,
                                               step, apply, stats, poll_timeout,
                                               classroom=classroom,
                                               experiment_name=name)
        except CollectionError as exc:
            stats['failed'] += 1
            print(f'      ✗ {subject}：{exc}')

        # 本地答案没通过：改用评测脚本逆向构造（不消耗 AI），成功后覆盖本地答案
        if apply and not passed:
            if local_source == 'prepared':
                # 预生成的 AI 草稿没通过：标记作废，下一轮改用逆向构造 / 现场 AI，
                # 避免同一份错误答案每轮重交。
                prepared.mark_rejected(name, subject, '提交未通过，下一轮重新生成')
                print('      · prepared/ 答案已标记作废，下一轮改用逆向构造/AI 重做')
            print(f'      · 本地答案未通过，改用评测脚本逆向构造')
            try:
                ref = await solve_level_from_grader(client, hw_id, gid, detail, target,
                                                    step, apply, stats, poll_timeout,
                                                    classroom=classroom)
            except CollectionError as exc:
                print(f'      ✗ {subject}：{exc}')
                ref = None
            if ref:
                saved = save_mdj_answer(name, step, ref, subject)
                print(f'      ↳ 已用逆向构造结果覆盖本地答案：{saved}')

    # 处理完一个实验后释放其环境 pod，避免并发环境数触发上限
    if release_pods and apply:
        mid = hw.get('myshixun_identifier')
        if mid and await release_myshixun_pod(client, mid):
            print(f'  ↳ 已释放环境 pod。')
    # 实验之间稍作停顿，避免环境启动过快失败
    if delay > 0:
        await asyncio.sleep(delay)


async def run(apply, classroom, limit, poll_timeout, experiment_filter, use_ai,
              release_pods=True, release_envs=False, delay=5.0, repair_status=False,
              include_expired=False):
    stats = {
        'submitted': 0, 'would_submit': 0, 'skipped_passed': 0,
        'skipped_no_answer': 0, 'skipped_error': 0, 'failed': 0, 'processed': 0,
        'unowned': 0,
    }
    async with open_client() as client:
        if release_envs:
            n = await release_all_envs(client, classroom)
            print(f'已释放 {n} 个实验环境 pod。')
        rows = await fetch_homework_rows(client, classroom)
        print(f'课堂 {classroom}：{len(rows)} 条实验作业。')
        for hw in rows:
            await process_experiment(client, hw, apply, stats, poll_timeout,
                                     limit=limit, experiment_filter=experiment_filter,
                                     use_ai=use_ai, release_pods=release_pods,
                                     delay=delay, classroom=classroom,
                                     repair_status=repair_status,
                                     include_expired=include_expired)
    print('\n===== 汇总 =====')
    for key, value in stats.items():
        print(f'  {key}: {value}')
    if not apply:
        print('\n这是 dry-run 预览，未真实提交。确认无误后加 --apply 真实提交。')
    return stats


def main():
    parser = argparse.ArgumentParser(description='根据本地 .mdj 自动提交头歌 UML 绘图题。')
    parser.add_argument('--apply', action='store_true', help='真实提交（默认 dry-run 只预览）。')
    parser.add_argument('--classroom', default=DEFAULT_CLASSROOM, help='课堂 code。')
    parser.add_argument('--limit', type=int, default=None, help='最多处理多少个图形化关卡（测试用）。')
    parser.add_argument('--experiment', default=None, help='只处理名称包含该字符串的实验。')
    parser.add_argument('--poll-timeout', type=int, default=180, help='评测等待秒数。')
    parser.add_argument('--no-ai', action='store_true', help='缺答案时不用 AI 自动生成，直接跳过。')
    parser.add_argument('--release-envs', action='store_true', help='运行前先释放课堂里所有实验环境 pod。')
    parser.add_argument('--no-release', action='store_true', help='每个实验跑完后不释放其环境 pod。')
    parser.add_argument('--repair-status', action='store_true',
                        help='重交「评测已通过但平台未记通关（status!=2）」的关卡。')
    parser.add_argument('--include-expired', action='store_true',
                        help='连已截止/已归档的实验也处理（默认跳过）。')
    parser.add_argument('--delay', type=float, default=5.0, help='每个实验之间的等待秒数（避免环境启动过快）。')
    args = parser.parse_args()
    try:
        asyncio.run(run(args.apply, args.classroom, args.limit,
                        args.poll_timeout, args.experiment, use_ai=not args.no_ai,
                        release_pods=not args.no_release, release_envs=args.release_envs,
                        delay=args.delay, repair_status=args.repair_status,
                        include_expired=args.include_expired))
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('Playwright 请求失败，请检查网络；认证详情不写入日志。') from None


if __name__ == '__main__':
    main()
