from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str | None
    answer_model: str
    judge_model: str
    debug_model: str
    data_dir: Path
    eval_dir: Path

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            answer_model=os.getenv("ANTHROPIC_ANSWER_MODEL", "claude-sonnet-4-6"),
            judge_model=os.getenv("ANTHROPIC_JUDGE_MODEL", "claude-sonnet-4-6"),
            debug_model=os.getenv("ANTHROPIC_DEBUG_MODEL", "claude-sonnet-4-6"),
            data_dir=Path(os.getenv("WIKIGROUNDED_DATA_DIR", "data")),
            eval_dir=Path(os.getenv("WIKIGROUNDED_EVAL_DIR", "evals")),
        )
