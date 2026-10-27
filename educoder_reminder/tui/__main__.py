"""入口：uv run python -m educoder_reminder.tui [--dump]"""
from __future__ import annotations

import argparse

from . import data


def dump() -> None:
    """无界面模式：打印本地状态摘要，便于服务器上核对或脚本调用。"""
    feed = data.summarize_feeds()
    session = feed['session']
    print('=' * 68)
    print('Educoder 控制台 · 本地状态摘要（不联网）')
    print('=' * 68)
    print(f'当前账号      : {session["account"] or "（未配置）"}')
    print(f'会话          : {"Token/Cookie 已缓存" if session["session_ready"] else "需要密码登录"}')
    print(f'AI            : {session["ai_model"] or "已配置" if session["ai_configured"] else "未配置"}')
    print(f'推送 SendKey  : {"已配置" if session["sendkey"] else "未配置"}')
    if session['cooldown']:
        print(f'登录冷却      : 还需 {session["cooldown"] // 60} 分 {session["cooldown"] % 60} 秒')
    latest = feed['latest_username']
    synced = feed['sync_times'].get(latest)
    print(f'最近同步      : {data.human_age(synced) if synced else "无记录"}'
          + (f'（{latest}）' if latest else ''))
    print(f'进行中课堂    : {len(feed["courses"])} 个')
    queue = feed['queue']
    print(f'账号队列      : {queue["total"]} 个（完成 {queue["done"]} / '
          f'失败 {queue["failed"]} / 待处理 {queue["pending"]}）')
    for row in data.queue_rows():
        courses = '、'.join(row.get('classrooms') or []) or '全部'
        note = f'（{row["note"]}）' if row.get('note') else ''
        print(f'  - {row["account"]:<16}{note:<8}课程：{courses}')

    homeworks = feed['homeworks']
    counts = homeworks['counts']
    print(f'作业          : 共 {homeworks["total"]} 项 · '
          + ' · '.join(f'{data.STATE_LABELS[k]} {counts[k]}'
                       for k in ('pending', 'overdue', 'no_deadline', 'completed')))
    print(f'提醒窗口      : 24h 内 {homeworks["urgent_24h"]} 项 / '
          f'1h 内 {homeworks["urgent_1h"]} 项')

    rows = [r for r in data.homework_rows() if r['state'] in ('pending', 'overdue')]
    if rows:
        print()
        print(f'{"课堂":<22}{"类型":<10}{"作业":<30}{"截止":<14}{"状态":<8}剩余')
        print('-' * 100)
        for row in rows[:20]:
            print(f'{row["course_name"][:20]:<22}{row["kind_name"]:<10}'
                  f'{row["name"][:28]:<30}{row["deadline_text"]:<14}'
                  f'{row["state_label"]:<8}{row["remaining"]}')
        if len(rows) > 20:
            print(f'… 其余 {len(rows) - 20} 项省略')
    print('\n启动界面：uv run python -m educoder_reminder.tui')


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='python -m educoder_reminder.tui',
        description='Educoder 控制台 TUI（Textual）')
    parser.add_argument('--dump', action='store_true',
                        help='打印本地状态摘要后退出（不启动界面、不联网）')
    args = parser.parse_args()
    if args.dump:
        dump()
        return
    from .app import EducoderTUI
    EducoderTUI().run()


if __name__ == '__main__':
    main()
