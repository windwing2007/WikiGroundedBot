from __future__ import annotations

import os
import sys


class TerminalUI:
    def __init__(self, color: bool | None = None, clear: bool | None = None) -> None:
        if color is None:
            color = sys.stdout.isatty() and not os.getenv("NO_COLOR")
        if clear is None:
            clear = sys.stdout.isatty() and sys.stdin.isatty()
        self.color_enabled = color
        self.clear_enabled = clear

    def clear_screen(self) -> str:
        return "\033[2J\033[H" if self.clear_enabled else ""

    def system(self, text: str) -> str:
        return self._style(text, "1;36")

    def user_prompt(self, text: str) -> str:
        return self._style(text, "1;34")

    def answer_label(self, text: str) -> str:
        return self._style(text, "1;32")

    def meta(self, text: str) -> str:
        return self._style(text, "2;37")

    def error(self, text: str) -> str:
        return self._style(text, "1;31")

    def command(self, text: str) -> str:
        return self._style(text, "1;33")

    def _style(self, text: str, code: str) -> str:
        if not self.color_enabled:
            return text
        return f"\033[{code}m{text}\033[0m"
