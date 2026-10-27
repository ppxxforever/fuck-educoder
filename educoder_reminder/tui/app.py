"""Educoder 控制台 TUI（Textual）。

启动：
  uv run python -m educoder_reminder.tui

界面全部使用 `[按键] 动作` 形式的文本操作条（可鼠标点击，也可按对应按键），
不使用按钮控件。每个账号可以单独指定要刷哪些课堂。

分页与按键：
  概览        [r] 刷新  [c] 同步课堂  [h] 同步作业  [p] 提醒预览  [k] 校验配置  [a] 认证检查
              [P] 爬题预览  [G] 预生成答案
  课堂·作业   [/] 搜索  [o] 打开选中作业  [r] 刷新
  多账号队列  [u] 设为当前  [v] 验证密码  [g] 选择课程  [s] 提交选中账号
              [b] 全部开始提交  [m] 显示密码  [d] 删除  [e] 保存到队列
  执行任务    [n] 禁用 AI  [l] 先释放环境 pod  [F5] 运行  [x] 停止任务
              [P] 爬题预览  [G] 预生成答案
  实时日志    [r] 刷新  [f] 跟随最新  [y] 清空视图
  全局        1-5 切换分页  Ctrl+R 刷新  Ctrl+S 停止  F1 帮助  Ctrl+Q 退出

设计原则：
  - 所有联网/提交/推送都通过子进程调用现有 CLI，界面进程不跑 Playwright；
  - 真实提交和推送必须二次确认（红色弹窗）；
  - 视图只读本地数据，刷新不会触发网络请求；
  - 每个账号的课堂筛选保存在 data/accounts.json 的 classrooms 字段。
"""
from __future__ import annotations

import webbrowser
from pathlib import Path

from rich.cells import cell_len
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable, Footer, Header, Input, RichLog, Select, Static, TabbedContent,
    TabPane,
)

from . import data
from .runner import (
    CLASSROOM_TASKS, EXPERIMENT_TASKS, GAP_TASKS, LIMIT_TASKS,
    NO_AI_TASKS, PY, RELEASE_TASKS, SCRIPTS, TASK_ORDER, TASKS, TIMEOUT_TASKS,
    Options, build_command, command_display, spawn,
)

STATE_OPTIONS = [('全部状态', 'all')] + [
    (label, key) for key, label in data.STATE_LABELS.items()
]
KIND_OPTIONS = [('全部类型', 'all'), ('课堂实验', '4'), ('图文作业', '1')]
LOG_OPTIONS = [('队列日志 data/queue.log', 'queue'), ('TUI 日志 data/tui.log', 'tui')]


# --------------------------------------------------------------------------- #
# `[按键] 动作` 文本操作条
# --------------------------------------------------------------------------- #
def option(key: str, label: str, action: str, *, on: bool | None = None,
           enabled: bool = True) -> str:
    """生成一段可点击的操作文本，例如 `[r] 刷新`。

    action 传完整目标，如 `app.refresh_current` 或 `screen.cancel`。
    on 不为 None 时额外显示 `[x]` / `[ ]` 开关标记。
    """
    head = f'\\[{key}]'
    if on is not None:
        head += f' \\[{"x" if on else " "}]'
    body = f'[b]{head}[/b] {label}'
    if not enabled:
        return f'[dim]{body}[/dim]'
    return f'[@click={action}]{body}[/]'


def options(*items: str) -> str:
    return '   '.join(items)


def bar(*items: tuple) -> str:
    """每项为 (key, label, action) 或 (key, label, action, on)。"""
    rendered = []
    for item in items:
        key, label, action = item[0], item[1], item[2]
        on = item[3] if len(item) > 3 else None
        rendered.append(option(key, label, action, on=on))
    return options(*rendered)


def _clip(text: str, limit: int) -> str:
    """按终端显示宽度截断（中文算 2 格），超出部分用 … 收尾。"""
    text = str(text)
    if cell_len(text) <= limit:
        return text
    out = ''
    for char in text:
        if cell_len(out + char) > limit - 1:
            break
        out += char
    return out + '…'


class ConfirmScreen(ModalScreen[bool]):
    """二次确认弹窗：真实提交 / 推送 / 批量操作。"""

    BINDINGS = [
        Binding('escape', 'cancel', '取消', show=False),
        Binding('n', 'cancel', '取消', show=False),
        Binding('y', 'confirm', '确认', show=False),
        Binding('enter', 'confirm', '确认', show=False),
    ]

    def __init__(self, title: str, body: str, command: str = '',
                 confirm_label: str = '确认执行', danger: bool = False) -> None:
        super().__init__()
        self.title_text = title
        self.body_text = body
        self.command = command
        self.confirm_label = confirm_label
        self.danger = danger

    def compose(self) -> ComposeResult:
        with Vertical(id='confirm-box'):
            yield Static(self.title_text, classes='modal-title')
            yield Static(self.body_text, classes='modal-body')
            if self.command:
                yield Static('命令：' + self.command, classes='modal-command')
            yield Static(
                bar(('y', self.confirm_label, 'screen.confirm'),
                    ('n', '取消', 'screen.cancel')),
                id='confirm-actions', classes='action-bar')

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class StatusScreen(ModalScreen[str | None]):
    """手动设置某个账号的队列状态。"""

    BINDINGS = [
        Binding('escape', 'cancel', '取消', show=False),
        Binding('p', 'pending', '待处理', show=False),
        Binding('d', 'done', '已完成', show=False),
        Binding('f', 'failed', '失败', show=False),
        Binding('z', 'reset', '清空进度', show=False),
    ]

    def __init__(self, account: str, status: str) -> None:
        super().__init__()
        self.account = account
        self.status = status

    def compose(self) -> ComposeResult:
        with Vertical(id='status-box'):
            yield Static(f'设置队列状态：{self.account}', classes='modal-title')
            yield Static('当前状态：' + data.QUEUE_STATUS_LABELS.get(
                self.status, self.status), classes='modal-body')
            yield Static(bar(
                ('p', '待处理', 'screen.pending'),
                ('d', '已完成', 'screen.done'),
                ('f', '失败', 'screen.failed'),
                ('z', '清空进度', 'screen.reset'),
                ('esc', '取消', 'screen.cancel'),
            ), id='status-actions', classes='action-bar')
            yield Static('待处理 = 重新进入队列；已完成 = run_queue 默认跳过；'
                         '清空进度 = 待处理并清零提交/失败计数。\n'
                         '只修改本地 data/queue_state.json，不改变平台作业状态。',
                         classes='muted')

    def action_pending(self) -> None:
        self.dismiss('pending')

    def action_done(self) -> None:
        self.dismiss('done')

    def action_failed(self) -> None:
        self.dismiss('failed')

    def action_reset(self) -> None:
        self.dismiss('reset')

    def action_cancel(self) -> None:
        self.dismiss(None)


class CoursePickerScreen(ModalScreen[list[str] | None]):
    """为某个账号勾选要刷的课堂。空格切换，回车保存，a 全选，n 清空。"""

    BINDINGS = [
        Binding('space', 'toggle', '选择', show=False),
        Binding('escape', 'cancel', '取消', show=False),
        Binding('a', 'all', '全选', show=False),
        Binding('n', 'none', '清空', show=False),
        Binding('s', 'save', '保存', show=False),
    ]

    def __init__(self, account: str, selected: list[str]) -> None:
        super().__init__()
        self.account = account
        self.selected = list(selected)
        self.keys: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id='picker-box'):
            yield Static(f'为 {self.account} 选择课堂', classes='modal-title')
            yield Static('空格/回车 切换选中 · a 全选 · n 清空 · s 保存 · esc 取消',
                         classes='muted')
            yield DataTable(id='picker-table', cursor_type='row', zebra_stripes=True)
            yield Static('', id='picker-footer', classes='muted')
            yield Static(bar(
                ('space', '选择/取消', 'screen.toggle'),
                ('a', '全选', 'screen.all'),
                ('n', '清空', 'screen.none'),
                ('s', '保存', 'screen.save'),
                ('esc', '取消', 'screen.cancel'),
            ), id='picker-actions', classes='action-bar')

    def on_mount(self) -> None:
        table = self.query_one('#picker-table', DataTable)
        table.add_column('选', key='pick', width=4)
        table.add_column('课程 code', width=16)
        table.add_column('课程名称', width=44)
        courses = data.courses()
        cached = set()
        for course in courses:
            identifier = str(course.get('identifier') or '')
            if not identifier:
                continue
            cached.add(identifier)
            table.add_row(self._mark(identifier), identifier,
                          str(course.get('name') or ''), key=identifier)
            self.keys.append(identifier)
        for identifier in self.selected:
            if identifier in cached:
                continue
            table.add_row(self._mark(identifier), identifier,
                          '（不在课堂缓存中，按原值匹配）', key=identifier)
            self.keys.append(identifier)
        if not self.keys:
            self.query_one('#picker-footer', Static).update(
                '课堂缓存为空：先回「概览」按 [c] 同步课堂；'
                '也可以直接关闭本窗口，在右侧输入课程 code 保存。')
        else:
            table.focus()
        self._update_footer()

    def _mark(self, identifier: str) -> str:
        return '[x]' if identifier in self.selected else '[ ]'

    def _update_footer(self) -> None:
        if not self.keys:
            return
        chosen = [key for key in self.keys if key in self.selected]
        text = '、'.join(chosen) if chosen else '（未选择，保存后该账号处理全部课堂）'
        self.query_one('#picker-footer', Static).update(f'已选 {len(chosen)} 个：{text}')

    def _current_key(self) -> str | None:
        table = self.query_one('#picker-table', DataTable)
        if not self.keys or table.cursor_row is None:
            return None
        index = table.cursor_row
        return self.keys[index] if 0 <= index < len(self.keys) else None

    def _toggle(self, identifier: str) -> None:
        if identifier in self.selected:
            self.selected.remove(identifier)
        else:
            self.selected.append(identifier)
        table = self.query_one('#picker-table', DataTable)
        table.update_cell(identifier, 'pick', self._mark(identifier))
        self._update_footer()

    def action_toggle(self) -> None:
        key = self._current_key()
        if key:
            self._toggle(key)

    @on(DataTable.RowSelected, '#picker-table')
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        if key:
            self._toggle(str(key))

    def action_all(self) -> None:
        for key in self.keys:
            if key not in self.selected:
                self.selected.append(key)
            self.query_one('#picker-table', DataTable).update_cell(key, 'pick', '[x]')
        self._update_footer()

    def action_none(self) -> None:
        self.selected.clear()
        for key in self.keys:
            self.query_one('#picker-table', DataTable).update_cell(key, 'pick', '[ ]')
        self._update_footer()

    def action_save(self) -> None:
        ordered = [key for key in self.keys if key in self.selected]
        self.dismiss(ordered)

    def action_cancel(self) -> None:
        self.dismiss(None)


class EducoderTUI(App):
    TITLE = 'Educoder 控制台'
    SUB_TITLE = '作业提醒 · 自动提交 · 多账号队列'

    CSS = """
    Screen { background: $surface; }

    TabbedContent { height: 1fr; }
    TabPane { height: 1fr; padding: 0 1; }

    .card {
        border: round $primary;
        padding: 1 2;
        height: auto;
    }
    .card-title {
        text-style: bold;
        color: $accent;
    }
    .muted { color: $text-muted; }
    .mono { color: $text-muted; }

    .action-bar {
        height: auto;
        color: $text;
        padding: 0 0 0 1;
    }

    /* 概览 */
    #overview-grid { height: auto; }
    #session-card { width: 1fr; }
    #stats-card { width: 1fr; }
    #todo-card { height: 1fr; margin-top: 1; }
    #todo-table { height: 1fr; }
    #overview-actions { height: auto; padding: 1 0 0 1; }

    /* 课堂/作业 */
    #hw-toolbar { height: auto; }
    #hw-search { width: 1fr; }
    #hw-toolbar Select { width: 24; margin-left: 1; }
    #hw-actions { height: auto; padding: 1 0; }
    #hw-table { height: 1fr; }
    #hw-footer { height: auto; padding: 0 1; color: $text-muted; }

    /* 队列 */
    #queue-body { height: 1fr; }
    #queue-list { width: 3fr; height: 1fr; }
    #queue-add { width: 1fr; height: 1fr; margin-left: 1; }
    #queue-table { height: 1fr; }
    #queue-actions { height: auto; padding: 1 0 0 1; }
    #queue-add Input { margin-bottom: 1; }
    #queue-form-actions { height: auto; padding: 1 0; }
    #queue-session { height: auto; padding-top: 1; color: $text-muted; }

    /* 任务 */
    #task-pane { height: 1fr; }
    #task-row1, #task-row2 { height: auto; }
    #task-row1 Select { width: 38; }
    #task-row1 Input, #task-row2 Input { width: 1fr; margin-left: 1; }
    #task-controls { height: auto; padding: 1 0 0 0; }
    #task-toggles { width: auto; height: 1; }
    #task-actions { width: auto; height: 1; padding-left: 3; }
    #task-status { width: 1fr; height: 1; content-align: left middle; color: $text-muted;
                   padding-left: 2; }
    #task-hint { height: auto; color: $text-muted; padding-bottom: 1; }
    #task-log { height: 1fr; border: round $primary; }

    /* 日志 */
    #log-pane { height: 1fr; }
    #log-toolbar { height: auto; }
    #log-toolbar Select { width: 34; }
    #log-actions { width: 1fr; height: 3; content-align: right middle; }
    #log-view { height: 1fr; border: round $primary; margin-top: 1; }

    /* 选择课程弹窗 */
    CoursePickerScreen { align: center middle; }
    #picker-box {
        width: 100;
        height: 80%;
        border: thick $accent;
        background: $panel;
        padding: 1 2;
    }
    #picker-table { height: 1fr; }
    #picker-footer { height: auto; padding-top: 1; }
    #picker-actions { height: auto; padding-top: 1; }

    /* 状态设置弹窗 */
    StatusScreen { align: center middle; }
    #status-box {
        width: 100;
        height: auto;
        border: thick $accent;
        background: $panel;
        padding: 1 2;
    }
    #status-actions { height: auto; padding-top: 1; }

    /* 确认弹窗 */
    ConfirmScreen { align: center middle; }
    #confirm-box {
        width: 90;
        height: auto;
        border: thick $error;
        background: $panel;
        padding: 1 2;
    }
    .modal-title { text-style: bold; color: $error; padding-bottom: 1; }
    .modal-body { padding-bottom: 1; }
    .modal-command {
        color: $text-muted;
        border: round $primary;
        padding: 0 1;
        margin-bottom: 1;
    }
    #confirm-actions { height: auto; padding-top: 1; content-align: right middle; }
    """

    BINDINGS = [
        Binding('ctrl+q', 'quit_app', '退出'),
        Binding('r', 'refresh_current', '刷新'),
        Binding('ctrl+r', 'refresh_current', '刷新', show=False),
        Binding('ctrl+s', 'stop_task', '停止任务'),
        Binding('f1', 'shortcuts', '快捷键'),
        # 分页
        Binding('1', 'tab_overview', '概览', show=False),
        Binding('2', 'tab_homework', '课堂·作业', show=False),
        Binding('3', 'tab_queue', '多账号队列', show=False),
        Binding('4', 'tab_tasks', '执行任务', show=False),
        Binding('5', 'tab_log', '实时日志', show=False),
        # 概览
        Binding('c', 'sync_courses', '同步课堂', show=False),
        Binding('h', 'sync_homeworks', '同步作业', show=False),
        Binding('p', 'preview_remind', '提醒预览', show=False),
        Binding('k', 'check_config', '校验配置', show=False),
        Binding('a', 'auth_check', '认证检查', show=False),
        Binding('P', 'prepare_preview', '爬题预览', show=False),
        Binding('G', 'prepare_generate', '预生成答案', show=False),
        # 作业
        Binding('slash', 'focus_search', '搜索', show=False),
        Binding('o', 'open_link', '打开作业', show=False),
        # 队列
        Binding('u', 'activate_account', '设为当前', show=False),
        Binding('v', 'verify_account', '验证密码', show=False),
        Binding('i', 'edit_account', '修改账号信息', show=False),
        Binding('t', 'set_status', '设置状态', show=False),
        Binding('escape', 'cancel_account_edit', '取消编辑', show=False),
        Binding('g', 'pick_courses', '选择课程', show=False),
        Binding('s', 'submit_selected', '提交选中账号', show=False),
        Binding('b', 'submit_all_accounts', '全部开始提交', show=False),
        Binding('m', 'toggle_passwords', '显示密码', show=False),
        Binding('d', 'delete_account', '删除账号', show=False),
        Binding('e', 'save_account', '保存到队列', show=False),
        # 任务
        Binding('n', 'toggle_noai', '禁用 AI', show=False),
        Binding('l', 'toggle_release', '释放环境 pod', show=False),
        Binding('f5', 'run_task', '运行任务', show=False),
        Binding('x', 'stop_task', '停止任务', show=False),
        # 日志
        Binding('f', 'toggle_follow', '跟随最新', show=False),
        Binding('y', 'clear_log', '清空视图', show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.hw_rows: list[dict] = []
        self.hw_visible: list[dict] = []
        self.todo_rows: list[dict] = []
        self.queue_rows: list[dict] = []
        self.selected_account: str = ''
        self.reveal_passwords = False
        self.editing_account = ''
        self.no_ai = False
        self.release_pods = False
        self.log_follow = True
        self._proc = None
        self.running_task: str = ''
        self._log_path: Path | None = None
        self._log_offset = 0
        self._feed: dict | None = None
        self._course_name_cache: dict[str, str] | None = None

    # ------------------------------------------------------------------ #
    # 布局
    # ------------------------------------------------------------------ #
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial='tab-overview'):
            with TabPane('概览', id='tab-overview'):
                with Vertical():
                    with Horizontal(id='overview-grid'):
                        with Vertical(classes='card', id='session-card'):
                            yield Static('当前会话', classes='card-title')
                            yield Static(id='session-body')
                        with Vertical(classes='card', id='stats-card'):
                            yield Static('作业与队列', classes='card-title')
                            yield Static(id='stats-body')
                    with Vertical(classes='card', id='todo-card'):
                        yield Static('最近待办（按截止时间，回车跳到作业清单）',
                                     classes='card-title')
                        yield DataTable(id='todo-table', cursor_type='row',
                                        zebra_stripes=True)
                    yield Static(id='overview-actions', classes='action-bar')
            with TabPane('课堂·作业', id='tab-homework'):
                with Vertical():
                    with Horizontal(id='hw-toolbar'):
                        yield Input(placeholder='搜索课堂或作业名称…', id='hw-search')
                        yield Select(STATE_OPTIONS, id='hw-state', value='all',
                                     allow_blank=False)
                        yield Select(KIND_OPTIONS, id='hw-kind', value='all',
                                     allow_blank=False)
                    yield Static(id='hw-actions', classes='action-bar')
                    yield DataTable(id='hw-table', cursor_type='row', zebra_stripes=True)
                    yield Static('', id='hw-footer')
            with TabPane('多账号队列', id='tab-queue'):
                with Horizontal(id='queue-body'):
                    with Vertical(classes='card', id='queue-list'):
                        yield Static('账号队列（每个账号可单独选择课程）',
                                     classes='card-title')
                        yield DataTable(id='queue-table', cursor_type='row',
                                        zebra_stripes=True)
                        yield Static(id='queue-actions', classes='action-bar')
                        yield Static(id='queue-submit-actions', classes='action-bar')
                    with Vertical(classes='card', id='queue-add'):
                        yield Static('添加 / 更新账号', id='queue-form-title',
                                     classes='card-title')
                        yield Input(placeholder='账号：手机号 / 邮箱 / 用户名',
                                    id='q-account')
                        yield Input(placeholder='密码（保存到 data/accounts.json）',
                                    password=True, id='q-password')
                        yield Input(placeholder='备注（可选）', id='q-note')
                        yield Input(placeholder='课程 code/名称，逗号分隔；空=全部课堂',
                                    id='q-courses')
                        yield Static(id='queue-form-actions', classes='action-bar')
                        yield Static('', id='queue-session')
            with TabPane('执行任务', id='tab-tasks'):
                with Vertical(id='task-pane'):
                    with Horizontal(id='task-row1'):
                        yield Select(
                            [(TASKS[key].select_label, key) for key in TASK_ORDER],
                            id='task-kind', value='all_preview', allow_blank=False)
                        yield Input(placeholder='课堂 code 或名称（逗号分隔）',
                                    id='task-classroom')
                        yield Input(placeholder='limit（最多处理关卡数）', id='task-limit')
                    with Horizontal(id='task-row2'):
                        yield Input(placeholder='实验名包含…（UML/一键提交）',
                                    id='task-experiment')
                        yield Input(placeholder='poll-timeout（评测等待秒）',
                                    id='task-timeout')
                        yield Input(placeholder='账号间隔秒（队列，默认 1800）',
                                    id='task-gap')
                    with Horizontal(id='task-controls'):
                        yield Static(id='task-toggles', classes='action-bar')
                        yield Static(id='task-actions', classes='action-bar')
                        yield Static('就绪', id='task-status')
                    yield Static('', id='task-hint')
                    yield RichLog(id='task-log', wrap=True, max_lines=5000)
            with TabPane('实时日志', id='tab-log'):
                with Vertical(id='log-pane'):
                    with Horizontal(id='log-toolbar'):
                        yield Select(LOG_OPTIONS, id='log-file', value='queue',
                                     allow_blank=False)
                        yield Static(id='log-actions', classes='action-bar')
                    yield RichLog(id='log-view', wrap=True, max_lines=20000)
        yield Footer()

    def on_mount(self) -> None:
        hw_table = self.query_one('#hw-table', DataTable)
        hw_table.add_column('课堂', width=20)
        hw_table.add_column('类型', width=10)
        hw_table.add_column('作业', width=42)
        hw_table.add_column('截止', width=13)
        hw_table.add_column('状态', width=12)
        hw_table.add_column('剩余', width=15)

        todo_table = self.query_one('#todo-table', DataTable)
        todo_table.add_column('课堂', width=20)
        todo_table.add_column('类型', width=10)
        todo_table.add_column('作业', width=46)
        todo_table.add_column('截止', width=13)
        todo_table.add_column('状态', width=12)
        todo_table.add_column('剩余', width=15)

        queue_table = self.query_one('#queue-table', DataTable)
        queue_table.add_column('账号', width=16)
        queue_table.add_column('备注', width=8)
        queue_table.add_column('状态', width=8)
        queue_table.add_column('进度', width=24)
        queue_table.add_column('课程', width=20)
        queue_table.add_column('最后运行', width=11)
        queue_table.add_column('密码', width=10)

        self.refresh_all()
        self.set_interval(3.0, self._tick)
        width, height = self.size.width, self.size.height
        if width < 110 or height < 30:
            self.notify(f'当前窗口 {width}×{height}，建议至少 110×30，部分内容会被截断',
                        severity='warning', timeout=8)
        self.query_one('#task-log', RichLog).write(
            '[TUI] 选任务、填参数后按 [F5] 运行；真实提交会弹窗确认。'
            '操作条可直接用鼠标点击。')

    # ------------------------------------------------------------------ #
    # 操作条
    # ------------------------------------------------------------------ #
    def _update_bars(self) -> None:
        self.query_one('#overview-actions', Static).update(bar(
            ('r', '刷新状态', 'app.refresh_current'),
            ('c', '同步课堂', 'app.sync_courses'),
            ('h', '同步作业', 'app.sync_homeworks'),
            ('p', '提醒预览', 'app.preview_remind'),
            ('k', '校验配置', 'app.check_config'),
            ('a', '认证检查', 'app.auth_check'),
            ('P', '爬题预览', 'app.prepare_preview'),
            ('G', '预生成答案', 'app.prepare_generate'),
        ))
        self.query_one('#hw-actions', Static).update(bar(
            ('/', '搜索', 'app.focus_search'),
            ('o', '打开选中作业', 'app.open_link'),
            ('r', '刷新', 'app.refresh_homeworks'),
        ))
        self.query_one('#queue-actions', Static).update(bar(
            ('u', '设为当前', 'app.activate_account'),
            ('v', '验证密码', 'app.verify_account'),
            ('i', '修改信息', 'app.edit_account'),
            ('t', '设置状态', 'app.set_status'),
            ('m', '显示密码', 'app.toggle_passwords'),
            ('d', '删除账号', 'app.delete_account'),
        ))
        self.query_one('#queue-submit-actions', Static).update(bar(
            ('g', '选择课程', 'app.pick_courses'),
            ('s', '提交选中账号', 'app.submit_selected'),
            ('b', '全部开始提交', 'app.submit_all_accounts'),
        ))
        editing = self.editing_account
        form_bar = bar(('e', '保存修改' if editing else '保存到队列',
                        'app.save_account'))
        if editing:
            form_bar += '   ' + option('esc', '取消编辑',
                                       'app.cancel_account_edit')
        self.query_one('#queue-form-actions', Static).update(form_bar)
        self.query_one('#queue-form-title', Static).update(
            f'修改账号：{editing}' if editing else '添加 / 更新账号')
        self.query_one('#task-toggles', Static).update(self._toggles_bar())
        self.query_one('#task-actions', Static).update(bar(
            ('F5', '运行', 'app.run_task'),
            ('x', '停止任务', 'app.stop_task'),
            ('P', '爬题预览', 'app.prepare_preview'),
            ('G', '预生成答案', 'app.prepare_generate'),
        ))
        self.query_one('#log-actions', Static).update(bar(
            ('r', '刷新', 'app.refresh_log'),
            ('f', '跟随最新', 'app.toggle_follow', self.log_follow),
            ('y', '清空视图', 'app.clear_log'),
        ))

    def _toggles_bar(self) -> str:
        key = self._current_task_key()
        return options(
            option('n', '禁用 AI', 'app.toggle_noai', on=self.no_ai,
                   enabled=key in NO_AI_TASKS),
            option('l', '先释放环境 pod', 'app.toggle_release',
                   on=self.release_pods, enabled=key in RELEASE_TASKS),
        )

    # ------------------------------------------------------------------ #
    # 刷新
    # ------------------------------------------------------------------ #
    def refresh_all(self) -> None:
        self._course_name_cache = None
        self.refresh_overview()
        self.refresh_homeworks()
        self.refresh_queue()
        self._update_bars()
        self.query_one('#task-hint', Static).update(self._task_hint())

    def action_refresh_current(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == 'tab-log':
            self.refresh_log()
            return
        self.refresh_all()
        self.notify('已刷新本地状态', timeout=2)

    def refresh_overview(self) -> None:
        try:
            feed = data.summarize_feeds()
        except Exception as exc:  # 数据损坏不应让界面崩掉
            self.query_one('#session-body', Static).update(
                Text(f'读取本地状态失败：{exc}', style='red'))
            return
        self.query_one('#session-body', Static).update(self._session_text(feed['session']))
        self.query_one('#stats-body', Static).update(self._stats_text(feed))
        self.query_one('#queue-session', Static).update(self._queue_session_text(feed))
        self._fill_todo(feed)
        self._feed = feed
        self.sub_title = self._subtitle(feed)

    @staticmethod
    def _subtitle(feed: dict) -> str:
        session = feed['session']
        pending = feed['homeworks']['counts'].get('pending', 0)
        account = session['account'] or '未配置账号'
        return f'{account} · {pending} 项待完成'

    @staticmethod
    def _session_text(session: dict) -> Text:
        out = Text()

        def line(label: str, value: str, style: str = '') -> None:
            out.append(label + ' ' * max(1, 12 - cell_len(label)), style='bold')
            out.append(value + '\n', style=style)

        line('当前账号', session['account'] or '（未配置）',
             'green' if session['account'] else 'red')
        if session['session_ready']:
            line('会话', '有效（Token + Cookie 已缓存）', 'green')
        else:
            line('会话', '需要账号密码登录', 'yellow')
        line('Token', '有' if session['has_token'] else '无')
        line('Cookie', '有' if session['has_cookie'] else '无')
        if session['ai_configured']:
            line('AI', session['ai_model'] or '已配置', 'green')
        else:
            line('AI', '未配置（缺答案会跳过）', 'yellow')
        line('推送', '已配置 SendKey' if session['sendkey'] else '未配置 SendKey',
             'green' if session['sendkey'] else 'yellow')
        cooldown = session['cooldown']
        if cooldown:
            line('登录冷却', f'还需 {cooldown // 60} 分 {cooldown % 60} 秒', 'yellow')
        else:
            line('登录冷却', '无')
        line('同步间隔', f'每 {session["sync_hours"] or "6（默认）"} 小时')
        if session['classrooms_url']:
            line('课堂缓址', '已缓存')
        if not session['env_exists']:
            line('配置', '缺少 .env（先复制 .env.example）', 'red')
        return out

    @staticmethod
    def _stats_text(feed: dict) -> Text:
        now = feed['now']
        counts = feed['homeworks']['counts']
        queue = feed['queue']
        sync_times = feed['sync_times']
        latest = feed['latest_username']
        out = Text()

        def row(label: str, value: str, style: str = '') -> None:
            out.append(label + ' ' * max(1, 12 - cell_len(label)), style='bold')
            out.append(value + '\n', style=style)

        row('作业总数', str(feed['homeworks']['total']))
        pending = counts.get('pending', 0)
        urgent = feed['homeworks']
        row('待完成', f'{pending} 项（24h 内 {urgent["urgent_24h"]} / '
                      f'1h 内 {urgent["urgent_1h"]}）',
            'yellow' if pending else '')
        overdue = counts.get('overdue', 0)
        row('已逾期', f'{overdue} 项', 'red' if overdue else '')
        row('无截止时间', f'{counts.get("no_deadline", 0)} 项')
        row('已完成', f'{counts.get("completed", 0)} 项', 'green')
        row('课堂', f'{len(feed["courses"])} 个进行中')
        row('队列', f'{queue["total"]} 个（完成 {queue["done"]} / '
                    f'失败 {queue["failed"]} / 待处理 {queue["pending"]}）',
            'green' if queue['failed'] == 0 else 'yellow')
        synced = sync_times.get(latest) if latest else None
        row('最近同步', data.human_age(synced, now) if synced else '无记录', 'cyan')
        report = feed.get('unfinished') or {}
        experiments = report.get('experiments') or []
        if experiments:
            levels = sum(len(e.get('levels') or []) for e in experiments)
            unowned = report.get('unowned_levels', 0)
            row('上次校验', f'{len(experiments)} 个实验 / {levels} 关未完成'
                             + (f'（无主 {unowned}）' if unowned else ''),
                'red' if unowned else 'yellow')
        row('当前时间', now.strftime('%Y-%m-%d %H:%M:%S'))
        return out

    def _queue_session_text(self, feed: dict) -> Text:
        session = feed['session']
        out = Text()
        out.append('当前 .env 账号：', style='bold')
        out.append(f'{session["account"] or "（未配置）"}\n')
        out.append('登录状态：', style='bold')
        out.append('会话可用\n' if session['session_ready'] else '需要密码登录\n',
                   style='green' if session['session_ready'] else 'yellow')
        row = self._selected_queue_row()
        if row is not None:
            classrooms = row.get('classrooms') or []
            out.append('选中账号：', style='bold')
            out.append(f'{row["account"]}\n')
            out.append('课程：', style='bold')
            out.append((self._classrooms_label(classrooms) + '\n')
                       if classrooms else '全部课堂\n')
            if row.get('cooldown'):
                out.append('冷却：', style='bold')
                out.append(f'{row["cooldown"] // 60} 分 {row["cooldown"] % 60} 秒后'
                           '才能再次自动登录\n', style='yellow')
        if session['cooldown'] and not (row and row.get('cooldown')):
            out.append('冷却：', style='bold')
            out.append(f'{session["cooldown"] // 60} 分 {session["cooldown"] % 60} 秒\n',
                       style='yellow')
        out.append('提示：切换账号会写入 .env 并清空旧 Token/Cookie。', style='dim')
        return out

    def _fill_todo(self, feed: dict) -> None:
        table = self.query_one('#todo-table', DataTable)
        previous = table.cursor_row
        table.clear()
        rows = [r for r in feed['rows'] if r['state'] in ('pending', 'overdue')][:12]
        self.todo_rows = rows
        for index, row in enumerate(rows):
            color = data.STATE_COLORS.get(row['state'], '')
            remain_style = 'red' if row['state'] == 'overdue' else ''
            if row['state'] == 'pending':
                minutes = data.minutes_left(row.get('deadline'))
                if minutes is not None:
                    remain_style = 'red' if minutes <= 60 else (
                        'yellow' if minutes <= 1440 else '')
            table.add_row(
                _clip(row['course_name'], 20),
                row['kind_name'],
                _clip(row['name'], 42),
                row['deadline_text'],
                Text(row['state_label'], style=color),
                Text(row['remaining'], style=remain_style),
                key=str(index),
            )
        if not rows:
            table.add_row('（没有待完成或已逾期的作业）', '', '', '', '', '')
        else:
            table.move_cursor(row=min(previous, len(rows) - 1))

    @on(DataTable.RowSelected, '#todo-table')
    def _todo_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value or '')
        if not key.isdigit():
            return
        index = int(key)
        if not (0 <= index < len(self.todo_rows)):
            return
        row = self.todo_rows[index]
        self.query_one('#hw-search', Input).value = row['name']
        self.query_one(TabbedContent).active = 'tab-homework'

    def refresh_homeworks(self) -> None:
        try:
            self.hw_rows = data.homework_rows()
        except Exception as exc:
            self.hw_rows = []
            self.query_one('#hw-footer', Static).update(
                Text(f'读取作业失败：{exc}', style='red'))
            return
        table = self.query_one('#hw-table', DataTable)
        table.clear()
        query = self.query_one('#hw-search', Input).value.strip().casefold()
        state = str(self.query_one('#hw-state', Select).value)
        kind = str(self.query_one('#hw-kind', Select).value)
        visible = []
        for row in self.hw_rows:
            if state != 'all' and row['state'] != state:
                continue
            if kind != 'all' and str(row['kind']) != kind:
                continue
            if query and query not in (row['course_name'] + ' ' + row['name']).casefold():
                continue
            visible.append(row)
        self.hw_visible = visible
        for row in visible:
            color = data.STATE_COLORS.get(row['state'], '')
            remaining = row['remaining']
            remain_style = ''
            if row['state'] == 'pending':
                minutes = data.minutes_left(row.get('deadline'))
                if minutes is not None:
                    remain_style = ('red' if minutes <= 60
                                    else ('yellow' if minutes <= 1440 else ''))
            elif row['state'] == 'overdue':
                remain_style = 'red'
            table.add_row(
                _clip(row['course_name'], 20),
                row['kind_name'],
                _clip(row['name'], 42),
                row['deadline_text'],
                Text(row['state_label'], style=color),
                Text(remaining, style=remain_style),
            )
        counts = data.summary(self.hw_rows)['counts']
        summary_text = ' · '.join(
            f'{data.STATE_LABELS[key]} {counts.get(key, 0)}'
            for key in ('pending', 'overdue', 'no_deadline', 'completed')
        )
        footer = (f'显示 {len(visible)} / {len(self.hw_rows)} 条　|　{summary_text}'
                  f'　|　按 o 在浏览器打开选中作业')
        self.query_one('#hw-footer', Static).update(footer)

    def _classrooms_label(self, classrooms: list[str]) -> str:
        """把课堂 code 映射成名称，找不到就原样显示。"""
        if self._course_name_cache is None:
            self._course_name_cache = {
                str(c.get('identifier')): str(c.get('name') or '')
                for c in data.courses()}
        names = self._course_name_cache
        parts = []
        for value in classrooms:
            name = names.get(value) or ''
            parts.append(f'{value}({_clip(name, 8)})' if name else value)
        return '、'.join(parts)

    def refresh_queue(self) -> None:
        try:
            self.queue_rows = data.queue_rows()
        except Exception as exc:
            self.queue_rows = []
            self.query_one('#queue-session', Static).update(
                Text(f'读取队列失败：{exc}', style='red'))
            return
        table = self.query_one('#queue-table', DataTable)
        previous = table.cursor_row
        table.clear()
        reveal = self.reveal_passwords
        for item in self.queue_rows:
            status = item['status']
            status_style = {'done': 'green', 'failed': 'red'}.get(status, 'yellow')
            if item.get('manual'):
                progress = {'done': '手动标记完成',
                            'failed': _clip(item['error'], 24),
                            'pending': '手动设为待处理'}.get(status, '手动设置')
            elif status == 'done':
                progress = (f'提交{item["submitted"]} 失败{item["failed"]}'
                            f' 跳过{item["skipped_passed"]}')
            elif status == 'failed':
                progress = _clip(item['error'], 24)
            else:
                progress = '尚未运行'
            password = data.password_display({'password': item['password']}, reveal)
            classrooms = item.get('classrooms') or []
            table.add_row(
                item['account'],
                _clip(item['note'], 8),
                Text(data.QUEUE_STATUS_LABELS.get(status, status),
                     style=status_style),
                _clip(progress, 24),
                _clip(self._classrooms_label(classrooms), 20) if classrooms else '全部',
                data.human_age(item['finished_at']) if item['finished_at'] else '-',
                password,
                key=item['account'],
            )
        if not self.queue_rows:
            self.selected_account = ''
        elif self.selected_account not in {r['account'] for r in self.queue_rows}:
            self.selected_account = self.queue_rows[0]['account']
        if self.queue_rows:
            index = next((i for i, r in enumerate(self.queue_rows)
                          if r['account'] == self.selected_account),
                         min(previous, len(self.queue_rows) - 1))
            table.move_cursor(row=max(0, index))

    # ------------------------------------------------------------------ #
    # 事件：筛选 / 选择
    # ------------------------------------------------------------------ #
    @on(Input.Changed, '#hw-search')
    def _hw_search_changed(self) -> None:
        self.refresh_homeworks()

    @on(Select.Changed, '#hw-state')
    def _hw_state_changed(self) -> None:
        self.refresh_homeworks()

    @on(Select.Changed, '#hw-kind')
    def _hw_kind_changed(self) -> None:
        self.refresh_homeworks()

    @on(DataTable.RowHighlighted, '#queue-table')
    def _queue_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if key:
            self.selected_account = str(key)
            if self._feed is not None:
                self.query_one('#queue-session', Static).update(
                    self._queue_session_text(self._feed))

    @on(DataTable.RowSelected, '#queue-table')
    def _queue_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        if key:
            self.selected_account = str(key)
            self.action_activate_account()

    @on(Select.Changed, '#task-kind')
    def _task_kind_changed(self) -> None:
        self._update_bars()
        self.query_one('#task-hint', Static).update(self._task_hint())

    @on(TabbedContent.TabActivated)
    def _tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pane = event.pane.id or ''
        if pane == 'tab-overview':
            self.refresh_overview()
        elif pane == 'tab-homework':
            self.refresh_homeworks()
        elif pane == 'tab-queue':
            self.refresh_queue()
            self._update_bars()
        elif pane == 'tab-tasks':
            self._update_bars()
        elif pane == 'tab-log':
            self.refresh_log()

    # ------------------------------------------------------------------ #
    # 概览动作
    # ------------------------------------------------------------------ #
    def action_sync_courses(self) -> None:
        self._start_task('courses')

    def action_sync_homeworks(self) -> None:
        self._start_task('homeworks')

    def action_preview_remind(self) -> None:
        self._start_task('remind_preview')

    def action_check_config(self) -> None:
        self._start_task('remind_check')

    def action_auth_check(self) -> None:
        self._start_task('auth_check')

    def action_prepare_preview(self) -> None:
        """爬题预览：切到执行任务页，跑 `prepare --dry-run`（不写文件、不调 AI）。"""
        self._select_task('prepare_preview')
        self._start_task('prepare_preview')

    def action_prepare_generate(self) -> None:
        """预生成答案：切到执行任务页，跑 `prepare`（只写 prepared/，会弹窗确认）。"""
        self._select_task('prepare_apply')
        self._start_task('prepare_apply')

    def _select_task(self, key: str) -> None:
        """把执行任务页的任务下拉框切到指定任务（不在该页时先切页）。"""
        self.query_one(TabbedContent).active = 'tab-tasks'
        self.query_one('#task-kind', Select).value = key

    # ------------------------------------------------------------------ #
    # 作业动作
    # ------------------------------------------------------------------ #
    def action_focus_search(self) -> None:
        self.query_one(TabbedContent).active = 'tab-homework'
        self.query_one('#hw-search', Input).focus()

    def action_refresh_homeworks(self) -> None:
        self.refresh_homeworks()
        self.notify('作业列表已刷新', timeout=2)

    def action_open_link(self) -> None:
        if self.query_one(TabbedContent).active != 'tab-homework':
            return
        table = self.query_one('#hw-table', DataTable)
        index = table.cursor_row
        if not self.hw_visible or index is None or index >= len(self.hw_visible):
            return
        row = self.hw_visible[index]
        url = row.get('url') or ''
        if not url:
            self.notify('该作业没有链接', severity='warning')
            return
        webbrowser.open(url)
        self.notify(f'已在浏览器打开：{_clip(row["name"], 30)}', timeout=3)

    # ------------------------------------------------------------------ #
    # 队列动作
    # ------------------------------------------------------------------ #
    def _on_queue_tab(self) -> bool:
        if self.query_one(TabbedContent).active != 'tab-queue':
            self.notify('这些操作在「多账号队列」页（按 3 切换）', timeout=3)
            return False
        return True

    def _selected_queue_row(self) -> dict | None:
        for item in self.queue_rows:
            if item['account'] == self.selected_account:
                return item
        return self.queue_rows[0] if self.queue_rows else None

    def action_activate_account(self) -> None:
        if not self._on_queue_tab():
            return
        item = self._selected_queue_row()
        if item is None:
            self.notify('队列为空，先添加账号', severity='warning')
            return
        password = data.decrypt_password(item['password'])
        if not password:
            self.notify('该账号密码缺失或无法解密', severity='error')
            return
        classrooms = item.get('classrooms') or []

        def done(ok: bool | None) -> None:
            if not ok:
                return
            try:
                data.activate_account(item['account'], password, clear_limit=True)
            except Exception as exc:
                self.notify(f'切换失败：{exc}', severity='error')
                return
            self.refresh_all()
            self.notify(f'已切换当前账号为 {item["account"]}', timeout=3)

        self.push_screen(ConfirmScreen(
            '切换当前账号',
            f'把 .env 的登录账号切换为 {item["account"]}，\n'
            f'该账号课程：{self._classrooms_label(classrooms) if classrooms else "全部课堂"}\n'
            '并清空旧账号的 Token / Cookie / 课堂地址缓存。',
            danger=False, confirm_label='切换'), done)

    def action_verify_account(self) -> None:
        if not self._on_queue_tab():
            return
        item = self._selected_queue_row()
        if item is None:
            self.notify('队列为空，先添加账号', severity='warning')
            return
        argv = [PY, '-u', str(SCRIPTS / 'verify_accounts.py'),
                '--only', item['account'], '--clear-limit']
        self._start_task('verify_all', argv=argv,
                         body=f'联网验证 {item["account"]} 的密码，并清除该账号登录冷却。\n'
                              '验证过程会改写 .env 的当前账号。')

    def _clear_account_form(self) -> None:
        for key in ('#q-account', '#q-password', '#q-note', '#q-courses'):
            self.query_one(key, Input).value = ''

    def action_edit_account(self) -> None:
        """把选中账号填进右侧表单，进入修改模式。"""
        if not self._on_queue_tab():
            return
        item = self._selected_queue_row()
        if item is None:
            self.notify('队列为空，先添加账号', severity='warning')
            return
        account = item['account']
        password = data.decrypt_password(item['password'])
        self.editing_account = account
        self.query_one('#q-account', Input).value = account
        self.query_one('#q-password', Input).value = password
        self.query_one('#q-note', Input).value = item.get('note', '')
        self.query_one('#q-courses', Input).value = '，'.join(
            item.get('classrooms') or [])
        self._update_bars()
        self.query_one('#q-password', Input).focus()
        if str(item.get('password', '')).startswith('enc:') and not password:
            self.notify('密码已加密且无法解密：留空保存会保留原密码',
                        severity='warning', timeout=4)
        else:
            self.notify(f'正在修改 {account}：改完按 [e] 保存，[esc] 取消',
                        timeout=3)

    def action_cancel_account_edit(self) -> None:
        if not self.editing_account:
            return
        self.editing_account = ''
        self._clear_account_form()
        self._update_bars()
        self.notify('已取消编辑', timeout=2)

    def action_set_status(self) -> None:
        """手动设置账号在本地队列里的状态。"""
        if not self._on_queue_tab():
            return
        item = self._selected_queue_row()
        if item is None:
            self.notify('队列为空，先添加账号', severity='warning')
            return
        account = item['account']

        def done(result: str | None) -> None:
            if not result:
                return
            try:
                if result == 'reset':
                    data.set_queue_status(account, 'pending', reset_progress=True)
                    label = '待处理（已清空进度）'
                else:
                    data.set_queue_status(account, result)
                    label = data.QUEUE_STATUS_LABELS.get(result, result)
            except Exception as exc:
                self.notify(f'设置失败：{exc}', severity='error')
                return
            self.selected_account = account
            self.refresh_queue()
            self._update_bars()
            self.notify(f'{account} 的状态已设为：{label}', timeout=3)

        self.push_screen(StatusScreen(account, item['status']), done)

    def action_pick_courses(self) -> None:
        if not self._on_queue_tab():
            return
        item = self._selected_queue_row()
        if item is None:
            self.notify('队列为空，先添加账号', severity='warning')
            return
        account = item['account']
        current = item.get('classrooms') or []

        def done(result: list[str] | None) -> None:
            if result is None:
                return
            try:
                data.set_account_classrooms(account, result)
            except Exception as exc:
                self.notify(f'保存课程失败：{exc}', severity='error')
                return
            self.refresh_queue()
            self.notify(f'{account} 的课程已设为：'
                        + (self._classrooms_label(result) if result else '全部课堂'),
                        timeout=3)

        self.push_screen(CoursePickerScreen(account, current), done)

    def _account_argv(self, account: str) -> list[str]:
        """只跑某个账号：把它自己的 classrooms 显式写成 --classroom 参数。"""
        form = self._options_from_form()
        argv = [PY, '-u', str(SCRIPTS / 'run_queue.py'),
                '--apply', '--only', account, '--force']
        for classroom in data.account_classrooms(account):
            argv += ['--classroom', classroom]
        if form.limit.strip():
            argv += ['--limit', form.limit.strip()]
        if form.timeout.strip():
            argv += ['--poll-timeout', form.timeout.strip()]
        if form.gap.strip():
            argv += ['--gap', form.gap.strip()]
        if form.no_ai:
            argv.append('--no-ai')
        return argv

    def action_submit_selected(self) -> None:
        if not self._on_queue_tab():
            return
        item = self._selected_queue_row()
        if item is None:
            self.notify('队列为空，先添加账号', severity='warning')
            return
        classrooms = item.get('classrooms') or []
        self._start_task(
            'queue_apply', argv=self._account_argv(item['account']),
            body=f'只提交账号 {item["account"]}（强制重跑，忽略上次完成状态）。\n'
                 f'课程：{self._classrooms_label(classrooms) if classrooms else "全部课堂"}\n'
                 'limit / poll-timeout / 账号间隔 / 禁用 AI 取自「执行任务」页。')

    def action_submit_all_accounts(self) -> None:
        if not self._on_queue_tab():
            return
        if not self.queue_rows:
            self.notify('队列为空，先添加账号', severity='warning')
            return
        # 不使用任务页的课堂筛选，按每个账号自己的 classrooms 执行
        form = self._options_from_form()
        form.classroom = ''
        classrooms_note = '、'.join(
            f'{r["account"]}={self._classrooms_label(r["classrooms"]) if r["classrooms"] else "全部"}'
            for r in self.queue_rows)
        self._start_task(
            'queue_apply', options=form,
            body='按队列顺序串行提交所有账号，每个账号使用自己配置的课程。\n'
                 '已完成的账号会跳过；要强制重跑请在队列里选账号按 [s]。\n'
                 'limit / poll-timeout / 账号间隔 / 禁用 AI 取自「执行任务」页。\n'
                 '（这条命令不带 --classroom，由 run_queue 逐个账号读取 classrooms，\n'
                 '运行日志开头会打印每个账号的课程安排。）\n\n'
                 + _clip(classrooms_note, 300))

    def action_toggle_passwords(self) -> None:
        self.reveal_passwords = not self.reveal_passwords
        self.refresh_queue()
        self.notify('显示明文密码' if self.reveal_passwords else '已隐藏密码',
                    timeout=2)

    def action_delete_account(self) -> None:
        if not self._on_queue_tab():
            return
        item = self._selected_queue_row()
        if item is None:
            self.notify('队列为空', severity='warning')
            return

        def done(ok: bool | None) -> None:
            if not ok:
                return
            if data.remove_account(item['account']):
                self.selected_account = ''
                self.refresh_queue()
                if self.queue_rows:
                    self.selected_account = self.queue_rows[0]['account']
                self.notify(f'已删除 {item["account"]}', timeout=2)

        self.push_screen(ConfirmScreen(
            '删除账号',
            f'从 data/accounts.json 中删除 {item["account"]}（不会删除提交记录）。',
            danger=True, confirm_label='删除'), done)

    def action_save_account(self) -> None:
        if not self._on_queue_tab():
            return
        account = self.query_one('#q-account', Input).value.strip()
        password = self.query_one('#q-password', Input).value
        note = self.query_one('#q-note', Input).value.strip()
        courses_text = self.query_one('#q-courses', Input).value.strip()
        classrooms = data.clean_classrooms(courses_text) if courses_text else None
        editing = self.editing_account
        try:
            if editing:
                final = data.update_account(editing, account or editing,
                                            password or None, note, classrooms)
                message = f'已更新账号 {final}'
            else:
                data.add_account(account, password, note, classrooms)
                final = account
                message = f'已保存账号 {final}'
        except Exception as exc:
            self.notify(str(exc), severity='error')
            return
        self.editing_account = ''
        self._clear_account_form()
        self.selected_account = final
        self.refresh_queue()
        self._update_bars()
        saved = next((r.get('classrooms') or [] for r in self.queue_rows
                      if r['account'] == final), [])
        target = self._classrooms_label(saved) if saved else '全部课堂'
        self.notify(f'{message}（课程：{target}）', timeout=3)

    # ------------------------------------------------------------------ #
    # 任务
    # ------------------------------------------------------------------ #
    def _options_from_form(self) -> Options:
        return Options(
            classroom=self.query_one('#task-classroom', Input).value,
            limit=self.query_one('#task-limit', Input).value,
            experiment=self.query_one('#task-experiment', Input).value,
            timeout=self.query_one('#task-timeout', Input).value,
            gap=self.query_one('#task-gap', Input).value,
            no_ai=self.no_ai,
            release=self.release_pods,
        )

    def _current_task_key(self) -> str:
        value = self.query_one('#task-kind', Select).value
        return str(value) if value in TASKS else 'all_preview'

    def _task_hint(self) -> Text:
        key = self._current_task_key()
        task = TASKS.get(key)
        if task is None:
            return Text('')
        out = Text(task.hint or '')
        if task.danger:
            out.append('　⚠ 会真实修改平台数据', style='bold red')
        elif task.confirm:
            out.append('　需要二次确认', style='yellow')
        out.append(f'\n日志同时写入 {data.display_path(data.TUI_LOG)}', style='dim')
        return out

    def _start_task(self, key: str, options: Options | None = None,
                    argv: list[str] | None = None, body: str | None = None) -> None:
        if self.running_task:
            self.notify(f'已有任务在运行：{self.running_task}，先停止再启动',
                        severity='warning')
            return
        task = TASKS[key]
        argv = argv or build_command(key, options or self._options_from_form())
        command = command_display(argv)
        if task.confirm:
            self.push_screen(
                ConfirmScreen(task.label, body or task.hint or task.label,
                              command=command,
                              confirm_label='真实执行' if task.danger else '确认',
                              danger=task.danger),
                lambda ok: self._launch(key, argv) if ok else None,
            )
        else:
            self._launch(key, argv)

    def _launch(self, key: str, argv: list[str]) -> None:
        task = TASKS[key]
        log = self.query_one('#task-log', RichLog)
        log.write(Text(f'\n$ {command_display(argv)}', style='bold cyan'))
        self.running_task = key
        self.query_one('#task-status', Static).update(
            Text(f'运行中：{task.label}', style='yellow'))
        self._execute(key, argv)

    def _thread_call(self, callback, *args) -> None:
        """线程 worker 回调界面；应用退出后忽略，避免刷一屏异常。"""
        try:
            self.call_from_thread(callback, *args)
        except Exception:
            pass

    @work(thread=True, exclusive=True, group='task', exit_on_error=False)
    def _execute(self, key: str, argv: list[str]) -> None:
        rc = -1
        proc = None
        try:
            proc = spawn(argv)
            self._proc = proc
            data.append_tui_log(f'[task] $ {command_display(argv)}')
            if proc.stdout is not None:
                for line in proc.stdout:
                    self._thread_call(self._task_line, line.rstrip('\r\n'))
            rc = proc.wait()
        except Exception as exc:  # 启动失败（例如解释器路径异常）
            self._thread_call(self._task_line,
                              f'启动失败：{type(exc).__name__}: {exc}')
        finally:
            if proc is not None and proc.stdout is not None:
                try:
                    proc.stdout.close()
                except OSError:
                    pass
            self._proc = None
            self._thread_call(self._task_finished, key, rc)

    def _task_line(self, line: str) -> None:
        log = self.query_one('#task-log', RichLog)
        text = line.rstrip()
        if not text:
            log.write('')
            return
        data.append_tui_log(text)
        style = ''
        if text.startswith('✓') or '已通过' in text:
            style = 'green'
        elif text.startswith('✗') or 'Traceback' in text or '失败' in text:
            style = 'red'
        elif text.startswith('$') or text.startswith('#'):
            style = 'cyan'
        log.write(Text(text, style=style))
        self.query_one('#task-status', Static).update(
            Text(_clip(text, 100), style=style or ''))

    def _task_finished(self, key: str, rc: int) -> None:
        self.running_task = ''
        task = TASKS[key]
        style = 'green' if rc == 0 else 'red'
        self.query_one('#task-status', Static).update(
            Text(f'{"完成" if rc == 0 else "结束"}：{task.label}（退出码 {rc}）',
                 style=style))
        self.query_one('#task-log', RichLog).write(Text(
            f'—— 任务结束：{task.label}，退出码 {rc} ——',
            style=f'bold {style}'))
        data.append_tui_log(f'[task] 结束 rc={rc} {task.key}')
        self.refresh_all()
        self.notify(f'{task.label}：退出码 {rc}',
                    severity='information' if rc == 0 else 'error', timeout=4)

    def action_run_task(self) -> None:
        self._start_task(self._current_task_key())

    def action_stop_task(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            self.notify('没有正在运行的任务', timeout=2)
            return
        data.append_tui_log('[task] 用户请求停止')
        self._task_line('已请求停止，正在终止子进程…')
        proc.terminate()
        self.set_timer(5.0, self._force_kill)

    def _force_kill(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.kill()
            self._task_line('子进程未退出，已强制结束')

    def action_toggle_noai(self) -> None:
        if self._current_task_key() not in NO_AI_TASKS:
            self.notify('当前任务不支持「禁用 AI」', timeout=2)
            return
        self.no_ai = not self.no_ai
        self._update_bars()
        self.notify('已禁用 AI 自动做题' if self.no_ai else 'AI 自动做题已启用', timeout=2)

    def action_toggle_release(self) -> None:
        if self._current_task_key() not in RELEASE_TASKS:
            self.notify('当前任务不支持「先释放环境 pod」', timeout=2)
            return
        self.release_pods = not self.release_pods
        self._update_bars()
        self.notify('运行前会释放环境 pod' if self.release_pods
                    else '运行前不释放环境 pod', timeout=2)

    # ------------------------------------------------------------------ #
    # 分页 / 帮助 / 退出
    # ------------------------------------------------------------------ #
    def action_tab_overview(self) -> None:
        self.query_one(TabbedContent).active = 'tab-overview'

    def action_tab_homework(self) -> None:
        self.query_one(TabbedContent).active = 'tab-homework'

    def action_tab_queue(self) -> None:
        self.query_one(TabbedContent).active = 'tab-queue'

    def action_tab_tasks(self) -> None:
        self.query_one(TabbedContent).active = 'tab-tasks'

    def action_tab_log(self) -> None:
        self.query_one(TabbedContent).active = 'tab-log'

    def action_shortcuts(self) -> None:
        self.notify(
            '1-5 切换分页 · 每页底部有 [按键] 操作条（可点击）\n'
            'r 刷新 · x / Ctrl+S 停止任务 · F1 帮助 · Ctrl+Q 退出\n'
            '概览/任务页：P 爬题预览 · G 爬题并集中预生成 AI 答案\n'
            '队列页：g 选课程 · s 提交选中账号 · b 全部开始提交',
            title='快捷键', timeout=10)

    def action_quit_app(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            # 直接 kill 并关掉管道，避免退出时卡在等待子进程/worker 线程
            proc.kill()
            if proc.stdout is not None:
                try:
                    proc.stdout.close()
                except OSError:
                    pass
        self.exit()

    # ------------------------------------------------------------------ #
    # 日志跟踪
    # ------------------------------------------------------------------ #
    @on(Select.Changed, '#log-file')
    def _log_file_changed(self) -> None:
        self.refresh_log(force=True)

    def action_refresh_log(self) -> None:
        self.refresh_log(force=True)

    def action_toggle_follow(self) -> None:
        self.log_follow = not self.log_follow
        self._update_bars()
        if self.log_follow:
            self.refresh_log()
        self.notify('日志跟随：开' if self.log_follow else '日志跟随：关', timeout=2)

    def action_clear_log(self) -> None:
        self.query_one('#log-view', RichLog).clear()

    def refresh_log(self, force: bool = False) -> None:
        choice = str(self.query_one('#log-file', Select).value)
        path = data.QUEUE_LOG if choice == 'queue' else data.TUI_LOG
        view = self.query_one('#log-view', RichLog)
        if force or path != self._log_path:
            self._log_path = path
            view.clear()
            tail = data.log_tail(path, 300)
            for line in tail:
                view.write(Text(line))
            try:
                self._log_offset = path.stat().st_size if path.exists() else 0
            except OSError:
                self._log_offset = 0
            if not path.exists():
                self.notify(f'{data.display_path(path)} 不存在（还没有产生日志）',
                            severity='warning', timeout=3)
            return
        try:
            size = path.stat().st_size
        except OSError:
            return
        if size < self._log_offset:
            self._log_offset = 0
        if size == self._log_offset:
            return
        try:
            with path.open('r', encoding='utf-8', errors='replace') as handle:
                handle.seek(self._log_offset)
                chunk = handle.read()
                self._log_offset = handle.tell()
        except OSError:
            return
        for line in chunk.splitlines():
            view.write(Text(line))

    def _tick(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == 'tab-overview':
            self.refresh_overview()
        elif active == 'tab-log' and self.log_follow:
            self.refresh_log()


def main() -> None:
    EducoderTUI().run()
