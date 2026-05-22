from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from .models import AnswerTrace


class TraceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, trace: AnswerTrace) -> Path:
        slug = _slug(trace.question) or "turn"
        path = self.root / f"{slug}.json"
        path.write_text(json.dumps(asdict(trace), indent=2), encoding="utf-8")
        return path


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:80]
