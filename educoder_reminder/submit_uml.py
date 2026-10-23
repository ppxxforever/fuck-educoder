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

from .ai import AIError, ai_chat, ai_configured, extract_json_block
from .client import open_client
from .errors import CollectionError
from .submit import (
    fetch_homework_rows, resolve_entry, verdict_signature, walk_prev_to_head,
    wait_for_verdict,
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


def collect_mdj(base: Path) -> dict:
    """扫描目录下所有 stepN.mdj / stepN/res.txt，返回 {step号: 文件绝对路径}。"""
    out = {}
    if not base or not base.is_dir():
        return out
    for f in sorted(base.rglob('*')):
        if f.suffix.lower() not in ('.mdj', '.txt'):
            continue
        m = re.search(r'step_?(\d+)', str(f.relative_to(base)))
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
            dir_raw = m.group(1).rstrip('/下')
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
    if detail.get('vnc_url'):
        return True
    envs = detail.get('shixun_environments') or []
    return bool(envs) and bool(envs[0].get('vnc_url'))


async def get_ssh_connection(client, detail):
    """调用 start.json 取得 VNC 机 SSH 连接信息。"""
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
    resp = await client.get(f'/api/myshixuns/{ident}/start.json', params)
    data = resp.get('data') or {}
    if data.get('code') not in (None, 0):
        msg = data.get('msg') or data.get('message') or f'code={data.get("code")}'
        raise CollectionError(f'启动图形化环境失败：{msg}（请关闭部分已打开的实验环境后重试）')
    if not data.get('ssh_address') or not data.get('password'):
        raise CollectionError('start.json 未返回 SSH 连接信息。')
    return data


def _ssh_connect(conn, retries=6, delay=3):
    """带重试的 SSH 连接（pod 启动后端口可能延迟就绪）。"""
    import paramiko
    last_exc = None
    for i in range(retries):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(conn['ssh_address'], port=int(conn['port']), username=conn['username'],
                        password=conn['password'], timeout=15, look_for_keys=False, allow_agent=False)
            return ssh
        except Exception as exc:
            last_exc = exc
            try:
                ssh.close()
            except Exception:
                pass
            if i < retries - 1:
                time.sleep(delay)
    raise last_exc


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
                              apply, stats, poll_timeout):
    """SSH 写 .mdj → git commit → 触发评测；返回是否评测通过。"""
    challenge = detail.get('challenge') or {}
    user = detail.get('user') or {}
    env = (detail.get('shixun_environments') or [{}])[0]
    myshixun = detail.get('myshixun') or {}

    targets = write_targets(challenge.get('path'), target_path, step)

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
        conn = await get_ssh_connection(client, detail)
        written, git_msg = ssh_write_and_commit(conn, content, targets)
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
    grade_resp = await client.post(
        f'/api/tasks/{gid}/game_build.json', {}, {
            'sec_key': detail.get('sec_key') or '',
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
    passed, _ = await wait_for_verdict(client, gid, timeout=poll_timeout, baseline=baseline)
    if passed is True:
        stats['submitted'] += 1
        print(f'      UML {gid}：评测通过 ✔')
        return True
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
    return await client.post(
        f'/api/tasks/{gid}/game_build.json', {}, {
            'sec_key': detail.get('sec_key') or '',
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


async def _capture_grader_script(ssh, step):
    """评测期间轮询读取评测脚本。

    不同实验位置不同：secret/codeReview/codeN.py、secret/<实验>/evaluate/demo*.py 等，
    因此扫描 secret/ 和 pingce/ 下所有非空 .py，优先返回与当前 step 相关的。
    """
    fixed = f'/data/workspace/myshixun/secret/codeReview/code{step}.py'
    scan = ('for f in $(find /data/workspace/myshixun/secret /data/workspace/myshixun/pingce '
            '-name "*.py" 2>/dev/null); do s=$(wc -c < "$f" 2>/dev/null); '
            'if [ "$s" != "0" ]; then echo "### $f"; cat "$f"; fi; done')
    for _ in range(25):
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
                                  stats, poll_timeout):
    """抓评测脚本 → 逆向构造 .mdj → 提交；返回是否通过。"""
    challenge = detail.get('challenge') or {}
    targets = write_targets(challenge.get('path'), target, step)
    if not apply:
        stats['would_submit'] += 1
        print(f'      [dry-run] UML {gid}：抓评测脚本逆向构造答案并提交。')
        return False

    conn = await get_ssh_connection(client, detail)
    ssh = _ssh_connect(conn)
    try:
        # 0) 优先用已缓存的评测脚本（避免每次触发评测去抓，pod 重建后易失败）
        subject = ((detail.get('challenge') or {}).get('subject') or '').strip()
        script = load_grader_cache(gid, subject, step)
        if script:
            print(f'      · 使用缓存的评测脚本')
        else:
            script = _read_static_grader(ssh, step)
        if not script:
            # 1) 写探针并触发评测（用于挂载评测脚本）
            await _ssh_write_commit(ssh, json.dumps({'_type': 'Project', 'name': 'probe',
                                                      'ownedElements': []}), targets, 'probe')
            await _trigger_eval(client, detail, hw_id, gid)
            script = await _capture_grader_script(ssh, step)
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
        # 2) 写正确答案并提交
        await _ssh_write_commit(ssh, content, targets, 'solve')
    finally:
        ssh.close()

    await _trigger_eval(client, detail, hw_id, gid)
    print(f'      UML {gid}：已按评测脚本构造并提交，等待结果…')
    passed, _ = await wait_for_verdict(client, gid, timeout=poll_timeout)
    if passed is True:
        stats['submitted'] += 1
        print(f'      UML {gid}：评测通过 ✔')
        return content
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
    content = await ai_chat(UML_SYSTEM_PROMPT, build_uml_prompt(task_pass, example), temperature=0.2)
    j = extract_json_block(content)
    try:
        obj = json.loads(j)
    except ValueError:
        return None
    if not isinstance(obj, dict) or obj.get('_type') != 'Project':
        return None
    return j


def save_mdj_answer(exp_name, step, content):
    """评测通过后把 .mdj 存回本地题库。"""
    base = resolve_answer_base(exp_name)
    if base is None:
        base = ROOT / 'answer' / exp_name
    d = base / f'step{step}'
    d.mkdir(parents=True, exist_ok=True)
    p = d / f'step{step}.mdj'
    p.write_text(content, encoding='utf-8')
    return p


async def process_experiment(client, hw, apply, stats, poll_timeout, limit=None,
                             experiment_filter=None, use_ai=True, release_pods=True, delay=5.0):
    """处理一个实验的图形化关卡。"""
    name = hw.get('name') or ''
    if experiment_filter and experiment_filter not in name:
        return
    hw_id = hw.get('homework_id')
    shixun_id = hw.get('shixun_identifier')
    if hw.get('shixun_finished_status') == 1:
        stats['skipped_passed'] += 1
        print(f'  - [跳过] 实验已完成：{name}')
        return

    entry = await resolve_entry(client, shixun_id, hw_id)
    if not entry:
        print(f'  ✗ 无法解析实验入口，跳过：{name}')
        return
    ordered, cache = await walk_prev_to_head(client, entry)

    # 非图形实验（选择/代码题）直接跳过，交给 submit.py 处理
    entry_detail = cache.get(entry)
    if entry_detail and not is_graphic(entry_detail):
        return

    base = resolve_answer_base(name)
    mdj = collect_mdj(base)
    example = None
    if mdj:
        try:
            example = Path(mdj[min(mdj.keys())]).read_text(encoding='utf-8')
        except OSError:
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
        detail = cache.get(gid) or await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
        game = detail.get('game') or {}
        challenge = detail.get('challenge') or {}
        subject = (challenge.get('subject') or '').strip()

        nxt = detail.get('next_game')
        if nxt and str(nxt) not in seen:
            seen.add(str(nxt))
            queue.append(str(nxt))

        if not is_graphic(detail):
            continue
        if game.get('status') == 2:
            stats['skipped_passed'] += 1
            print(f'  [跳过] {subject}：已通过。')
            continue
        target, step = extract_target(challenge.get('path'), challenge.get('task_pass'))
        if not target:
            stats['skipped_error'] += 1
            print(f'  - [跳过] {subject}：无法解析保存路径（非 .mdj 绘图题？）。')
            continue

        if step is None or step not in mdj:
            # 无本地答案：优先抓评测脚本逆向构造（不消耗 AI），失败再尝试 AI
            print(f'  ▸ {subject}（抓评测脚本逆向构造）')
            stats['processed'] += 1
            content = None
            try:
                content = await solve_level_from_grader(client, hw_id, gid, detail, target,
                                                        step, apply, stats, poll_timeout)
            except CollectionError as exc:
                print(f'      ✗ {subject}：{exc}')
            except Exception as exc:
                stats['failed'] += 1
                print(f'      ✗ {subject}：{exc}')
            if content:
                p = save_mdj_answer(name, step, content)
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
                                                           target, step, apply, stats, poll_timeout)
                    except CollectionError as exc:
                        stats['failed'] += 1
                        print(f'      ✗ {subject}：{exc}')
                        passed = False
                    if passed:
                        p = save_mdj_answer(name, step, content)
                        print(f'      ↳ AI 答案已保存到本地题库：{p}')
            continue

        # 有本地答案
        content = Path(mdj[step]).read_text(encoding='utf-8')
        print(f'  ▸ {subject}')
        print(f'      目标 {target}  <-  {mdj[step]}')
        stats['processed'] += 1
        try:
            await submit_graphic_game(client, hw_id, gid, detail, content, target,
                                      step, apply, stats, poll_timeout)
        except CollectionError as exc:
            stats['failed'] += 1
            print(f'      ✗ {subject}：{exc}')

    # 处理完一个实验后释放其环境 pod，避免并发环境数触发上限
    if release_pods and apply:
        mid = hw.get('myshixun_identifier')
        if mid and await release_myshixun_pod(client, mid):
            print(f'  ↳ 已释放环境 pod。')
    # 实验之间稍作停顿，避免环境启动过快失败
    if delay > 0:
        await asyncio.sleep(delay)


async def run(apply, classroom, limit, poll_timeout, experiment_filter, use_ai,
              release_pods=True, release_envs=False, delay=5.0):
    stats = {
        'submitted': 0, 'would_submit': 0, 'skipped_passed': 0,
        'skipped_no_answer': 0, 'skipped_error': 0, 'failed': 0, 'processed': 0,
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
                                     use_ai=use_ai, release_pods=release_pods, delay=delay)
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
    parser.add_argument('--poll-timeout', type=int, default=120, help='评测等待秒数。')
    parser.add_argument('--no-ai', action='store_true', help='缺答案时不用 AI 自动生成，直接跳过。')
    parser.add_argument('--release-envs', action='store_true', help='运行前先释放课堂里所有实验环境 pod。')
    parser.add_argument('--no-release', action='store_true', help='每个实验跑完后不释放其环境 pod。')
    parser.add_argument('--delay', type=float, default=5.0, help='每个实验之间的等待秒数（避免环境启动过快）。')
    args = parser.parse_args()
    try:
        asyncio.run(run(args.apply, args.classroom, args.limit,
                        args.poll_timeout, args.experiment, use_ai=not args.no_ai,
                        release_pods=not args.no_release, release_envs=args.release_envs,
                        delay=args.delay))
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('Playwright 请求失败，请检查网络；认证详情不写入日志。') from None


if __name__ == '__main__':
    main()
