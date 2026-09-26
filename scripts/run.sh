#!/usr/bin/env bash
# Run from any directory; systemd uses the locked, preinstalled uv environment.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$project_dir"
if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
    echo '缺少虚拟环境，请先在项目目录运行：uv sync --locked' >&2
    exit 1
fi
export PYTHONUNBUFFERED=1
if [[ $# -eq 0 ]]; then
    set -- run
fi
exec "$project_dir/.venv/bin/python" -m educoder_reminder.remind "$@"
