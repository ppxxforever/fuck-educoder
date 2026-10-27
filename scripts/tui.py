"""Educoder 队列管理 TUI（纯标准库 curses，无需额外依赖）。

启动：
  uv run python scripts/tui.py

界面操作（方向键 / 字母键）：
  ↑ ↓     选择账号
  a       添加账号（输入账号，密码回显）
  d       删除选中账号
  v       验证选中账号密码
  r       运行队列（真实提交），运行时实时显示日志
  c       选择课程（多选，支持 code 或名称）
  f       切换「是否跳过已完成账号」
  g       切换账号间隔（30 分钟 / 10 分钟 / 不等待）
  L       查看队列汇总状态
  q       退出
"""
import curses
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

ACCOUNTS = ROOT / 'data' / 'accounts.json'
STATE = ROOT / 'data' / 'queue_state.json'
COURSES_CACHE = ROOT / 'data' / 'courses.json'
LOG = ROOT / 'data' / 'queue.log'
ENV_PATH = ROOT / '.env'

GAPS = [300, 600, 1800, 0]
GAP_LABELS = {300: '5 分钟', 600: '10 分钟', 1800: '30 分钟', 0: '不等待'}


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def save_json(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        tmp.chmod(mode)
    except OSError:
        pass
    tmp.replace(path)


def load_courses():
    """读取课堂列表：优先缓存，缺失时联网取一次。"""
    data = load_json(COURSES_CACHE, None)
    if isinstance(data, list) and data:
        return data
    try:
        from educoder_reminder.submit import fetch_homework_rows  # noqa: F401
        import asyncio
        from educoder_reminder.client import open_client
        from educoder_reminder.courses import fetch_courses

        async def _fetch():
            async with open_client() as client:
                return await fetch_courses(client)

        courses = asyncio.run(_fetch())
        rows = [{'identifier': c.identifier, 'name': c.name} for c in courses]
        save_json(COURSES_CACHE, rows)
        return rows
    except Exception:
        return []


class App:
    def __init__(self):
        self.accounts = load_json(ACCOUNTS, [])
        self.state = load_json(STATE, {})
        self.courses = []
        self.selected_courses = []      # 空 = 全部课程
        self.cursor = 0
        self.skip_done = True
        self.gap = 300
        self.message = ''
        self.running = False
        self.log_lines = []
        self.log_offset = 0
        self.proc = None
        self.scroll = 0

    # ---------- 数据 ----------
    def reload(self):
        self.accounts = load_json(ACCOUNTS, [])
        self.state = load_json(STATE, {})

    def save_accounts(self):
        save_json(ACCOUNTS, self.accounts)

    def status_of(self, acc):
        return self.state.get(acc, {}).get('status', 'pending')

    def progress_of(self, acc):
        st = self.state.get(acc, {})
        if st.get('status') == 'done':
            return f"提交{st.get('submitted', 0)} 失败{st.get('failed', 0)} 跳过{st.get('skipped_passed', 0)}"
        if st.get('status') in ('failed', 'invalid'):
            return (st.get('error') or '')[:40]
        return '-'

    # ---------- 日志 ----------
    def read_new_log(self):
        if not LOG.exists():
            return
        try:
            size = LOG.stat().st_size
            if size < self.log_offset:
                self.log_offset = 0
                self.log_lines = []
            if size == self.log_offset:
                return
            with LOG.open('r', encoding='utf-8', errors='replace') as f:
                f.seek(self.log_offset)
                chunk = f.read()
                self.log_offset = f.tell()
            for line in chunk.splitlines():
                self.log_lines.append(line.rstrip())
            self.log_lines = self.log_lines[-4000:]
        except OSError:
            pass

    # ---------- 绘制 ----------
    def draw(self, stdscr):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        if self.running:
            self.draw_run(stdscr, h, w)
            return
        title = ' Educoder 队列管理 '
        try:
            stdscr.addstr(0, 0, title.center(w, '═'), curses.A_BOLD)
        except curses.error:
            pass

        # 账号表
        head = f'{"":2}{"账号":<15}{"备注":<10}{"状态":<9}进度'
        self._put(stdscr, 2, 0, head, curses.A_UNDERLINE)
        for i, a in enumerate(self.accounts):
            acc = a.get('account', '')
            mark = '▶' if i == self.cursor else ' '
            line = f'{mark} {acc:<15}{(a.get("note") or "")[:8]:<10}{self.status_of(acc):<9}{self.progress_of(acc)}'
            attr = curses.A_REVERSE if i == self.cursor else 0
            self._put(stdscr, 3 + i, 0, line[:w - 1], attr)
        if not self.accounts:
            self._put(stdscr, 4, 2, '（队列为空，按 a 添加账号）', curses.A_DIM)

        row = 4 + max(len(self.accounts), 1)
        self._put(stdscr, row, 0, '─' * (w - 1), curses.A_DIM)
        courses = '全部课程' if not self.selected_courses else '、'.join(self.selected_courses)
        self._put(stdscr, row + 1, 1, f'课程筛选：{courses}'[:w - 2])
        self._put(stdscr, row + 2, 1,
                  f'跳过已完成：{"是" if self.skip_done else "否"}    '
                  f'账号间隔：{GAP_LABELS.get(self.gap, str(self.gap))}'[:w - 2])

        keys = '[a]添加 [d]删除 [v]验证  [r]运行  [c]选课程  [f]切换跳过  [g]切换间隔  [L]汇总  [q]退出'
        self._put(stdscr, h - 2, 0, keys[:w - 1], curses.A_REVERSE)
        if self.message:
            self._put(stdscr, h - 1, 0, self.message[:w - 1])
        stdscr.refresh()

    def draw_run(self, stdscr, h, w):
        self.read_new_log()
        self._put(stdscr, 0, 0, ' 运行中（按 q 中止并返回） '.center(w, '═'), curses.A_BOLD)
        body_h = h - 3
        lines = self.log_lines
        total = len(lines)
        if self.scroll == 0:
            shown = lines[-body_h:]
        else:
            start = max(0, total - body_h - self.scroll)
            shown = lines[start:start + body_h]
        for i, line in enumerate(shown):
            self._put(stdscr, 1 + i, 0, line[:w - 1])
        alive = self.proc is not None and self.proc.poll() is None
        tail = '运行中…' if alive else '已结束'
        self._put(stdscr, h - 2, 0,
                  f'{tail}  ↑↓/PgUp/PgDn 滚动  q 返回 '.ljust(w - 1)[:w - 1], curses.A_REVERSE)
        stdscr.refresh()

    @staticmethod
    def _put(stdscr, y, x, text, attr=0):
        try:
            stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass

    # ---------- 交互 ----------
    def prompt(self, stdscr, label, secret=False, default=''):
        h, w = stdscr.getmaxyx()
        curses.echo()
        try:
            stdscr.addstr(h - 1, 0, ' ' * (w - 1))
            stdscr.addstr(h - 1, 0, label[:w - len(default) - 2])
            if default:
                stdscr.addstr(h - 1, len(label), default)
            stdscr.refresh()
            raw = stdscr.getstr(h - 1, len(label), 60)
            return raw.decode('utf-8', 'replace').strip()
        except (curses.error, KeyboardInterrupt):
            return ''
        finally:
            curses.noecho()

    def add_account(self, stdscr):
        acc = self.prompt(stdscr, '账号（手机号/邮箱/用户名）: ')
        if not acc:
            self.message = '已取消'
            return
        if any(a.get('account') == acc for a in self.accounts):
            self.message = f'账号 {acc} 已存在'
            return
        pwd = self.prompt(stdscr, '密码（会回显）: ')
        if not pwd:
            self.message = '密码为空，已取消'
            return
        self.accounts.append({'account': acc, 'password': pwd, 'note': ''})
        self.save_accounts()
        self.message = f'已添加 {acc}'
        self.cursor = len(self.accounts) - 1

    def delete_account(self, stdscr):
        if not self.accounts:
            return
        acc = self.accounts[self.cursor].get('account')
        h, w = stdscr.getmaxyx()
        self._put(stdscr, h - 1, 0, f'删除 {acc}？(y/N) ')
        stdscr.refresh()
        try:
            ch = stdscr.getkey()
        except curses.error:
            return
        if ch.lower() == 'y':
            del self.accounts[self.cursor]
            self.cursor = max(0, self.cursor - 1)
            self.save_accounts()
            self.message = f'已删除 {acc}'

    def run_verify(self, stdscr):
        if not self.accounts:
            self.message = '队列为空'
            return
        acc = self.accounts[self.cursor].get('account')
        self.message = f'正在验证 {acc}…'
        self.draw(stdscr)
        curses.endwin()
        try:
            subprocess.run([sys.executable, '-u', str(ROOT / 'scripts' / 'verify_accounts.py'),
                            '--only', acc, '--clear-limit'], cwd=str(ROOT))
        except Exception as exc:
            self.message = f'验证失败：{exc}'
        input('\n回车返回…')
        stdscr.refresh()

    def choose_courses(self, stdscr):
        if not self.courses:
            self.message = '正在获取课程列表…'
            self.draw(stdscr)
            self.courses = load_courses()
        if not self.courses:
            self.message = '获取课程失败，请先运行 educoder_reminder.courses'
            return
        picks = set(self.selected_courses)
        idx = 0
        while True:
            h, w = stdscr.getmaxyx()
            stdscr.erase()
            self._put(stdscr, 0, 0, ' 选择课程（空格切换，回车确认，q 取消） '.center(w, '═'), curses.A_BOLD)
            self._put(stdscr, 2, 1, '按回车不选任何课程 = 处理全部课程', curses.A_DIM)
            for i, c in enumerate(self.courses):
                key = c.get('identifier') or ''
                name = c.get('name') or ''
                checked = '[x]' if key in picks else '[ ]'
                line = f'{checked} {key:<14}{name}'
                attr = curses.A_REVERSE if i == idx else 0
                self._put(stdscr, 3 + i, 1, line[:w - 2], attr)
            stdscr.refresh()
            try:
                ch = stdscr.getch()
            except curses.error:
                continue
            if ch in (curses.KEY_UP, ord('k')):
                idx = max(0, idx - 1)
            elif ch in (curses.KEY_DOWN, ord('j')):
                idx = min(len(self.courses) - 1, idx + 1)
            elif ch == ord(' '):
                key = self.courses[idx].get('identifier')
                picks.symmetric_difference_update({key})
            elif ch in (10, 13, curses.KEY_ENTER):
                self.selected_courses = sorted(picks)
                self.message = ('课程：' + '、'.join(self.selected_courses)) if picks else '课程：全部'
                return
            elif ch in (ord('q'), 27):
                return

    def start_run(self, stdscr):
        if not self.accounts:
            self.message = '队列为空'
            return
        cmd = [sys.executable, '-u', str(ROOT / 'scripts' / 'run_queue.py'), '--apply',
               '--gap', str(self.gap)]
        if self.skip_done:
            pass  # run_queue 默认跳过已完成
        else:
            cmd.append('--force')
        for c in self.selected_courses:
            cmd.extend(['--classroom', c])
        LOG.parent.mkdir(parents=True, exist_ok=True)
        logf = LOG.open('a', encoding='utf-8')
        logf.write(f'\n\n===== TUI 启动 {time.strftime("%Y-%m-%d %H:%M:%S")} =====\n')
        logf.flush()
        self.log_offset = LOG.stat().st_size
        self.log_lines = []
        self.scroll = 0
        self.proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=logf,
                                     stderr=subprocess.STDOUT, text=True)
        self.running = True

    # ---------- 主循环 ----------
    def loop(self, stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.timeout(500)
        self.courses = load_courses()
        while True:
            try:
                self.draw(stdscr)
            except curses.error:
                pass
            if self.running:
                if self.proc is not None and self.proc.poll() is not None:
                    self.running = False
                    self.reload()
                    self.message = '队列已结束'
                try:
                    ch = stdscr.getch()
                except curses.error:
                    continue
                if ch == ord('q'):
                    if self.proc and self.proc.poll() is None:
                        self.proc.terminate()
                    self.running = False
                    self.reload()
                    self.message = '已中止'
                elif ch == curses.KEY_UP:
                    self.scroll += 1
                elif ch == curses.KEY_DOWN:
                    self.scroll = max(0, self.scroll - 1)
                elif ch == curses.KEY_PPAGE:
                    self.scroll += 10
                elif ch == curses.KEY_NPAGE:
                    self.scroll = max(0, self.scroll - 10)
                elif ch in (ord('G'), curses.KEY_END):
                    self.scroll = 0
                continue

            try:
                ch = stdscr.getch()
            except curses.error:
                continue
            if ch == -1:
                continue
            if ch in (ord('q'), 27):
                return
            if ch == curses.KEY_UP:
                self.cursor = max(0, self.cursor - 1)
            elif ch == curses.KEY_DOWN:
                self.cursor = min(max(0, len(self.accounts) - 1), self.cursor + 1)
            elif ch == ord('a'):
                cursed_end(stdscr)
                self.add_account(stdscr)
            elif ch == ord('d'):
                self.delete_account(stdscr)
            elif ch == ord('v'):
                self.run_verify(stdscr)
            elif ch == ord('r'):
                self.start_run(stdscr)
            elif ch == ord('c'):
                self.choose_courses(stdscr)
            elif ch == ord('f'):
                self.skip_done = not self.skip_done
                self.message = f'跳过已完成：{"是" if self.skip_done else "否"}'
            elif ch == ord('g'):
                i = GAPS.index(self.gap) if self.gap in GAPS else 2
                self.gap = GAPS[(i + 1) % len(GAPS)]
                self.message = f'账号间隔：{GAP_LABELS[self.gap]}'
            elif ch == ord('L'):
                curses.endwin()
                subprocess.run([sys.executable, str(ROOT / 'scripts' / 'queue_status.py')],
                               cwd=str(ROOT))
                input('\n回车返回…')
                stdscr.refresh()
            elif ch == ord('R'):
                self.reload()
                self.message = '已刷新'


def cursed_end(stdscr):
    """进入输入前确保光标可用。"""
    try:
        curses.curs_set(1)
        stdscr.refresh()
    except curses.error:
        pass


def main():
    if not sys.stdout.isatty():
        raise SystemExit('TUI 需要交互终端（TTY）。请直接在终端里运行。')
    (ROOT / 'data').mkdir(mode=0o700, exist_ok=True)
    app = App()
    try:
        curses.wrapper(app.loop)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
