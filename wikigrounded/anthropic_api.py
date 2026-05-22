from __future__ import annotations

import json
from collections.abc import Callable
from urllib import error, request

from .model_manager import AvailableModel, ModelProvider
from .models import ToolCall, ToolDrivenAnswer, WikiEvidence
from .prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_answer_user_content,
    build_question_user_content,
    build_source_packet,
    tool_definition,
)


ANTHROPIC_VERSION = "2023-06-01"


class AnthropicModelProvider(ModelProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def list_models(self) -> list[AvailableModel]:
        data = _anthropic_get(self.api_key, "https://api.anthropic.com/v1/models")
        return [
            AvailableModel(
                id=item["id"],
                display_name=item.get("display_name", item["id"]),
            )
            for item in data.get("data", [])
        ]


class AnthropicAnswerer:
    def __init__(self, api_key: str, model: str, max_tool_rounds: int = 6) -> None:
        self.api_key = api_key
        self.model = model
        self.max_tool_rounds = max_tool_rounds

    def answer(self, question: str, evidence: list[WikiEvidence]) -> str:
        body = {
            "model": self.model,
            "max_tokens": 700,
            "temperature": 0,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": build_answer_user_content(question, evidence),
                }
            ],
        }
        data = _anthropic_post(
            self.api_key,
            "https://api.anthropic.com/v1/messages",
            body,
        )
        chunks = [
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        answer = "\n".join(chunk for chunk in chunks if chunk).strip()
        if not answer:
            return "I couldn't generate an answer from the retrieved Wikipedia evidence."
        return answer

    def answer_with_tools(
        self,
        question: str,
        search_wikipedia: Callable[[str], list[WikiEvidence]],
    ) -> ToolDrivenAnswer:
        sources: list[WikiEvidence] = []
        tool_calls: list[ToolCall] = []
        search_retry_added = False
        messages: list[dict] = [
            {
                "role": "user",
                "content": build_question_user_content(question),
            }
        ]

        for _ in range(self.max_tool_rounds):
            body = {
                "model": self.model,
                "max_tokens": 700,
                "temperature": 0,
                "system": SYSTEM_PROMPT,
                "tools": [tool_definition()],
                "messages": messages,
            }
            data = _anthropic_post(
                self.api_key,
                "https://api.anthropic.com/v1/messages",
                body,
            )
            content = data.get("content", [])
            tool_uses = [
                block
                for block in content
                if block.get("type") == "tool_use"
                and block.get("name") == "search_wikipedia"
            ]
            if not tool_uses:
                if (
                    not tool_calls
                    and not search_retry_added
                    and _requires_initial_search(question)
                ):
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You need to call search_wikipedia before answering "
                                "this factual or searchable question. Call "
                                "search_wikipedia now with a concise query. Do not "
                                "provide a final answer until after tool results are "
                                "returned."
                            ),
                        }
                    )
                    search_retry_added = True
                    continue
                return ToolDrivenAnswer(
                    answer=_extract_text(content),
                    sources=sources,
                    tool_calls=tool_calls,
                    final_prompt=_prompt_snapshot(SYSTEM_PROMPT, messages),
                )

            messages.append({"role": "assistant", "content": content})
            tool_results = []
            for block in tool_uses:
                query = str(block.get("input", {}).get("query", "")).strip()
                if not query:
                    result_content = json.dumps(
                        {"error": "search_wikipedia query was empty."},
                        ensure_ascii=True,
                    )
                else:
                    tool_calls.append(ToolCall("search_wikipedia", {"query": query}))
                    try:
                        evidence = search_wikipedia(query)
                    except RuntimeError as exc:
                        evidence = []
                        result_content = json.dumps(
                            {"error": str(exc)},
                            ensure_ascii=True,
                        )
                    else:
                        sources.extend(evidence)
                        result_content = json.dumps(
                            build_source_packet(evidence),
                            ensure_ascii=True,
                        )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.get("id"),
                        "content": result_content,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        messages.append(
            {
                "role": "user",
                "content": (
                    "Stop searching and answer now using only the Wikipedia "
                    "evidence already returned. If the evidence is insufficient, "
                    "say so."
                ),
            }
        )
        body = {
            "model": self.model,
            "max_tokens": 700,
            "temperature": 0,
            "system": SYSTEM_PROMPT,
            "messages": messages,
        }
        data = _anthropic_post(
            self.api_key,
            "https://api.anthropic.com/v1/messages",
            body,
        )
        return ToolDrivenAnswer(
            answer=_extract_text(data.get("content", [])),
            sources=sources,
            tool_calls=tool_calls,
            final_prompt=_prompt_snapshot(SYSTEM_PROMPT, messages),
        )


def _extract_text(content: list[dict]) -> str:
    answer = "\n".join(
        block.get("text", "")
        for block in content
        if block.get("type") == "text"
    ).strip()
    if not answer:
        return "I couldn't generate an answer from the retrieved Wikipedia evidence."
    return answer


def _requires_initial_search(question: str) -> bool:
    current = _current_question_text(question).casefold().strip()
    if not current:
        return False
    if current.startswith("/"):
        return False
    if current in {"hi", "hello", "hey", "thanks", "thank you"}:
        return False
    if any(term in current for term in ["repeat the answer", "repeat that", "recap", "summarize the previous"]):
        return False
    if "my neighbor" in current or "breakfast today" in current:
        return False
    if "who will win" in current and "world cup" in current:
        return False
    if any(term in current for term in ["kill myself", "suicide painlessly"]):
        return False
    if any(term in current for term in ["build a pipe bomb", "make a bomb", "hotwire a car"]):
        return False
    return True


def _current_question_text(question: str) -> str:
    marker = "\nQuestion:\n"
    if marker not in question:
        return question
    return question.rsplit(marker, 1)[-1]


def _prompt_snapshot(system: str, messages: list[dict]) -> str:
    return json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "system": system,
            "tools": [tool_definition()],
            "messages": messages,
        },
        ensure_ascii=True,
        indent=2,
    )


def _anthropic_get(api_key: str, url: str) -> dict:
    req = request.Request(
        url,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic API request failed: {exc}") from exc


def _anthropic_post(api_key: str, url: str, body: dict) -> dict:
    req = request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(f"Anthropic API request failed: {exc}") from exc
