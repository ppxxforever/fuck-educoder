"""TUI 任务定义与子进程执行。

所有会联网 / 提交 / 推送的动作都以子进程方式调用项目现有 CLI，
TUI 只负责参数拼装、确认和日志展示，避免在界面进程里跑 Playwright
（也避免和后台 systemd 服务抢进程锁）。
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Task:
    key: str
    label: str
    argv: tuple[str, ...]
    group: str = ''
    hint: str = ''
    # confirm: 需要弹窗确认（会写数据或占用额度）；danger: 真实提交/推送，红色确认
    confirm: bool = False
    danger: bool = False

    @property
    def select_label(self) -> str:
        return f'{self.group} · {self.label}' if self.group else self.label


PY = sys.executable
SCRIPTS = ROOT / 'scripts'

TASKS: dict[str, Task] = {}


def _add(task: Task) -> None:
    TASKS[task.key] = task


_add(Task('courses', '刷新进行中课堂', ('-m', 'educoder_reminder.courses'), '采集',
          '访问课堂接口，更新 data/courses.json'))
_add(Task('homeworks', '同步课堂与作业', ('-m', 'educoder_reminder.homeworks'), '采集',
          '刷新课堂并采集两类作业，写入 SQLite 与 JSON'))
_add(Task('archive_failures', '归档未通过关卡',
          (str(SCRIPTS / 'archive_failures.py'),), '采集',
          '只读：把未通过关卡的本地答案/平台反馈存到 attempts/'))
_add(Task('archive_solutions', '归档已通关答案',
          (str(SCRIPTS / 'archive_solutions.py'),), '采集',
          '只读：把已完成关卡的答案存到 solutions/'))
_add(Task('remind_check', '校验提醒配置', ('-m', 'educoder_reminder.remind', 'check'), '提醒',
          '只检查 .env 配置，不联网、不推送'))
_add(Task('remind_preview', '本地预览待发提醒', ('-m', 'educoder_reminder.remind', 'preview'), '提醒',
          '只读本地数据库，不联网、不推送'))
_add(Task('auth_check', '联网校验登录状态', ('-m', 'educoder_reminder.remind', 'auth-check'), '认证',
          '身份失效时自动用账号密码恢复会话（受频率限制）'))
_add(Task('remind_test', '发送测试推送', ('-m', 'educoder_reminder.remind', 'test'), '提醒',
          '占用一次 Server 酱额度', confirm=True))
_add(Task('remind_once', '检查并发送一次提醒', ('-m', 'educoder_reminder.remind', 'once'), '提醒',
          '到期则同步并推送，会真实发送', confirm=True, danger=True))
_add(Task('submit_preview', '预览选择题/代码题提交', ('-m', 'educoder_reminder.submit'), '提交',
          '只读平台状态，打印会提交什么'))
_add(Task('submit_apply', '真实提交选择题/代码题', ('-m', 'educoder_reminder.submit', '--apply'), '提交',
          '会向平台提交答案并触发评测（默认跳过已截止实验）', confirm=True, danger=True))
_add(Task('uml_preview', '预览 UML 绘图题提交', ('-m', 'educoder_reminder.submit_uml'), '提交',
          '只读，不写工作区'))
_add(Task('uml_apply', '真实提交 UML 绘图题', ('-m', 'educoder_reminder.submit_uml', '--apply'), '提交',
          'SSH 写入 VNC 工作区并触发评测（默认跳过已截止实验）', confirm=True, danger=True))
_add(Task('all_preview', '预览一键提交', ('-m', 'educoder_reminder.submit_all'), '提交',
          '平台驱动的整体预览'))
_add(Task('all_apply', '真实一键提交', ('-m', 'educoder_reminder.submit_all', '--apply'), '提交',
          '选择/代码题 + UML 题全部提交（默认跳过已截止实验）', confirm=True, danger=True))
_add(Task('all_repair', '修复「已通过但未记通关」',
          ('-m', 'educoder_reminder.submit_all', '--apply', '--repair-status'), '提交',
          '只重交评测已通过、但平台 status≠2 的关卡；需本地答案（默认跳过已截止）', confirm=True, danger=True))
_add(Task('prepare_preview', '预览：课程爬题查缺答案',
          ('-m', 'educoder_reminder.prepare', '--dry-run'), '题库',
          '只读平台：列出每关是否已有本地答案、要不要 AI，不写文件'))
_add(Task('prepare_apply', '课程爬题 + 集中预生成 AI 答案',
          ('-m', 'educoder_reminder.prepare'), '题库',
          '写入 prepared/，不提交；已有本地答案的关卡不调用 AI', confirm=True))
_add(Task('queue_preview', '查看队列计划', (str(SCRIPTS / 'run_queue.py'), '--list'), '队列',
          '打印账号与上次运行结果'))
_add(Task('queue_status', '查看队列汇总', (str(SCRIPTS / 'queue_status.py'), '--log-lines', '30'), '队列',
          '账号状态 + 当前登录态 + 日志尾部'))
_add(Task('queue_status_detail', '联网检查课堂进度', (str(SCRIPTS / 'queue_status.py'), '--detail'), '队列',
          '会用账号登录一次（会改写 .env 当前账号），较慢'))
_add(Task('verify_all', '验证队列账号密码', (str(SCRIPTS / 'verify_accounts.py'), '--clear-limit'), '队列',
          '逐个联网验证并清除登录冷却（会依次改写 .env 当前账号）', confirm=True))
_add(Task('queue_apply', '串行刷题（全部账号）', (str(SCRIPTS / 'run_queue.py'), '--apply'), '队列',
          '按队列顺序真实提交，账号之间会等待', confirm=True, danger=True))


TASK_ORDER = list(TASKS)

# 哪些任务支持哪些参数输入（用于在界面上禁用不相关输入框）
CLASSROOM_TASKS = {'submit_preview', 'submit_apply', 'uml_preview', 'uml_apply',
                   'all_preview', 'all_apply', 'all_repair', 'queue_apply',
                   'prepare_preview', 'prepare_apply'}
LIMIT_TASKS = {'submit_preview', 'submit_apply', 'uml_preview', 'uml_apply',
               'all_preview', 'all_apply', 'all_repair', 'queue_apply',
               'prepare_preview', 'prepare_apply'}
EXPERIMENT_TASKS = {'uml_preview', 'uml_apply', 'all_preview', 'all_apply',
                    'all_repair', 'queue_apply', 'prepare_preview', 'prepare_apply'}
NO_AI_TASKS = {'submit_preview', 'submit_apply', 'uml_preview', 'uml_apply',
               'all_preview', 'all_apply', 'all_repair', 'queue_apply',
               'prepare_preview', 'prepare_apply'}
RELEASE_TASKS = {'uml_preview', 'uml_apply', 'all_preview', 'all_apply', 'all_repair'}
TIMEOUT_TASKS = {'submit_preview', 'submit_apply', 'uml_preview', 'uml_apply',
                 'all_preview', 'all_apply', 'all_repair', 'queue_apply'}
GAP_TASKS = {'queue_apply'}


@dataclass
class Options:
    classroom: str = ''
    limit: str = ''
    experiment: str = ''
    timeout: str = ''
    gap: str = ''
    no_ai: bool = False
    release: bool = False


def split_filters(values: str) -> list[str]:
    out = []
    for part in str(values or '').replace('，', ',').split(','):
        part = part.strip()
        if part:
            out.append(part)
    return out


def build_command(key: str, options: Options) -> list[str]:
    task = TASKS[key]
    argv = list(task.argv)
    # 统一用当前解释器启动（模块方式或 scripts/*.py 都需要），非 Python 命令原样保留
    if not argv or argv[0] != PY:
        argv = [PY, '-u', *argv]
    if key == 'submit_preview' or key == 'submit_apply':
        argv += _common_options(options, classroom=True, limit=True, no_ai=True,
                                timeout=True)
    elif key in ('uml_preview', 'uml_apply'):
        argv += _common_options(options, classroom=True, limit=True, experiment=True,
                                no_ai=True, timeout=True)
        if options.release:
            argv.append('--release-envs')
    elif key in ('all_preview', 'all_apply', 'all_repair'):
        argv += _common_options(options, classroom=True, limit=True, experiment=True,
                                no_ai=True, timeout=True)
        if options.release:
            argv.append('--release-envs')
    elif key == 'queue_apply':
        argv += _common_options(options, classroom=True, limit=True, experiment=True,
                                no_ai=True, timeout=True)
        if options.gap.strip():
            argv += ['--gap', options.gap.strip()]
    elif key in ('prepare_preview', 'prepare_apply'):
        argv += _common_options(options, classroom=True, limit=True, experiment=True,
                                no_ai=True)
    return argv


def _common_options(options: Options, *, classroom=False, limit=False, experiment=False,
                    no_ai=False, timeout=False, gap=False) -> list[str]:
    argv: list[str] = []
    if classroom:
        for item in split_filters(options.classroom):
            argv += ['--classroom', item]
    if limit and options.limit.strip():
        argv += ['--limit', options.limit.strip()]
    if experiment and options.experiment.strip():
        argv += ['--experiment', options.experiment.strip()]
    if timeout and options.timeout.strip():
        argv += ['--poll-timeout', options.timeout.strip()]
    if gap and options.gap.strip():
        argv += ['--gap', options.gap.strip()]
    if no_ai and options.no_ai:
        argv.append('--no-ai')
    return argv


def command_display(argv: list[str]) -> str:
    parts = [Path(argv[0]).name] + argv[1:]
    return shlex.join(parts)


def subprocess_env() -> dict:
    env = dict(os.environ)
    env.update({
        'PYTHONUNBUFFERED': '1',
        'PYTHONIOENCODING': 'utf-8',
        'TERM': 'dumb',
        'COLUMNS': '200',
        'NO_COLOR': '1',
    })
    return env


def spawn(argv: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        argv,
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
        env=subprocess_env(),
    )
