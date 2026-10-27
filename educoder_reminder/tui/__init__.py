"""Textual 版 Educoder 控制台 TUI。"""

from .data import ROOT, DATA_DIR

__all__ = ['ROOT', 'DATA_DIR', 'main']


def main() -> None:
    from .__main__ import main as _main
    _main()
