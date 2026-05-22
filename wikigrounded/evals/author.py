from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from wikigrounded.models import AnswerTrace


class HeuristicEvalAuthor:
    """Local eval proposal author with the same shape as an LLM author."""

    def propose(self, trace: AnswerTrace, expected: str | None = None) -> dict[str, Any]:
        expected_value = expected or _extract_expected(trace.answer)
        if expected_value:
            suite = "exact_groundtruth"
            expected_answer = {
                "type": "contains",
                "value": expected_value,
                "source": "user" if expected else "retrieved_source",
            }
            confidence = 0.95 if trace.sources else 0.7
            needs_review: list[str] = [] if trace.sources else ["No retrieved source."]
        else:
            suite = "judge_grounded"
            expected_answer = {"type": "judge"}
            confidence = 0.6
            needs_review = ["No stable exact answer identified."]

        return {
            "id": _case_id(trace.question),
            "suite": suite,
            "question": trace.question,
            "expect_search": trace.search_used,
            "expected_answer": expected_answer,
            "author": {
                "method": "heuristic",
                "confidence": confidence,
                "needs_review": needs_review,
                "trace": asdict(trace),
            },
        }


def _extract_expected(answer: str) -> str | None:
    if "Paris" in answer:
        return "Paris"
    if "Jane Austen" in answer:
        return "Jane Austen"
    return None


def _case_id(question: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", question.lower()).strip("_")
    return slug[:60] or "generated_eval"
