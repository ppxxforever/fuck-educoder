#!/usr/bin/env python3
"""Render/install/manage the Debian system service; never install implicitly."""
import argparse
import os
import pwd
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = 'educoder-reminder.service'


def quote(value, *, executable=False):
    if any(c in value for c in '\n\r\0'):
        raise ValueError('服务路径不能包含换行或空字符。')
    value = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    if executable:
        value = value.replace('$', '$$')
    return '"' + value + '"'


def render(root, username):
    if not root.is_absolute():
        raise ValueError('项目目录必须是绝对路径。')
    account = pwd.getpwnam(username)
    if account.pw_uid == 0:
        raise ValueError('请指定非 root 的运行用户。')
    if not username or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in username):
        raise ValueError('运行用户名格式不受支持。')
    # ExecStart uses only a preinstalled venv: no package download at service startup.
    return f'''[Unit]
Description=Educoder homework reminders
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User={username}
WorkingDirectory={str(root).replace('%', '%%')}
ExecStart={quote(str(root / '.venv/bin/python'), executable=True)} -u -m educoder_reminder.remind run
Restart=on-failure
RestartSec=60
KillSignal=SIGINT
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''


def main():
    parser = argparse.ArgumentParser(description='Debian systemd 定时提醒服务管理（安装不自动启动）')
    parser.add_argument('action', choices=['render', 'install', 'start', 'stop', 'restart', 'status', 'logs'])
    parser.add_argument('--user', help='render/install 必须指定运行服务的现有非 root 用户')
    args = parser.parse_args()
    if args.action in ('render', 'install'):
        if not args.user:
            parser.error('请使用 --user 指定运行用户')
        try:
            unit = render(ROOT, args.user)
        except (KeyError, ValueError) as exc:
            parser.error(str(exc))
        if args.action == 'render':
            print(unit, end='')
            return
        if os.geteuid() != 0:
            parser.error('安装到 /etc/systemd/system 需要 sudo；render 可无需 sudo 预览。')
        python = ROOT / '.venv/bin/python'
        if not python.is_file() or not (ROOT / '.env').is_file():
            parser.error('请先运行 uv sync --locked 并配置 .env。')
        # Validate permissions/configuration as the actual service user, without sending.
        subprocess.run(['runuser', '-u', args.user, '--', str(python), '-m',
                        'educoder_reminder.remind', 'check'], cwd=ROOT, check=True)
        subprocess.run(['runuser', '-u', args.user, '--', str(python), '-c',
                        'from pathlib import Path; p=Path("data"); p.mkdir(mode=0o700,exist_ok=True); '
                        'import tempfile; f=tempfile.TemporaryFile(dir=p); f.close()'], cwd=ROOT, check=True)
        target = Path('/etc/systemd/system') / NAME
        target.write_text(unit)
        target.chmod(0o644)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        print('服务已安装，尚未启动。启动并设置开机运行：sudo python3 scripts/service.py start')
        return
    if args.action == 'logs':
        subprocess.run(['journalctl', '-u', NAME, '-n', '100', '-f'], check=True)
    elif args.action == 'start':
        subprocess.run(['systemctl', 'enable', '--now', NAME], check=True)
    elif args.action == 'stop':
        subprocess.run(['systemctl', 'disable', '--now', NAME], check=True)
    elif args.action == 'status':
        raise SystemExit(subprocess.run(['systemctl', 'status', '--no-pager', NAME]).returncode)
    else:
        subprocess.run(['systemctl', 'restart', NAME], check=True)


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit('服务管理命令失败，请检查上方错误和运行权限。') from None
    except KeyboardInterrupt:
        pass
