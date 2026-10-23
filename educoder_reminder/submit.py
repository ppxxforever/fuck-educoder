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
import json
import re
import time
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

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
        return 'dry-run'

    resp = await client.post(f'/api/tasks/{identifier}/choose_build.json', {}, payload)
    correct = resp.get('choose_correct_num', 0)
    total = resp.get('challenge_chooses_count', len(answers))
    if total > 0 and correct == total:
        stats['submitted'] += 1
        print(f'      选择题 {identifier}：{correct}/{total} 正确 ✔')
        return 'ok'

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
            return 'ok-fallback'
        stats['failed'] += 1
        print(f'      选择题 {identifier}：重交后仍只对 {correct2}/{total2}，请人工核对。')
        return 'failed'

    stats['failed'] += 1
    print(f'      选择题 {identifier}：提交 {correct}/{total}，且响应未回吐完整答案键。')
    return 'failed'


async def wait_for_verdict(client, identifier, timeout=90, poll=2):
    deadline = time.monotonic() + timeout
    last_detail = None
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
        tests = detail.get('test_sets') or []
        rated = [t for t in tests if t.get('result') is not None]
        if tests and len(rated) == len(tests):
            return all(bool(t.get('result')) for t in tests), detail
    return None, last_detail


async def submit_choice_game(client, gid, level, detail, level_idx, offsets, apply, stats):
    """提交一个选择题关卡（level 可能对应多个 game，按 chooses 数量切分答案）。"""
    items = sorted(level['answer'], key=lambda x: x.get('number', 0))
    full = [reconstruct_selected(item.get('selected', [])) for item in items]
    if not full:
        stats['skipped_no_answer'] += 1
        return False
    count = len(detail.get('chooses') or [])
    offset = offsets.get(level_idx, 0)
    answers = full[offset:offset + count]
    offsets[level_idx] = offset + count
    challenge_id = (detail.get('challenge') or {}).get('id')
    subject_id = detail.get('subject_id')
    status = await submit_choice(client, gid, answers, challenge_id, subject_id, apply, stats)
    return status in ('ok', 'ok-fallback')


async def submit_code_game(client, hw_id, gid, level, detail, apply, stats, poll_timeout):
    """提交一个代码关卡；返回是否评测通过。"""
    answer = level['answer']
    code = answer.get('code') if isinstance(answer, dict) else None
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
    passed, _ = await wait_for_verdict(client, gid, timeout=poll_timeout)
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


async def process_experiment(client, hw_row, experiment, apply, stats, poll_timeout, limit=None):
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
        if level_idx is None:
            stats['skipped_error'] += 1
            print(f'      [跳过] {subject}（{gid}）：answers.json 无对应关卡。')
        else:
            level = levels[level_idx]
            ordinal = consumed.get(level_idx, 0) + 1
            consumed[level_idx] = ordinal
            stats['processed'] = stats.get('processed', 0) + 1
            if not level.get('answered'):
                stats['skipped_no_answer'] += 1
                print(f'      - [跳过] {subject}：answers.json 未记录答案。')
            elif game.get('status') == 2:
                stats['skipped_passed'] += 1
                print(f'      [跳过] {subject}：已通过。')
            else:
                try:
                    if level.get('kind') == 'choice':
                        mutated = await submit_choice_game(
                            client, gid, level, detail, level_idx, offsets, apply, stats)
                    elif level.get('kind') == 'code':
                        mutated = await submit_code_game(
                            client, hw_id, gid, level, detail, apply, stats, poll_timeout)
                    else:
                        stats['skipped_error'] += 1
                        print(f'      - [跳过] {subject}：未知类型 {level.get("kind")}。')
                        mutated = False
                except CollectionError as exc:
                    stats['failed'] += 1
                    print(f'      ✗ {subject}：{exc}')
                    mutated = False
                if mutated:
                    # 通过后 next_game 才会出现，重读一次以继续遍历。
                    cache.pop(gid, None)
                    detail = await _detail_of(client, cache, gid)

        nxt = detail.get('next_game')
        if nxt and str(nxt) not in seen:
            seen.add(str(nxt))
            queue.append(str(nxt))


async def run(apply, classroom_filter, limit, poll_timeout, answers_path):
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
            for experiment in classroom.get('experiments', []):
                hw = match_homework(experiment.get('name'), rows)
                if hw is None:
                    stats['skipped_error'] += len(experiment.get('levels', []))
                    print(f'  ✗ 实验「{experiment.get("name")}」未在课堂列表中找到，跳过。')
                    continue
                if hw.get('shixun_finished_status') == 1:
                    stats['skipped_passed'] += len(experiment.get('levels', []))
                    print(f'  - [跳过] 实验已完成：{experiment.get("name")}')
                    continue
                print(f'  ▸ 实验：{experiment.get("name")}（homework_id={hw.get("homework_id")}）')
                try:
                    await process_experiment(client, hw, experiment, apply, stats,
                                             poll_timeout, limit=limit)
                except CollectionError as exc:
                    stats['skipped_error'] += len(experiment.get('levels', []))
                    print(f'  ✗ 实验处理失败：{exc}')
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
    args = parser.parse_args()
    try:
        if args.diagnose:
            asyncio.run(diagnose(Path(args.answers), args.classroom))
        else:
            asyncio.run(run(args.apply, args.classroom, args.limit,
                            args.poll_timeout, Path(args.answers)))
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('Playwright 请求失败，请检查网络；认证详情不写入日志。') from None


if __name__ == '__main__':
    main()
