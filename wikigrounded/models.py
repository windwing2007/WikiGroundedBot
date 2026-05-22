from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class WikiEvidence:
    title: str
    url: str
    extract: str
    page_id: int | None = None
    last_revid: int | None = None
    section: str | None = None
    retrieval_mode: str = "intro"
    score: float = 1.0
    truncated: bool = False


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, str]


@dataclass
class AnswerTrace:
    question: str
    answer: str
    search_used: bool
    sources: list[WikiEvidence] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_version: str | None = None
    final_prompt: str | None = None
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    search_used: bool
    sources: list[WikiEvidence]
    trace: AnswerTrace


@dataclass(frozen=True)
class ToolDrivenAnswer:
    answer: str
    sources: list[WikiEvidence]
    tool_calls: list[ToolCall]
    final_prompt: str | None = None
    error: str | None = None
