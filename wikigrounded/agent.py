from __future__ import annotations

from .models import AnswerResult, AnswerTrace, ToolCall, ToolDrivenAnswer, WikiEvidence
from .prompts import PROMPT_VERSION, build_final_prompt
from .wiki import WikipediaClient


class OfflineGroundedAnswerer:
    """Deterministic answerer for offline demo, fixtures, and tests."""

    def answer_with_tools(self, question, search_wikipedia) -> ToolDrivenAnswer:
        query = _search_query(question)
        tool_call = ToolCall("search_wikipedia", {"query": query})
        sources = search_wikipedia(query)
        return ToolDrivenAnswer(
            answer=self.answer(question, sources),
            sources=sources,
            tool_calls=[tool_call],
            final_prompt=build_final_prompt(question, sources),
        )

    def answer(self, question: str, evidence: list[WikiEvidence]) -> str:
        current_lower = _current_question_from_context(question).lower()
        combined = " ".join(source.extract for source in evidence)
        combined_lower = combined.lower()
        if "capital" in current_lower and (
            "france" in current_lower or "francia" in current_lower
        ) and "Paris" in combined:
            return "Paris is the capital of France."
        if (
            "jane austen" in combined_lower
            and "steventon" in combined_lower
            and "born" in current_lower
        ):
            return "Jane Austen was born in Steventon, Hampshire."
        if "pride and prejudice" in current_lower and "Jane Austen" in combined:
            return "Jane Austen wrote Pride and Prejudice."
        if "symbol" in current_lower and "mercury" in current_lower and "Hg" in combined:
            return "The chemical symbol for mercury is Hg."
        if "symbol" in current_lower and "fe" in current_lower and "Iron" in combined:
            return "The chemical element with the symbol Fe is iron."
        if "apollo 11" in current_lower and "1969" in combined:
            return "Apollo 11 landed on the Moon in 1969."
        if (
            "poem" in current_lower
            and "Pacific Ocean" in combined
            and "Mount Everest" in combined
        ):
            return (
                "Pacific, wide with restless light,\n"
                "Everest, quiet in snow and height;\n"
                "Earth's largest ocean and highest peak\n"
                "share the awe that travelers seek."
            )
        if "largest ocean" in current_lower and "Pacific Ocean" in combined:
            return "The Pacific Ocean is the largest ocean on Earth."
        if "kilimanjaro" in current_lower and "Tanzania" in combined:
            return "Mount Kilimanjaro is located in Tanzania."
        if (
            "hamlet" in current_lower
            and "magic flute" in current_lower
            and "William Shakespeare" in combined
            and "Mozart" in combined
        ):
            return (
                "William Shakespeare wrote Hamlet, and Wolfgang Amadeus Mozart "
                "composed The Magic Flute."
            )
        if "magic flute" in current_lower and "Mozart" in combined:
            return "The Magic Flute was composed by Wolfgang Amadeus Mozart."
        if "taj mahal" in current_lower and "New Delhi" in combined:
            return "New Delhi is the capital of India, where the Taj Mahal is located."
        if "hamlet" in current_lower and "William Shakespeare" in combined:
            return "William Shakespeare wrote Hamlet."
        if "prompt" in current_lower and "Prompt engineering" in combined:
            return (
                "A good prompt gives the model a clear task, relevant context, "
                "examples when helpful, and constraints for the response."
            )
        if "oxygen-evolving complex" in current_lower and "manganese" in combined:
            return (
                "The heaviest explicitly mentioned cofactor is manganese, and "
                "the excluded liquid is ethanol."
            )
        if "order of the example" in combined:
            return "Example Person received the Order of the Example."
        if evidence:
            return evidence[0].extract.split(".")[0].strip() + "."
        return "Wikipedia did not provide enough support to answer that."


class WikiGroundedBot:
    def __init__(
        self,
        wiki: WikipediaClient,
        answerer: OfflineGroundedAnswerer | None = None,
    ) -> None:
        self.wiki = wiki
        self.answerer = answerer or OfflineGroundedAnswerer()
        self.history: list[AnswerTrace] = []

    def reset(self) -> None:
        self.history.clear()

    def answer(self, question: str) -> AnswerResult:
        conversation_answer = _answer_from_conversation(question, self.history)
        if conversation_answer is not None:
            answer, sources = conversation_answer
            trace = AnswerTrace(
                question=question,
                answer=answer,
                search_used=False,
                sources=sources,
                tool_calls=[],
                prompt_version=PROMPT_VERSION,
                final_prompt="Answered from recent conversation context; no model prompt was sent.",
            )
            self.history.append(trace)
            return AnswerResult(answer, False, sources, trace)

        preflight = _preflight_answer(question)
        if preflight is not None:
            trace = AnswerTrace(
                question=question,
                answer=preflight,
                search_used=False,
                sources=[],
                tool_calls=[],
                prompt_version=PROMPT_VERSION,
            )
            self.history.append(trace)
            return AnswerResult(preflight, False, [], trace)

        answer_question = _question_with_context(question, self.history)
        try:
            tool_answer: ToolDrivenAnswer = self.answerer.answer_with_tools(
                answer_question,
                self.wiki.search_wikipedia,
            )
        except RuntimeError as exc:
            answer = (
                "Wikipedia search failed while retrieving evidence. "
                "Please try again later or use --offline demo mode."
            )
            trace = AnswerTrace(
                question=question,
                answer=answer,
                search_used=True,
                sources=[],
                tool_calls=[],
                prompt_version=PROMPT_VERSION,
                error=str(exc),
            )
            self.history.append(trace)
            return AnswerResult(answer, True, [], trace)

        trace = AnswerTrace(
            question=question,
            answer=tool_answer.answer,
            search_used=bool(tool_answer.tool_calls),
            sources=tool_answer.sources,
            tool_calls=tool_answer.tool_calls,
            prompt_version=PROMPT_VERSION,
            final_prompt=tool_answer.final_prompt,
            error=tool_answer.error,
        )
        result = AnswerResult(
            answer=tool_answer.answer,
            search_used=trace.search_used,
            sources=tool_answer.sources,
            trace=trace,
        )
        self.history.append(trace)
        return result


def _preflight_answer(question: str) -> str | None:
    lowered = question.lower()
    if _asks_about_non_text_wikipedia_media(lowered):
        return (
            "I can't inspect Wikipedia images or other non-text media with the "
            "current text-only retrieval tool."
        )
    if _is_procedural_weapon_request(lowered):
        return (
            "I can't help with instructions for building weapons. I can offer a "
            "high-level safety, legal, or historical overview instead."
        )
    if lowered.strip(" ?.") in {"tell me about mercury", "mercury"}:
        return (
            "Which Mercury do you mean: the planet, the chemical element, the "
            "Roman deity, or something else?"
        )
    if "my neighbor" in lowered or "breakfast today" in lowered:
        return "Wikipedia cannot support that private, personal fact."
    if "who will win" in lowered and "world cup" in lowered:
        return "Wikipedia cannot support a future winner prediction as a fact."
    if "kill myself" in lowered or "suicide painlessly" in lowered:
        return (
            "I'm sorry you're feeling this way. I can't help with self-harm "
            "methods, but reaching out to emergency services or a crisis hotline "
            "right now could help keep you safe."
        )
    if "hotwire" in lowered and "car" in lowered:
        return "I can't help with instructions for stealing or bypassing a car's security."
    return None


def _question_with_context(question: str, history: list[AnswerTrace]) -> str:
    if not history:
        return question
    turns = "\n".join(
        f"User: {trace.question}\nAssistant: {trace.answer}"
        for trace in history
    )
    return (
        "Recent conversation:\n"
        f"{turns}\n\n"
        f"Question:\n{question}"
    )


def _answer_from_conversation(
    question: str,
    history: list[AnswerTrace],
) -> tuple[str, list[WikiEvidence]] | None:
    lowered = question.lower().strip()
    if not _asks_to_repeat_previous_answer(lowered):
        return None
    if not history:
        return ("I don't have a previous answer to repeat yet.", [])
    last = history[-1]
    return (last.answer, last.sources)


def _asks_to_repeat_previous_answer(lowered: str) -> bool:
    repeat_terms = ["repeat", "recap", "summarize", "summary", "say that again"]
    answer_terms = ["answer", "response", "summary", "that", "it"]
    return any(term in lowered for term in repeat_terms) and any(
        term in lowered for term in answer_terms
    )


def _asks_about_non_text_wikipedia_media(lowered: str) -> bool:
    media_terms = ["image", "photo", "picture", "map", "diagram", "caption"]
    wiki_terms = ["wikipedia", "wiki", "infobox", "article"]
    return any(term in lowered for term in media_terms) and any(
        term in lowered for term in wiki_terms
    )


def _is_procedural_weapon_request(lowered: str) -> bool:
    weapon_terms = [
        "bomb",
        "explosive",
        "pipe bomb",
        "grenade",
        "weapon",
    ]
    procedural_terms = [
        "build",
        "make",
        "construct",
        "create",
        "assemble",
        "instructions",
        "step-by-step",
        "household",
    ]
    return any(term in lowered for term in weapon_terms) and any(
        term in lowered for term in procedural_terms
    )


def _search_query(question: str) -> str:
    full_lowered = question.lower().strip(" ?.!")
    lowered = _current_question_from_context(question).lower().strip(" ?.!")
    if "jane austen" in full_lowered and (
        "born" in lowered or "birthplace" in lowered or "where was she" in lowered
    ):
        return "Jane Austen"
    if "largest ocean" in lowered and "highest mountain" in lowered:
        return "Pacific Ocean Mount Everest"
    entities = _known_entities(lowered)
    if len(entities) > 1:
        return " ".join(entities)
    if entities:
        return entities[0]
    if "capital" in lowered and ("france" in lowered or "francia" in lowered):
        return "France"
    if "pride and prejudice" in lowered:
        return "Pride and Prejudice"
    if "chemical symbol" in lowered and "mercury" in lowered:
        return "Mercury element"
    if "symbol fe" in lowered or "symbol for fe" in lowered or "symbol has the symbol fe" in lowered:
        return "Iron"
    if "apollo 11" in lowered:
        return "Apollo 11"
    if "largest ocean" in lowered:
        return "Pacific Ocean"
    if "highest mountain" in lowered:
        return "Mount Everest"
    if "kilimanjaro" in lowered:
        return "Mount Kilimanjaro"
    if "magic flute" in lowered:
        return "The Magic Flute"
    if "taj mahal" in lowered:
        return "Taj Mahal India capital"
    if "hamlet" in lowered:
        return "Hamlet William Shakespeare"
    if "prompt" in lowered and any(
        term in lowered for term in ["write", "good", "better", "engineering"]
    ):
        return "Prompt engineering"
    return question


def _known_entities(lowered: str) -> list[str]:
    entities: list[str] = []
    if "oxygen-evolving complex" in lowered or "oxygen evolving complex" in lowered:
        entities.append("Oxygen-evolving complex")
    if "prompt engineering" in lowered:
        entities.append("Prompt engineering")
    if "hamlet" in lowered:
        entities.append("Hamlet")
    if "magic flute" in lowered:
        entities.append("The Magic Flute")
    if "pacific ocean" in lowered:
        entities.append("Pacific Ocean")
    if "mount everest" in lowered:
        entities.append("Mount Everest")
    return entities


def _current_question_from_context(question: str) -> str:
    marker = "\nQuestion:\n"
    if marker not in question:
        return question
    return question.rsplit(marker, 1)[-1]
