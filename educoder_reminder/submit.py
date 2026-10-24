"""根据 answers.json 自动提交头歌作业（选择题 + 代码题）。

默认 dry-run：只读取平台当前状态并打印提交计划，不真正提交；
加 --apply 才会真实提交到平台。

关键点：answers.json 里的关卡标识（game identifier）是导出时的旧值，每个学生
每次进入实验都会生成新的 myshixun/game，旧标识会 403。因此本模块不直接使用
answers.json 的标识，而是从 shixun_exec.json 重新解析当前有效的关卡链，再按
challenge.subject（关卡标题）匹配 answers.json 里的答案。

选择题：优先直接提交 answers.json 里的答案，并用平台在提交响应里回吐的标准答案
兜底重交一次。代码题：写入远程工作区 → 触发一次评测 → 轮询结果。

安全策略：
- 跳过 answers.json 里 answered=false 或没有答案的关卡；
- 跳过平台已通过（game.status==2）的关卡；
- 跳过整份实验已标记完成（shixun_finished_status==1）的实验；
- 代码题只处理单文件关卡，多文件关卡跳过以免半提交。
"""
import argparse
import asyncio
import base64
import json
import re
import time
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from .ai import AIError, ai_chat, ai_configured, strip_code_fence
from .client import open_client
from .errors import CollectionError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANSWERS = ROOT / 'answers.json'


def load_answers(path=DEFAULT_ANSWERS):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CollectionError(f'无法读取 {path}：{exc}') from None
    if data.get('kind') != 'class-answers':
        raise CollectionError('answers.json 不是 class-answers 格式。')
    return data


def split_paths(raw):
    """拆分 challenge.path：平台用全角/半角分号连接多个文件。"""
    if not raw:
        return []
    return [part.strip() for part in re.split(r'[；;]', str(raw)) if part.strip()]


def reconstruct_selected(selected):
    """把 answers.json 的 ['A','C','D'] 还原成提交用的答案字符串。"""
    letters = sorted({str(s).strip().upper() for s in selected if str(s).strip()})
    return ','.join(letters)


def harvest_key(resp):
    """从选择题提交响应里取出平台回吐的标准答案键。"""
    sets = resp.get('test_sets') or []
    if not isinstance(sets, list) or not sets:
        return None
    rows = sorted(sets, key=lambda x: x.get('position', 0))
    key = [row.get('standard_answer') for row in rows if isinstance(row, dict)]
    if key and all(k is not None and str(k).strip() != '' for k in key):
        return [str(k) for k in key]
    return None


def _norm_name(name):
    text = str(name or '').strip()
    stripped = re.sub(r'^\[[^\]]*\]\s*', '', text)
    return text, stripped


def match_homework(experiment_name, rows):
    """按实验名匹配作业行（精确 → 去掉章节前缀 → 互相包含）。"""
    target, target_stripped = _norm_name(experiment_name)
    candidates = [r for r in rows if isinstance(r, dict)]
    for row in candidates:
        name, _ = _norm_name(row.get('name'))
        if name and name == target:
            return row
    if target_stripped:
        for row in candidates:
            _, stripped = _norm_name(row.get('name'))
            if stripped and stripped == target_stripped:
                return row
    for row in candidates:
        name, _ = _norm_name(row.get('name'))
        if name and (target in name or name in target):
            return row
    return None


def _status_note(detail):
    status = detail.get('status')
    msg = detail.get('message') or detail.get('msg') or ''
    if status is None and not msg:
        return ''
    return f'（status={status}，{msg}）'


async def fetch_homework_rows(client, code):
    """抓取一个课堂的全部 type=4 实验作业（原始行）。"""
    rows = []
    for page in range(1, 100):
        data = await client.get(f'/api/courses/{code}/homework_commons.json', {
            'limit': 100, 'page': page, 'status': 0, 'id': code, 'type': 4, 'order': 0,
        })
        batch = data.get('homeworks') or []
        rows.extend(batch)
        count = data.get('query_total_count')
        if type(count) is int and len(rows) >= count:
            break
        if not batch:
            break
    return rows


async def resolve_entry(client, shixun_id, hw_id):
    """从 shixun_exec.json 解析当前有效的入口关卡标识。"""
    if not shixun_id or hw_id is None:
        return None
    data = await client.get(f'/api/shixuns/{shixun_id}/shixun_exec.json',
                            {'homework_common_id': hw_id}, strict_status=False)
    return data.get('game_identifier')


async def _detail_of(client, cache, gid):
    if gid not in cache:
        cache[gid] = await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
    return cache[gid]


async def walk_prev_to_head(client, entry):
    """从入口关卡沿 prev_game 回退到头，返回 [gid,...]（头在前）及详情缓存。"""
    cache = {}
    ordered = []
    seen = set()
    cursor = str(entry)
    while cursor and cursor not in seen:
        seen.add(cursor)
        detail = await _detail_of(client, cache, cursor)
        ordered.append(cursor)
        prev = detail.get('prev_game')
        cursor = str(prev) if prev else ''
    ordered.reverse()
    return ordered, cache


async def submit_choice(client, identifier, answers, challenge_id, subject_id, apply, stats):
    """提交选择题，返回 (状态, 最终答案列表)。"""
    payload = {
        'answer': list(answers),
        'challenge_id': challenge_id,
        'subject_id': subject_id,
        'question_id': None,
        'competition_entry_id': None,
        'smart_plan_page_item_bank_id': None,
    }
    if not apply:
        stats['would_submit'] += 1
        print(f'      [dry-run] 选择题 {identifier}：提交 {len(answers)} 题答案 {answers}')
        return 'dry-run', list(answers)

    resp = await client.post(f'/api/tasks/{identifier}/choose_build.json', {}, payload)
    correct = resp.get('choose_correct_num', 0)
    total = resp.get('challenge_chooses_count', len(answers))
    if total > 0 and correct == total:
        stats['submitted'] += 1
        print(f'      选择题 {identifier}：{correct}/{total} 正确 ✔')
        return 'ok', list(answers)

    key = harvest_key(resp)
    if key:
        payload['answer'] = key
        resp2 = await client.post(f'/api/tasks/{identifier}/choose_build.json', {}, payload)
        correct2 = resp2.get('choose_correct_num', 0)
        total2 = resp2.get('challenge_chooses_count', total)
        if total2 > 0 and correct2 == total2:
            stats['submitted'] += 1
            print(f'      选择题 {identifier}：首次 {correct}/{total}，'
                  f'用平台答案键重交后 {correct2}/{total2} ✔')
            return 'ok-fallback', key
        stats['failed'] += 1
        print(f'      选择题 {identifier}：重交后仍只对 {correct2}/{total2}，请人工核对。')
        return 'failed', key

    stats['failed'] += 1
    print(f'      选择题 {identifier}：提交 {correct}/{total}，且响应未回吐完整答案键。')
    return 'failed', list(answers)


def is_level_passed(detail):
    """关卡是否已通过（统一判定口径）。

    平台有几种表现，只看 game.status 会漏判：
    - 正常通过：game.status == 2
    - 测试集全部通过但 status 没同步（实测出现过 final_score>0、status=0）
    - test_sets 全为 True
    漏判会导致已通过的关卡被反复重新提交。
    """
    game = detail.get('game') or {}
    if game.get('status') == 2:
        return True
    if (game.get('final_score') or 0) > 0:
        return True
    tests = [t for t in (detail.get('test_sets') or [])
             if t.get('result') is not None]
    return bool(tests) and all(t.get('result') for t in tests)


def verdict_signature(detail):
    """评测结果签名：用于区分「上一次评测」与「本次评测」。

    关键是用 game.evaluate_count（评测次数）——只看 test_sets 内容不够：
    如果本次评测失败且报错信息与上次完全相同，内容签名不变会被误判成旧结果。
    """
    game = detail.get('game') or {}
    tests = detail.get('test_sets') or []
    return (game.get('status'), game.get('evaluate_count'),
            tuple((str(t.get('result')), str(t.get('actual_output'))) for t in tests))


async def wait_for_verdict(client, identifier, timeout=90, poll=2, baseline=None):
    """等评测结果；baseline 为提交前的签名，只有结果变化才算有效（避免误读旧结果）。"""
    started = time.monotonic()
    deadline = started + timeout
    last_detail = None
    # 先给平台几秒启动评测，避免读到上一次的旧结果
    await asyncio.sleep(3)
    while time.monotonic() < deadline:
        await asyncio.sleep(poll)
        detail = await client.get(f'/api/tasks/{identifier}.json', {}, strict_status=False)
        last_detail = detail
        game = detail.get('game') or {}
        status = game.get('status')
        if status == 2:
            return True, detail
        if status == 3:
            return False, detail
        # status 未同步但已经拿到分数，也算通过
        if (game.get('final_score') or 0) > 0:
            return True, detail
        tests = detail.get('test_sets') or []
        rated = [t for t in tests if t.get('result') is not None]
        if tests and len(rated) == len(tests):
            if baseline is not None:
                now_sig = verdict_signature(detail)
                if now_sig == baseline:
                    continue      # 完全是旧结果，继续等
                # evaluate_count 变了但 test_sets 内容没变：评测已执行、结果还没刷新，
                # 再等一小会儿；若持续不变则认为本次结果确实与上次相同
                if now_sig[2] == baseline[2] and time.monotonic() - started < 20:
                    continue
            return all(bool(t.get('result')) for t in tests), detail
    # 超时：用最后读到的结果兜底判断，避免只报「超时」而没有任何结论
    if last_detail:
        tests = last_detail.get('test_sets') or []
        rated = [t for t in tests if t.get('result') is not None]
        if tests and len(rated) == len(tests):
            same = baseline is not None and verdict_signature(last_detail) == baseline
            if not same:
                return all(bool(t.get('result')) for t in tests), last_detail
    return None, last_detail


async def submit_choice_game(client, gid, level, detail, level_idx, offsets, apply, stats,
                             use_ai=True):
    """提交一个选择题关卡（level 可能对应多个 game，按 chooses 数量切分答案）。"""
    items = sorted(level['answer'], key=lambda x: x.get('number', 0))
    full = [reconstruct_selected(item.get('selected', [])) for item in items]
    if not full:
        stats['skipped_no_answer'] += 1
        return False
    chooses = detail.get('chooses') or []
    count = len(chooses)
    offset = offsets.get(level_idx, 0)
    answers = full[offset:offset + count]
    offsets[level_idx] = offset + count

    # 平台题目数比答案多（如新增了题）：缺的题用 AI 补答
    if len(answers) < count and use_ai and ai_configured() and apply:
        try:
            for i in range(len(answers), count):
                extra = await ai_solve_choice([chooses[i]])
                answers.append(extra[0] if extra else 'A')
            print(f'      · 缺 {count - len(full[offset:offset + count])} 题，已用 AI 补答')
        except AIError as exc:
            print(f'      ✗ AI 补答失败：{exc}')

    challenge_id = (detail.get('challenge') or {}).get('id')
    subject_id = detail.get('subject_id')
    status, _ = await submit_choice(client, gid, answers, challenge_id, subject_id, apply, stats)
    if status in ('ok', 'ok-fallback'):
        return True

    # 仍失败且答案与题目数不匹配 / 答案过时：让 AI 重新答全部题目
    if apply and use_ai and ai_configured() and chooses:
        try:
            retry = await ai_solve_choice(chooses)
        except AIError as exc:
            print(f'      ✗ AI 重答失败：{exc}')
            return False
        if retry and retry != answers:
            print(f'      ▸ 选择题 {gid}（AI 重新作答）')
            status2, final = await submit_choice(client, gid, retry, challenge_id, subject_id,
                                                 apply, stats)
            if status2 in ('ok', 'ok-fallback'):
                level['answer'] = [{'number': i + 1, 'selected': a.split(',')}
                                   for i, a in enumerate(final)]
                level['answered'] = True
                return True
    return False


async def submit_code_game(client, hw_id, gid, code, detail, apply, stats, poll_timeout):
    """提交一个代码关卡（code 为代码文本）；返回是否评测通过。"""
    if not code or not code.strip():
        stats['skipped_no_answer'] += 1
        return False
    challenge = detail.get('challenge') or {}
    myshixun = detail.get('myshixun') or {}
    user = detail.get('user') or {}
    envs = detail.get('shixun_environments') or []
    paths = split_paths(challenge.get('path'))
    missing = []
    if not myshixun.get('identifier'):
        missing.append('myshixun identifier')
    if not challenge.get('id'):
        missing.append('challenge id')
    if not user.get('user_id'):
        missing.append('user id')
    if not paths:
        missing.append('远端文件路径')
    if len(paths) != 1:
        missing.append(f'多文件关卡（{len(paths)} 个文件，暂不支持自动拆分）')
    if missing:
        stats['skipped_error'] += 1
        print(f'      [跳过] 代码题 {gid}：缺少 {"、".join(missing)}。')
        return False
    path = paths[0]
    if path.endswith('.sql') and code:
        # SQL 必须在初始模板上补充：模板里的 use 提供数据库上下文，重写会报
        # No database selected / Unknown database。优先用本地缓存的原始模板
        # （远端提交后会被覆盖，所以第一次读到就存一份）。
        subject = (challenge.get('subject') or '').strip()
        step_no = None
        m_step = re.search(r'step[_]?(\d+)', path)
        if m_step:
            step_no = int(m_step.group(1))
        tpl = load_template(subject, step_no)
        if tpl is None:
            fresh = await read_remote_file(client, gid, hw_id, path)
            # 远端内容看起来还是模板（含 use 且没被我们填过）才缓存
            if fresh.strip() and re.search(r'^\s*use\s+', fresh, re.M | re.I):
                tpl = fresh
                save_template(subject, step_no, fresh)
        if tpl:
            code = merge_sql_template(tpl, code)
        code = postprocess_sql(code, tpl, challenge.get('task_pass'))
    if not apply:
        stats['would_submit'] += 1
        print(f'      [dry-run] 代码题 {gid}：写入 {path}（{len(code)} 字符）并触发评测。')
        return False

    extras = {
        'challenge_id': challenge['id'],
        'homework_common_id': hw_id,
        'currentUserId': user['user_id'],
        'exercise_id': '',
        'question_id': '',
        'subject_id': '',
        'competition_entry_id': '',
    }
    env_id = envs[0].get('shixun_environment_id') if envs else 0
    # 提交前实时读一次，记录旧评测签名，避免提交后误读到上一次的结果
    try:
        fresh = await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
        baseline = verdict_signature(fresh)
    except CollectionError:
        baseline = verdict_signature(detail)
    save_resp = await client.post(
        f'/api/myshixuns/{myshixun["identifier"]}/update_file.json', {}, {
            'path': path,
            'evaluate': 0,
            'content': code,
            'game_id': detail.get('game', {}).get('id'),
            'tab_type': 1,
            'homework_common_id': hw_id,
            'extras': extras,
        })
    content = save_resp.get('content')
    commit_id = content.get('commitID', '') if isinstance(content, dict) else ''
    grade_resp = await client.post(
        f'/api/tasks/{gid}/game_build.json', {}, {
            'sec_key': detail.get('sec_key', ''),
            'resubmit': '',
            'first': 1,
            'content_modified': 0,
            'shixun_environment_id': env_id,
            'tab_type': 1,
            'extras': {**extras, 'commitID': commit_id or str(myshixun.get('commit_id', ''))},
        })
    res = grade_resp.get('res')
    err_code = res.get('code') if isinstance(res, dict) else grade_resp.get('code')
    if err_code is not None and err_code != 0:
        stats['failed'] += 1
        print(f'      代码题 {gid}：评测未能启动（code={err_code}）。')
        return False
    print(f'      代码题 {gid}：已提交，等待评测…')
    passed, _ = await wait_for_verdict(client, gid, timeout=poll_timeout, baseline=baseline)
    if passed is True:
        stats['submitted'] += 1
        print(f'      代码题 {gid}：评测通过 ✔')
        return True
    if passed is False:
        stats['failed'] += 1
        print(f'      代码题 {gid}：评测未通过，请查看平台反馈。')
    else:
        stats['failed'] += 1
        print(f'      代码题 {gid}：评测超时（>{poll_timeout}s），请到平台确认。')
    return False


# --- AI 自动做题（选择题 + 代码题）---

CHOICE_SYSTEM = '你是答题助手。根据题目选择正确答案。只输出选项字母。'
CODE_SYSTEM = '你是编程专家。根据题目要求写出完整代码。只输出代码本身，不要 markdown 代码块或解释。'


def detect_kind(detail):
    """从平台关卡详情推断题型：choice / code / None。"""
    if detail.get('chooses'):
        return 'choice'
    challenge = detail.get('challenge') or {}
    if challenge.get('path') and not detail.get('vnc_url'):
        return 'code'
    return None


async def ai_solve_choice(chooses):
    """AI 选择题：返回按关卡切分的答案列表（如 ['A', 'A,C']）。"""
    answers = []
    for q in chooses:
        text = (q.get('subject') or '').strip()
        opts = q.get('challenge_question') or []
        letters = [chr(ord('A') + i) for i in range(len(opts))]
        lines = [f'题目：{text}', '选项：']
        for i, o in enumerate(opts):
            lines.append(f'{letters[i]}. {o.get("option_name")}')
        multi = '多' in (q.get('question_name') or '') or len(opts) > 4
        lines.append('请选出所有正确答案，用逗号分隔（如 A,C），只输出字母。' if multi
                     else '请选出唯一正确答案，只输出一个字母（如 A）。')
        content = await ai_chat(CHOICE_SYSTEM, '\n'.join(lines), temperature=0)
        sel = []
        for c in content.upper():
            if 'A' <= c <= 'Z' and c in letters and c not in sel:
                sel.append(c)
        if not sel:
            sel = ['A']
        answers.append(','.join(sel))
    return answers


async def ai_solve_code(task_pass, path, grader_hint=None, expected_output=None,
                        template=None):
    """AI 生成代码文本；template 为当前文件的初始模板，AI 在其基础上修改。"""
    text = re.sub(r'<[^>]+>', ' ', task_pass or '')
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 6000:
        text = text[:6000] + '…'
    prompt = f'题目要求：\n{text}\n\n目标文件路径：{path}\n'
    if template and template.strip():
        tpl = template
        if len(tpl) > 6000:
            tpl = tpl[:6000] + '…'
        prompt += (f'\n以下是该文件当前的内容（初始代码模板），必须在此基础上修改：\n'
                   f'```\n{tpl}\n```\n\n'
                   f'要求：保留模板里所有已有的结构（import、use 语句、函数定义与签名、'
                   f'注释框架、Begin/End 标记、文件路径常量等）；只填充题目要求的部分；'
                   f'输出修改后的完整文件内容。\n')
        if path.endswith('.sql'):
            prompt += ('SQL 特别注意：模板里的 use 语句必须原样保留，数据库名不要改动、'
                       '不要臆造新的库名；不要删除模板中的注释和结尾标记。\n')
    else:
        prompt += '请生成该文件的完整代码。\n'
    if grader_hint:
        hint = re.sub(r'<[^>]+>', ' ', grader_hint)
        hint = re.sub(r'\s+', ' ', hint).strip()
        if len(hint) > 5000:
            hint = hint[:5000] + '…'
        if path.endswith('.sql'):
            prompt += (f'\n\n以下是本课程数据库的真实表结构（必须严格使用这些表名和字段名，'
                       f'不要臆造字段）：\n{hint}\n\n'
                       f'重要：每一关评测都会重新初始化数据库（基础表和数据由平台自动创建，'
                       f'不要重复建表）。但之前关卡创建的视图等对象不会保留——如果本关依赖它们，'
                       f'请在本关 SQL 里用 CREATE OR REPLACE VIEW 等自行创建，使本关 SQL 自包含。\n')
        else:
            prompt += (f'\n\n以下是平台的评测脚本，它从你的文件里 import 函数并调用，'
                       f'请严格按它要求的函数名、参数名、默认参数和返回值实现：\n{hint}\n')
    if expected_output:
        exp = (expected_output or '').strip()
        if len(exp) > 1000:
            exp = exp[:1000] + '…'
        prompt += (f'\n\n平台的预期输出（参考，尽量让你的程序输出与之一致）：\n{exp}\n')
    content = await ai_chat(CODE_SYSTEM, prompt, temperature=0.1, max_tokens=8192)
    return strip_code_fence(content)


async def get_code_feedback(client, gid):
    """读取最近一次评测的预期输出与实际反馈。"""
    detail = await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
    expected, actual = [], []
    for t in detail.get('test_sets') or []:
        o = (t.get('output') or '').strip()
        ao = (t.get('actual_output') or '').strip()
        if o:
            expected.append(o)
        if ao:
            actual.append(ao)
    return '\n'.join(expected), '\n'.join(actual)


async def ai_fix_code(task_pass, path, existing_code, expected, actual):
    """AI 在已有代码基础上根据预期输出与失败反馈修正代码。"""
    text = re.sub(r'<[^>]+>', ' ', task_pass or '')
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 4000:
        text = text[:4000] + '…'
    old = (existing_code or '').strip()
    if len(old) > 8000:
        old = old[:8000] + '…'
    exp = (expected or '').strip()
    fb = (actual or '').strip()
    if len(exp) > 1500:
        exp = exp[:1500] + '…'
    if len(fb) > 1500:
        fb = fb[:1500] + '…'
    prompt = (f'题目要求：\n{text}\n\n目标文件路径：{path}\n\n'
              f'你上一次提交的代码：\n{old}\n\n'
              f'平台预期输出：\n{exp}\n\n'
              f'上一次评测失败，平台反馈：\n{fb}\n\n'
              f'请在上一次代码基础上修正（务必保留所有函数定义和参数签名，不要删除任何函数），'
              f'生成完整可运行的代码，确保输出与预期输出一致。')
    content = await ai_chat(CODE_SYSTEM, prompt, temperature=0.1, max_tokens=8192)
    return strip_code_fence(content)


# --- 读测试文件提取参考答案（比 AI 可靠） ---

async def read_remote_file(client, gid, hw_id, path):
    """读取远端工作区文件内容。"""
    data = await client.get(f'/api/tasks/{gid}/rep_content.json',
                            {'path': path, 'homework_common_id': hw_id, 'exercise_id': ''},
                            strict_status=False)
    cd = data.get('content') or {}
    content = cd.get('content', '') if isinstance(cd, dict) else ''
    return base64.b64decode(content).decode('utf-8', 'replace') if content else ''


TEMPLATE_DIR = ROOT / 'templates'


def merge_sql_template(template, answer):
    """把答案合并进「初始模板」骨架，而不是整体替换。

    评测依赖模板提供的上下文，重写会失败：
    - 模板里的 `use X;` 提供数据库上下文，缺了会报 No database selected
    - 答案如果自己编了别的库名，会被模板里的库名替换掉
    - 模板的结尾标记（/* end of your code */）保留不动

    示例：
      模板: use finance1;\n-- 注释\n/* end of your code */
      答案: CREATE OR REPLACE VIEW v AS SELECT 1;
      结果: use finance1;
            CREATE OR REPLACE VIEW v AS SELECT 1;
            /* end of your code */
    """
    if not template or not template.strip():
        return answer
    if not answer or not answer.strip():
        return answer

    # 1) 数据库上下文：以模板的 use 为准
    tpl_use = re.search(r'^\s*use\s+`?(\w+)`?\s*;[ \t]*$', template, re.M | re.I)
    if tpl_use:
        tpl_db = tpl_use.group(1)
        ans_use = re.search(r'^\s*use\s+`?(\w+)`?\s*;[ \t]*$', answer, re.M | re.I)
        if not ans_use:
            answer = tpl_use.group(0).strip() + '\n' + answer
        elif ans_use.group(1) != tpl_db:
            # 答案臆造了别的库名 → 换回模板的库
            answer = (answer[:ans_use.start()] + tpl_use.group(0).strip()
                      + answer[ans_use.end():])

    # 2) 结尾标记：模板有就保留
    tail = re.search(r'/\*+\s*(?:end|End)[^*]*\*+/\s*$', template, re.S)
    if tail and not re.search(r'/\*+\s*(?:end|End)', answer, re.I):
        answer = answer.rstrip() + '\n' + tail.group(0).strip()

    return answer


def save_template(name, step, content):
    """缓存关卡初始模板（远端提交后会被覆盖，必须提前存一份）。"""
    try:
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[^\w\u4e00-\u9fff-]+', '_', name or 'x')[:60]
        (TEMPLATE_DIR / f'{safe}_step{step}.sql').write_text(content, encoding='utf-8')
    except OSError:
        pass


def load_template(name, step):
    try:
        safe = re.sub(r'[^\w\u4e00-\u9fff-]+', '_', name or 'x')[:60]
        return (TEMPLATE_DIR / f'{safe}_step{step}.sql').read_text(encoding='utf-8')
    except OSError:
        return None


def strip_postprocess_artifacts(sql):
    """去掉提交时临时添加的内容（CREATE DATABASE / DROP TABLE IF EXISTS）。

    answers.json 只保存「用户答案」，这些补齐项必须在提交时动态生成，
    否则会污染答案：例如给 aircon 这类平台预置库额外 CREATE DATABASE
    会得到空库，反而报 Table doesn't exist。
    """
    if not sql:
        return sql
    lines = sql.split('\n')
    out = []
    for line in lines:
        st = line.strip()
        if re.match(r'^CREATE\s+DATABASE\s+IF\s+NOT\s+EXISTS\b', st, re.I):
            continue
        if re.match(r'^DROP\s+TABLE\s+IF\s+EXISTS\b', st, re.I):
            continue
        out.append(line)
    cleaned = '\n'.join(out)
    return re.sub(r'\n{3,}', '\n\n', cleaned).strip() + '\n'


def postprocess_sql(code, template, task_pass):
    """SQL 后处理：合并模板骨架 + 补数据库 + CREATE 前加 DROP（幂等）。"""
    if not code:
        return code
    code = merge_sql_template(template, code)
    code = ensure_sql_use(code, template, guess_db_name(task_pass))
    code = ensure_sql_drop_before_create(code)
    return code


async def read_grader_file(client, gid, hw_id, student_path):
    """读 main.py / test.py（评测脚本），了解要求的函数签名。"""
    directory = student_path.rsplit('/', 1)[0] if '/' in student_path else ''
    for name in ('main.py', 'test.py', 'evaluate.py', 'check.py', 'judge.py', 'eval.py'):
        path = f'{directory}/{name}' if directory else name
        txt = await read_remote_file(client, gid, hw_id, path)
        if txt.strip():
            return txt
    return None


async def read_sql_schema(client, gid, hw_id, student_path):
    """SQL 题：读同/上级目录的 *.sql 数据文件，提取 CREATE TABLE 建表语句。"""
    directory = student_path.rsplit('/', 1)[0] if '/' in student_path else ''
    candidates = []
    for d in (directory, '../', ''):
        for n in ('finance1.sql', 'finance2.sql', 'init.sql', 'schema.sql', 'data.sql'):
            p = f'{d}/{n}' if d else n
            if p not in candidates:
                candidates.append(p)
    for p in candidates:
        txt = await read_remote_file(client, gid, hw_id, p)
        if not txt.strip():
            continue
        tables = re.findall(
            r'CREATE TABLE[^;]+?\)\s*ENGINE[^;]*;', txt, re.S | re.I)
        if tables:
            return '\n\n'.join(tables)
    return None


def extract_field_tables(text):
    """从题目描述（markdown）提取「字段名称」表结构表格（含上方表名）。"""
    if not text:
        return None
    lines = text.split('\n')
    blocks, cur, start = [], [], 0
    for i, line in enumerate(lines):
        if line.strip().startswith('|'):
            if not cur:
                start = i
            cur.append(line.rstrip())
        else:
            if cur and any('字段名称' in l for l in cur):
                ctx = '\n'.join(l.strip() for l in lines[max(0, start - 4):start]
                                 if l.strip() and not l.strip().startswith('!'))
                blocks.append((ctx + '\n' + '\n'.join(cur)).strip())
            cur = []
    if cur and any('字段名称' in l for l in cur):
        ctx = '\n'.join(l.strip() for l in lines[max(0, start - 4):start]
                         if l.strip() and not l.strip().startswith('!'))
        blocks.append((ctx + '\n' + '\n'.join(cur)).strip())
    return '\n\n'.join(blocks) if blocks else None


# 课堂 code -> 表结构说明缓存（表结构往往只写在某个关卡的题目里，其它关卡只写「回看」）
_SCHEMA_CACHE = {}


def guess_db_name(text):
    """从题目描述猜当前使用的数据库名（如 aircon / finance1 / MyDb）。"""
    t = text or ''
    patterns = [
        r'在数据库\s*`?([a-zA-Z_][\w]*)`?\s*[中里]',
        r'数据库(?:名称)?(?:仍然)?(?:为|是)\s*`?([a-zA-Z_][\w]*)',
        r'(?:自动)?创建\s*`?([a-zA-Z_][\w]*)`?\s*数据库',
        r'\buse\s+([a-zA-Z_][\w]*)',
        r'`([a-zA-Z_][\w]*)`\s*数据库',
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            return m.group(1)
    return None


_USE_RE = re.compile(r'^\s*use\s+\w+\s*;', re.M | re.I)


def ensure_sql_use(sql, template, db_name):
    """确保 SQL 里的数据库存在。

    - 没有 use 语句：按 db_name 补 CREATE DATABASE + use
    - 已有 use X：在它前面补 CREATE DATABASE IF NOT EXISTS X
      （pod 重建后数据库会丢，评测会报 Unknown database）
    """
    if not sql:
        return sql
    m = re.search(r'^\s*use\s+`?(\w+)`?\s*;', sql, re.M | re.I)
    if not m:
        # 没有 use 语句时：
        # - 只建表（CREATE TABLE）才补库名，否则会得到空库反而报 Table doesn't exist
        # - 纯查询/建视图不动，库由平台预置
        if not db_name or not re.search(r'\bcreate\s+table\b', sql, re.I):
            return sql
        db = db_name
    else:
        db = m.group(1)
    already = re.search(
        r'create\s+database\s+(?:if\s+not\s+exists\s+)?`?' + re.escape(db) + r'`?',
        sql, re.I)
    if already:
        return sql
    create = 'CREATE DATABASE IF NOT EXISTS `' + db + '`;\n'
    if m:
        return sql[:m.start()] + create + sql[m.start():]
    return create + 'use ' + db + ';\n' + sql


def ensure_sql_drop_before_create(sql):
    """在每个 CREATE TABLE 前插入 DROP TABLE IF EXISTS（避免重复提交时表已存在）。"""
    if not sql:
        return sql
    out, pos = [], 0
    for m in re.finditer(
            r'create\s+table\s+(?:if\s+not\s+exists\s+)?`?(\w+)`?', sql, re.I):
        name = m.group(1)
        out.append(sql[pos:m.start()])
        if not re.search(
                rf'drop\s+table\s+(?:if\s+exists\s+)?`?{re.escape(name)}`?', sql, re.I):
            out.append(f'DROP TABLE IF EXISTS `{name}`;\n')
        out.append(m.group(0))
        pos = m.end()
    out.append(sql[pos:])
    return ''.join(out)


async def get_classroom_schema(client, code, prefer=None, current_task_pass=None):
    """扫描课堂各实验入口关卡，找出题目里的表结构说明。

    prefer：当前题目的数据库名，含该名字的优先。
    """
    cache_key = (code, prefer)
    if cache_key in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[cache_key]
    if not prefer and current_task_pass:
        prefer = guess_db_name(current_task_pass)
        cache_key = (code, prefer)
        if cache_key in _SCHEMA_CACHE:
            return _SCHEMA_CACHE[cache_key]
    matched, others = [], []
    try:
        rows = await fetch_homework_rows(client, code)
        for hw in rows:
            entry = await resolve_entry(client, hw.get('shixun_identifier'), hw.get('homework_id'))
            if not entry:
                continue
            try:
                d = await client.get(f'/api/tasks/{entry}.json', {}, strict_status=False)
                # 表结构通常在关卡链的头部（第1关），需先回退到链头
                ordered, cache = await walk_prev_to_head(client, entry)
                if ordered:
                    head = cache.get(ordered[0])
                    if head:
                        d = head
            except CollectionError:
                continue
            tp = (d.get('challenge') or {}).get('task_pass') or ''
            t = extract_field_tables(tp)
            if not t:
                continue
            if prefer and prefer.lower() in tp.lower():
                matched.append(t)
            else:
                others.append(t)
    except CollectionError:
        pass
    parts = matched[:2] if matched else others[:1]
    schema = '\n\n'.join(parts)
    if len(schema) > 6000:
        schema = schema[:6000] + '…'
    _SCHEMA_CACHE[cache_key] = schema
    return schema


def _top_level_funcs(text):
    """提取文本里所有顶层 def 函数块，返回 {函数名: 代码块}。"""
    lines = text.split('\n')
    funcs = {}
    i = 0
    while i < len(lines):
        m = re.match(r'^def\s+(\w+)\s*\(', lines[i])
        if m:
            name = m.group(1)
            start = i
            i += 1
            while i < len(lines) and not re.match(r'^(def\s+|if\s+__name__|class\s+)', lines[i]):
                i += 1
            funcs[name] = '\n'.join(lines[start:i])
        else:
            i += 1
    return funcs


def extract_reference_from_test(test_content, student_basename):
    """从测试文件里提取参考答案代码；失败返回 None。"""
    if not test_content:
        return None
    module = None
    for m in re.finditer(r'^import\s+(\w+)', test_content, re.M):
        if m.group(1).lower() == student_basename.lower():
            module = m.group(1)
            break
    if module is None:
        for m in re.finditer(r'^from\s+(\w+)\s+import', test_content, re.M):
            if m.group(1).lower() == student_basename.lower():
                module = m.group(1)
                break
    if module is None:
        return None
    targets = set()
    for m in re.finditer(rf'\b{re.escape(module)}\.(\w+)\s*\(', test_content):
        targets.add(m.group(1))
    funcs = _top_level_funcs(test_content)
    selected = [funcs[t] for t in sorted(targets) if t in funcs]
    if not selected:
        return None
    imports = []
    for m in re.finditer(r'^(?:import|from)\s+([^\n]+)', test_content, re.M):
        first = m.group(1).split()[0]
        if first.lower() == student_basename.lower():
            continue
        imports.append(m.group(0).strip())
    return '\n'.join(imports) + '\n\n\n' + '\n\n\n'.join(selected)


async def solve_code_from_test(client, gid, hw_id, student_path):
    """读测试文件并提取参考答案；失败返回 None。"""
    if not student_path:
        return None
    directory, sep, filename = student_path.rpartition('/')
    directory = directory if sep else ''
    basename = filename.rsplit('.', 1)[0]
    names = [f'test_{basename}.py', f'test_{basename.lower()}.py', f'test_{basename.upper()}.py',
             'test.py', f'{basename}_test.py', f'{basename.lower()}_test.py']
    seen = set()
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        path = f'{directory}/{n}' if directory else n
        txt = await read_remote_file(client, gid, hw_id, path)
        code = extract_reference_from_test(txt, basename)
        if code:
            return code
    return None


def save_level_answer(data, classroom_code, hw_name, subject, kind, answer):
    """把 AI 做题结果写回 answers.json 结构（内存）。"""
    for c in data.get('classrooms', []):
        if c.get('code') != classroom_code:
            continue
        experiments = c.setdefault('experiments', [])
        exp = match_homework(hw_name, experiments)
        if exp is None:
            exp = {'name': hw_name, 'levels': []}
            experiments.append(exp)
        levels = exp.setdefault('levels', [])
        if kind == 'code' and isinstance(answer, dict) and answer.get('code', '').lstrip().upper().startswith(
                ('CREATE', 'USE', 'SELECT', 'INSERT', 'DELETE', 'UPDATE', 'DROP', 'ALTER')):
            answer = {**answer, 'code': strip_postprocess_artifacts(answer['code'])}
        for lv in levels:
            if (lv.get('title') or '').strip() == subject.strip():
                lv['answered'] = True
                lv['kind'] = kind
                lv['answer'] = answer
                return
        levels.append({'title': subject, 'kind': kind, 'answered': True, 'answer': answer})
        return


async def ai_submit_level(client, hw_id, gid, detail, subject, kind, apply, stats,
                          poll_timeout, answers, classroom_code, hw_name):
    """用 AI 生成答案并提交；评测通过后写回 answers.json。返回是否通过。"""
    if kind == 'choice':
        chooses = detail.get('chooses') or []
        if not chooses:
            return False
        try:
            sel = await ai_solve_choice(chooses)
        except AIError as exc:
            stats['failed'] += 1
            print(f'      ✗ {subject}：AI 调用失败：{exc}')
            return False
        challenge_id = (detail.get('challenge') or {}).get('id')
        subject_id = detail.get('subject_id')
        status, final_ans = await submit_choice(client, gid, sel, challenge_id, subject_id, apply, stats)
        if status in ('ok', 'ok-fallback'):
            ans = [{'number': i + 1, 'selected': s.split(',')} for i, s in enumerate(final_ans)]
            save_level_answer(answers, classroom_code, hw_name, subject, 'choice', ans)
            return True
        return False

    if kind == 'code':
        challenge = detail.get('challenge') or {}
        paths = split_paths(challenge.get('path'))
        if len(paths) != 1:
            stats['skipped_error'] += 1
            print(f'      [跳过] {subject}：多文件关卡，AI 暂不支持。')
            return False
        if not apply:
            stats['would_submit'] += 1
            print(f'      [dry-run] 代码题 {gid}：写 {paths[0]} 并评测。')
            return False
        # 1) 优先读测试文件提取参考答案（比 AI 可靠）
        code = await solve_code_from_test(client, gid, hw_id, paths[0])
        if code:
            print(f'      ▸ {subject}（读测试文件提取参考答案）')
        else:
            # 2) 再 AI 生成（带初始模板 + 评测脚本 + 预期输出）
            try:
                template = await read_remote_file(client, gid, hw_id, paths[0])
                if paths[0].endswith('.sql'):
                    hint = await read_sql_schema(client, gid, hw_id, paths[0])
                    if not hint:
                        # 表结构可能只写在别的关卡题目里，从课堂全局找
                        hint = await get_classroom_schema(
                            client, classroom_code, current_task_pass=challenge.get('task_pass'))
                    if not hint:
                        hint = extract_field_tables(challenge.get('task_pass'))
                else:
                    hint = await read_grader_file(client, gid, hw_id, paths[0])
                expected = '\n'.join(
                    (t.get('output') or '').strip()
                    for t in detail.get('test_sets') or []
                    if (t.get('output') or '').strip())
                code = await ai_solve_code(challenge.get('task_pass'), paths[0],
                                           grader_hint=hint, expected_output=expected,
                                           template=template)
                if paths[0].endswith('.sql') and code:
                    # 有些关卡模板没写 use，评测会报 No database selected
                    code = ensure_sql_use(code, template,
                                          guess_db_name(challenge.get('task_pass')))
                    code = ensure_sql_drop_before_create(code)
            except AIError as exc:
                stats['failed'] += 1
                print(f'      ✗ {subject}：AI 调用失败：{exc}')
                return False
            if not code or not code.strip():
                stats['skipped_no_answer'] += 1
                print(f'      - [跳过] {subject}：AI 未生成代码。')
                return False
        passed = await submit_code_game(client, hw_id, gid, code, detail, apply, stats, poll_timeout)
        if passed:
            save_level_answer(answers, classroom_code, hw_name, subject, 'code',
                              {'language': '', 'code': code})
            print(f'      ↳ 答案已写回 answers.json。')
            return True
        # 失败后用评测反馈重试一次
        if apply and ai_configured():
            try:
                expected, feedback = await get_code_feedback(client, gid)
                new_code = await ai_fix_code(challenge.get('task_pass'), paths[0], code,
                                             expected, feedback)
            except AIError as exc:
                stats['failed'] += 1
                print(f'      ✗ {subject}：AI 重试失败：{exc}')
                new_code = None
            if new_code and new_code.strip() and new_code != code:
                if paths[0].endswith('.sql'):
                    tpl = await read_remote_file(client, gid, hw_id, paths[0])
                    new_code = postprocess_sql(new_code, tpl, challenge.get('task_pass'))
                print(f'      ▸ {subject}（AI 根据反馈重试）')
                passed = await submit_code_game(client, hw_id, gid, new_code, detail, apply,
                                                stats, poll_timeout)
                if passed:
                    save_level_answer(answers, classroom_code, hw_name, subject, 'code',
                                      {'language': '', 'code': new_code})
                    print(f'      ↳ AI 修正后的答案已写回 answers.json。')
                    return True
        return False

    stats['skipped_error'] += 1
    print(f'      - [跳过] {subject}：未知题型，无法 AI 做题。')
    return False


async def process_experiment(client, hw_row, experiment, apply, stats, poll_timeout, limit=None,
                             answers=None, classroom_code=None, use_ai=True, delay=5.0):
    """处理一个实验：解析当前关卡链 → 按标题匹配 answers.json → 逐关提交。"""
    hw_id = hw_row.get('homework_id')
    shixun_id = hw_row.get('shixun_identifier')
    levels = experiment.get('levels', [])

    entry = await resolve_entry(client, shixun_id, hw_id)
    if not entry:
        stats['skipped_error'] += len(levels)
        print(f'  ✗ 无法解析实验入口关卡（shixun_exec 无 game_identifier），跳过。')
        return

    ordered, cache = await walk_prev_to_head(client, entry)
    if not ordered:
        stats['skipped_error'] += len(levels)
        print(f'  ✗ 关卡链为空，跳过。')
        return

    # 标题 → 该标题对应的 level 下标列表（通常一个标题对应一个 level）。
    title_index = {}
    for i, lv in enumerate(levels):
        title = (lv.get('title') or '').strip()
        if title:
            title_index.setdefault(title, []).append(i)

    def find_level_indices(subject):
        s = (subject or '').strip()
        if not s:
            return None
        if s in title_index:
            return title_index[s]
        sn = re.sub(r'\s+', '', s)
        for t, idxs in title_index.items():
            if re.sub(r'\s+', '', t) == sn:
                return idxs
        for t, idxs in title_index.items():
            if s and (s in t or t in s):
                return idxs
        return None

    consumed = {}   # level_idx -> 已消费的 game 数
    offsets = {}    # level_idx -> 选择题答案切分游标
    queue = list(ordered)
    seen = set(ordered)
    done = set()

    while queue:
        if limit is not None and stats.get('processed', 0) >= limit:
            print(f'  … 达到 --limit {limit}，停止。')
            return
        gid = queue.pop(0)
        if gid in done:
            continue
        done.add(gid)
        detail = await _detail_of(client, cache, gid)
        game = detail.get('game') or {}
        challenge = detail.get('challenge') or {}
        subject = (challenge.get('subject') or '').strip()

        idxs = find_level_indices(subject) or []
        level_idx = None
        for ci in idxs:
            if consumed.get(ci, 0) < len(levels[ci].get('identifiers', [1])):
                level_idx = ci
                break
        level = levels[level_idx] if level_idx is not None else None
        kind = level.get('kind') if level is not None else detect_kind(detail)
        if level is not None:
            consumed[level_idx] = consumed.get(level_idx, 0) + 1
        stats['processed'] = stats.get('processed', 0) + 1

        mutated = False
        if is_level_passed(detail):
            stats['skipped_passed'] += 1
            print(f'      [跳过] {subject}：已通过。')
        elif level is not None and level.get('answered'):
            try:
                if kind == 'choice':
                    mutated = await submit_choice_game(
                        client, gid, level, detail, level_idx, offsets, apply, stats,
                        use_ai=use_ai)
                elif kind == 'code':
                    code = level['answer'].get('code') if isinstance(level.get('answer'), dict) else None
                    mutated = await submit_code_game(
                        client, hw_id, gid, code, detail, apply, stats, poll_timeout)
                    path = (split_paths(challenge.get('path')) or [''])[0]
                    if not mutated and apply:
                        # 1) 优先读测试文件提取参考答案
                        ref = await solve_code_from_test(client, gid, hw_id, path)
                        if ref and ref.strip():
                            print(f'      ▸ {subject}（读测试文件提取参考答案）')
                            mutated = await submit_code_game(
                                client, hw_id, gid, ref, detail, apply, stats, poll_timeout)
                            if mutated:
                                save_level_answer(answers, classroom_code, hw_row.get('name'),
                                                  subject, 'code', {'language': '', 'code': ref})
                                print(f'      ↳ 参考答案已写回 answers.json。')
                        # 2) 再 AI 根据反馈重试
                        if not mutated and use_ai and ai_configured():
                            try:
                                expected, feedback = await get_code_feedback(client, gid)
                                new_code = await ai_fix_code(challenge.get('task_pass'), path, code, expected, feedback)
                            except AIError as exc:
                                stats['failed'] += 1
                                print(f'      ✗ {subject}：AI 重试失败：{exc}')
                                new_code = None
                            if new_code and new_code.strip():
                                if path.endswith('.sql'):
                                    tpl = await read_remote_file(client, gid, hw_id, path)
                                    new_code = postprocess_sql(new_code, tpl, challenge.get('task_pass'))
                                print(f'      ▸ {subject}（AI 修正重试）')
                                mutated = await submit_code_game(
                                    client, hw_id, gid, new_code, detail, apply, stats, poll_timeout)
                                if mutated:
                                    save_level_answer(answers, classroom_code, hw_row.get('name'),
                                                      subject, 'code', {'language': '', 'code': new_code})
                                    print(f'      ↳ AI 修正后的答案已写回 answers.json。')
                else:
                    stats['skipped_error'] += 1
                    print(f'      - [跳过] {subject}：未知类型 {kind}。')
            except CollectionError as exc:
                stats['failed'] += 1
                print(f'      ✗ {subject}：{exc}')
        else:
            # 无本地答案：图形题（kind=None）由 submit_uml 处理，这里静默跳过
            if kind is None:
                continue
            # 配置了 AI 就用 AI 做题
            if not (use_ai and ai_configured()):
                stats['skipped_no_answer'] += 1
                print(f'      - [跳过] {subject}：answers.json 未记录答案。')
            else:
                print(f'      ▸ {subject}（AI 自动做题）')
                mutated = await ai_submit_level(
                    client, hw_id, gid, detail, subject, kind, apply, stats,
                    poll_timeout, answers, classroom_code, hw_row.get('name'))

        if mutated:
            # 通过后 next_game 才会出现，重读一次以继续遍历。
            cache.pop(gid, None)
            detail = await _detail_of(client, cache, gid)

        nxt = detail.get('next_game')
        if nxt and str(nxt) not in seen:
            seen.add(str(nxt))
            queue.append(str(nxt))

    # 每个实验之间稍作停顿，避免环境启动过快失败
    if delay > 0:
        await asyncio.sleep(delay)


async def run(apply, classroom_filter, limit, poll_timeout, answers_path, use_ai=True, delay=5.0):
    answers = load_answers(answers_path)
    stats = {
        'submitted': 0, 'would_submit': 0, 'skipped_passed': 0,
        'skipped_no_answer': 0, 'skipped_error': 0, 'failed': 0, 'processed': 0,
    }
    classrooms = answers.get('classrooms', [])
    codes = [c.get('code') for c in classrooms]
    if classroom_filter and classroom_filter not in codes:
        print(f'⚠️  --classroom {classroom_filter!r} 在 answers.json 中不存在。')
        print('可选课堂 code：')
        for c in classrooms:
            print(f'  {c.get("code")}  ->  {c.get("name")}')
        return stats
    async with open_client() as client:
        for classroom in classrooms:
            code = classroom.get('code')
            if classroom_filter and code != classroom_filter:
                continue
            print(f'\n===== 课堂：{classroom.get("name")}（{code}）=====')
            try:
                rows = await fetch_homework_rows(client, code)
            except CollectionError as exc:
                stats['skipped_error'] += len(classroom.get('experiments', []))
                print(f'  ✗ 无法读取课堂作业列表，跳过整个课堂：{exc}')
                continue
            matched_names = set()
            for experiment in classroom.get('experiments', []):
                hw = match_homework(experiment.get('name'), rows)
                if hw is None:
                    stats['skipped_error'] += len(experiment.get('levels', []))
                    print(f'  ✗ 实验「{experiment.get("name")}」未在课堂列表中找到，跳过。')
                    continue
                matched_names.add(hw.get('name') or '')
                if hw.get('shixun_finished_status') == 1:
                    stats['skipped_passed'] += len(experiment.get('levels', []))
                    print(f'  - [跳过] 实验已完成：{experiment.get("name")}')
                    continue
                print(f'  ▸ 实验：{experiment.get("name")}（homework_id={hw.get("homework_id")}）')
                try:
                    await process_experiment(client, hw, experiment, apply, stats,
                                             poll_timeout, limit=limit, answers=answers,
                                             classroom_code=code, use_ai=use_ai, delay=delay)
                except CollectionError as exc:
                    stats['skipped_error'] += len(experiment.get('levels', []))
                    print(f'  ✗ 实验处理失败：{exc}')

            # answers.json 里没有收录的实验：选择/代码题用 AI 补做，图形题自动跳过
            for hw in rows:
                if (hw.get('name') or '') in matched_names:
                    continue
                if hw.get('shixun_finished_status') == 1:
                    continue
                synthetic = {'name': hw.get('name'), 'levels': []}
                print(f'  ▸ 实验（answers.json 未收录，AI 补做）：{hw.get("name")}'
                      f'（homework_id={hw.get("homework_id")}）')
                try:
                    await process_experiment(client, hw, synthetic, apply, stats,
                                             poll_timeout, limit=limit, answers=answers,
                                             classroom_code=code, use_ai=use_ai, delay=delay)
                except CollectionError as exc:
                    stats['skipped_error'] += 1
                    print(f'  ✗ 实验处理失败：{exc}')
    # AI 做题后写回 answers.json（保留原格式）
    if apply and answers_path and ai_configured():
        try:
            answers_path.write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'\n已把 AI 答案写回 {answers_path}。')
        except OSError as exc:
            print(f'\n⚠️ 写回 {answers_path} 失败：{exc}')
    print('\n===== 汇总 =====')
    for key, value in stats.items():
        print(f'  {key}: {value}')
    if not apply:
        print('\n这是 dry-run 预览，未真实提交。确认无误后加 --apply 真实提交。')
    return stats


def _print_task_keys(label, detail):
    game = detail.get('game') or {}
    challenge = detail.get('challenge') or {}
    print(f'{label}：status={detail.get("status")!r} message={detail.get("message")!r}')
    print(f'  game.identifier={game.get("identifier")!r} game.status={game.get("status")!r}')
    print(f'  challenge.subject={challenge.get("subject")!r} challenge.path={challenge.get("path")!r}')
    print(f'  homework_common_id={detail.get("homework_common_id")!r}')
    print(f'  prev_game={detail.get("prev_game")!r} next_game={detail.get("next_game")!r}')
    print(f'  chooses={len(detail.get("chooses") or [])}'
          f' myshixun={(detail.get("myshixun") or {}).get("identifier")!r}')


async def diagnose(answers_path, classroom_filter):
    """打印关键接口原始字段，用于确认关卡链解析方式，不做任何提交。"""
    answers = load_answers(answers_path)
    async with open_client() as client:
        for classroom in answers.get('classrooms', []):
            code = classroom.get('code')
            if classroom_filter and code != classroom_filter:
                continue
            experiments = classroom.get('experiments', [])
            if not experiments:
                continue
            experiment = experiments[0]
            print(f'== 课堂：{classroom.get("name")}（{code}）==')
            print(f'实验：{experiment.get("name")}')
            rows = await fetch_homework_rows(client, code)
            hw = match_homework(experiment.get('name'), rows)
            if hw is None:
                print('  ✗ 未匹配到 homework 行')
                return
            print('homework 行字段：')
            for key in ('homework_id', 'name', 'shixun_identifier', 'myshixun_identifier',
                        'challenge_count', 'finished_challenge_count', 'shixun_finished_status'):
                print(f'  {key} = {hw.get(key)!r}')

            shixun_id = hw.get('shixun_identifier')
            hw_id = hw.get('homework_id')
            if shixun_id and hw_id is not None:
                print('\nshixun_exec.json 响应（关键字段）：')
                try:
                    data = await client.get(
                        f'/api/shixuns/{shixun_id}/shixun_exec.json',
                        {'homework_common_id': hw_id}, strict_status=False)
                    print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
                    entry = data.get('game_identifier')
                    if entry:
                        print(f'\n入口 game_identifier={entry!r} 的任务详情：')
                        _print_task_keys('  ', await client.get(
                            f'/api/tasks/{entry}.json', {}, strict_status=False))
                except CollectionError as exc:
                    print(f'  ✗ shixun_exec 失败：{exc}')

            level = experiment.get('levels', [{}])[0]
            identifier = (level.get('identifiers') or [None])[0]
            print(f'\nanswers.json 第一个关卡：title={level.get("title")!r} identifier={identifier!r}')
            if identifier:
                print('用 answers.json 标识读任务详情：')
                _print_task_keys('  ', await client.get(
                    f'/api/tasks/{identifier}.json', {}, strict_status=False))
            return


def main():
    parser = argparse.ArgumentParser(description='根据 answers.json 自动提交头歌作业。')
    parser.add_argument('--apply', action='store_true', help='真实提交（默认 dry-run 只预览）。')
    parser.add_argument('--classroom', help='只处理指定课堂 code。')
    parser.add_argument('--limit', type=int, default=None, help='最多处理多少个关卡（用于测试）。')
    parser.add_argument('--poll-timeout', type=int, default=90, help='代码评测等待秒数。')
    parser.add_argument('--answers', default=str(DEFAULT_ANSWERS), help='answers.json 路径。')
    parser.add_argument('--diagnose', action='store_true', help='打印关键接口字段用于诊断，不提交。')
    parser.add_argument('--no-ai', action='store_true', help='缺答案时不用 AI 自动生成，直接跳过。')
    parser.add_argument('--delay', type=float, default=5.0, help='每个实验之间的等待秒数（避免环境启动过快）。')
    args = parser.parse_args()
    try:
        if args.diagnose:
            asyncio.run(diagnose(Path(args.answers), args.classroom))
        else:
            asyncio.run(run(args.apply, args.classroom, args.limit,
                            args.poll_timeout, Path(args.answers), use_ai=not args.no_ai,
                            delay=args.delay))
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('Playwright 请求失败，请检查网络；认证详情不写入日志。') from None


if __name__ == '__main__':
    main()
