from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any

from wikigrounded.agent import WikiGroundedBot


@dataclass(frozen=True)
class EvalRunResult:
    total: int
    passed: int
    cases: list[dict[str, Any]]


class EvalRunner:
    def __init__(
        self,
        bot: WikiGroundedBot,
        simulated_bot: WikiGroundedBot | None = None,
    ) -> None:
        self.bot = bot
        self.simulated_bot = simulated_bot

    def run_file(
        self,
        cases_path: Path,
        on_case_result: Callable[[dict[str, Any]], None] | None = None,
    ) -> EvalRunResult:
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        results = []
        for case in cases:
            result = self._run_case(case)
            results.append(result)
            if on_case_result:
                on_case_result(result)
        return EvalRunResult(
            total=len(results),
            passed=sum(1 for result in results if result["pass"]),
            cases=results,
        )

    def _run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        question = _case_question(case)
        try:
            bot = self.simulated_bot if case.get("simulated") else self.bot
            if bot is None:
                raise RuntimeError("Simulated eval case has no simulated bot.")
            if hasattr(bot, "reset"):
                bot.reset()
            answer, turn_results = self._answer_case(bot, case)
        except Exception as exc:
            return {
                "case_id": case.get("id"),
                "suite": case.get("suite"),
                "question": question,
                "simulated": bool(case.get("simulated")),
                "answer": "",
                "search_used": False,
                "retrieved_sources": [],
                "turns": [],
                "pass": False,
                "failure_reason": str(exc),
                "error": str(exc),
            }

        case_checks = _checks_for_answer(answer, case)
        checked_turns = [
            turn for turn in turn_results if turn["checks"]
        ]
        checks = case_checks + [
            bool(turn["pass"]) for turn in checked_turns
        ]
        passed = False if answer.trace.error else all(checks) if checks else bool(answer.answer)
        failure_reason = answer.trace.error
        if not failure_reason and not passed:
            failed_turns = [
                str(turn["index"])
                for turn in checked_turns
                if not turn["pass"]
            ]
            if failed_turns:
                failure_reason = "Conversation turn check failed: " + ", ".join(failed_turns)
            else:
                failure_reason = "One or more checks failed."
        return {
            "case_id": case.get("id"),
            "suite": case.get("suite"),
            "question": question,
            "simulated": bool(case.get("simulated")),
            "answer": answer.answer,
            "search_used": answer.search_used,
            "retrieved_sources": [source.title for source in answer.sources],
            "turns": turn_results,
            "pass": passed,
            "failure_reason": None if passed else failure_reason,
            "error": answer.trace.error,
        }

    def _answer_case(self, bot, case: dict[str, Any]):
        turns = case.get("turns")
        if not turns:
            answer = bot.answer(case["question"])
            return answer, []
        answer = None
        turn_results = []
        for index, turn in enumerate(turns, start=1):
            answer = bot.answer(turn["question"])
            checks = _checks_for_answer(answer, turn)
            passed = False if answer.trace.error else all(checks) if checks else True
            turn_results.append(
                {
                    "index": index,
                    "question": turn["question"],
                    "answer": answer.answer,
                    "search_used": answer.search_used,
                    "retrieved_sources": [source.title for source in answer.sources],
                    "checks": checks,
                    "pass": passed,
                    "error": answer.trace.error,
                }
            )
        if answer is None:
            raise RuntimeError("Conversation eval case has no turns.")
        return answer, turn_results


def _case_question(case: dict[str, Any]) -> str:
    if "question" in case:
        return str(case["question"])
    turns = case.get("turns") or []
    if turns:
        return str(turns[-1].get("question", ""))
    return ""


def _normalize_match_text(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _checks_for_answer(answer, spec: dict[str, Any]) -> list[bool]:
    checks: list[bool] = []
    if "expect_search" in spec:
        checks.append(answer.search_used is bool(spec["expect_search"]))

    expected = spec.get("expected_answer")
    normalized_answer = _normalize_match_text(answer.answer)
    if expected and expected.get("type") == "contains":
        checks.append(_normalize_match_text(expected["value"]) in normalized_answer)
    if expected and expected.get("type") == "contains_any":
        checks.append(
            any(
                _normalize_match_text(value) in normalized_answer
                for value in expected.get("values", [])
            )
        )
    if expected and expected.get("type") == "contains_all":
        checks.append(
            all(
                _normalize_match_text(value) in normalized_answer
                for value in expected.get("values", [])
            )
        )

    if spec.get("expected_retrieval_mode"):
        checks.append(
            any(
                source.retrieval_mode == spec["expected_retrieval_mode"]
                for source in answer.sources
            )
        )
    return checks
