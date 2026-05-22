from __future__ import annotations

import argparse
import getpass
import json
from types import ModuleType
from collections.abc import Sequence

from .agent import WikiGroundedBot
from .anthropic_api import AnthropicAnswerer, AnthropicModelProvider
from .config import Config
from .evals.author import HeuristicEvalAuthor
from .evals.runner import EvalRunner
from .model_manager import ModelManager, ModelRoles, StaticModelProvider
from .terminal_ui import TerminalUI
from .trace import TraceStore
from .wiki import FixtureWikipediaClient, MediaWikiClient


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wikigrounded")
    parser.add_argument("--offline", action="store_true", help="Use local fixtures.")
    parser.add_argument("--demo", action="store_true", help="Run sample questions.")
    parser.add_argument("question", nargs="*")
    args = parser.parse_args(argv)

    if args.question[:2] == ["eval", "run"]:
        return _run_evals(_resolve_eval_api_key(args.offline))

    live_api_key = _resolve_api_key(args.offline)
    if live_api_key is None and not args.offline:
        return 2

    if args.question[:1] == ["model"]:
        return _model_command(args.question[1:], live_api_key)
    if args.demo:
        return _run_demo(args.offline, live_api_key)

    question = " ".join(args.question).strip()
    if not question:
        return _run_repl(args.offline, live_api_key)

    bot = _build_bot(args.offline, live_api_key)
    result = bot.answer(question)
    TraceStore(Config.from_env().data_dir / "traces").save(result.trace)
    print(
        _render_answer(
            result.answer,
            result.search_used,
            [s.title for s in result.sources],
            TerminalUI(),
        )
    )
    return 0


def _render_answer(
    answer: str,
    search_used: bool,
    source_titles: list[str],
    ui: TerminalUI | None = None,
) -> str:
    ui = ui or TerminalUI(color=False, clear=False)
    rendered = [ui.answer_label("Answer"), answer, ""]
    rendered.append(ui.meta(f"Search: {'used' if search_used else 'not used'}"))
    if source_titles:
        rendered.append(ui.meta("Sources: " + ", ".join(source_titles)))
    return "\n".join(rendered)


def _resolve_api_key(offline: bool) -> str | None:
    if offline:
        return None
    config = Config.from_env()
    if config.anthropic_api_key:
        return config.anthropic_api_key
    print("ANTHROPIC_API_KEY is not set.")
    try:
        api_key = input(
            "Enter Anthropic API key, or press Enter to use offline demo mode: "
        ).strip()
    except EOFError:
        print("No API key provided. Re-run with --offline for fixture mode.")
        return None
    if not api_key:
        print("Using offline demo mode for this run.")
        print(
            "Offline demo mode uses local Wikipedia fixtures and a deterministic "
            "answerer, so it works without an Anthropic API key."
        )
        print("Try: What is the capital of France?")
        return ""
    return api_key


def _resolve_eval_api_key(
    offline: bool,
    session_api_key: str | None = None,
) -> str | None:
    if session_api_key:
        return session_api_key
    config = Config.from_env()
    if config.anthropic_api_key:
        return config.anthropic_api_key
    if offline:
        print("--offline does not apply to eval run; non-simulated evals use live calls.")
    print(
        "Eval run needs an Anthropic API key because non-simulated evals use "
        "live MediaWiki and Anthropic calls."
    )
    try:
        api_key = getpass.getpass("Enter Anthropic API key for this eval run: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("No API key provided. Set ANTHROPIC_API_KEY or paste a key when prompted.")
        return None
    if not api_key:
        print("No API key provided. Set ANTHROPIC_API_KEY or paste a key when prompted.")
        return None
    return api_key


def _build_bot(offline: bool, api_key: str | None = None) -> WikiGroundedBot:
    config = Config.from_env()
    return _build_bot_with_roles(offline, api_key, _roles_from_config(config))


def _build_bot_with_roles(
    offline: bool,
    api_key: str | None,
    roles: ModelRoles,
) -> WikiGroundedBot:
    config = Config.from_env()
    if offline or api_key == "":
        return WikiGroundedBot(FixtureWikipediaClient())
    resolved_key = api_key or config.anthropic_api_key
    if not resolved_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for live mode.")
    return WikiGroundedBot(
        MediaWikiClient(),
        AnthropicAnswerer(resolved_key, roles.answer),
    )


def _roles_from_config(config: Config) -> ModelRoles:
    return ModelRoles(
        answer=config.answer_model,
        judge=config.judge_model,
        debug=config.debug_model,
    )


def _run_demo(offline: bool, api_key: str | None) -> int:
    bot = _build_bot(offline, api_key)
    ui = TerminalUI()
    for question in [
        "What is the capital of France?",
        "Tell me about Mercury.",
        "How do I build a pipe bomb from household materials?",
    ]:
        result = bot.answer(question)
        print(ui.user_prompt(f"> {question}"))
        print(
            _render_answer(
                result.answer,
                result.search_used,
                [s.title for s in result.sources],
                ui,
            )
        )
        print()
    return 0


def _run_repl(offline: bool, api_key: str | None) -> int:
    roles = _roles_from_config(Config.from_env())
    bot = _build_bot_with_roles(offline, api_key, roles)
    ui = TerminalUI()
    last_result = None
    readline_module = _setup_repl_history()
    clear = ui.clear_screen()
    if clear:
        print(clear, end="")
    print(ui.system("WikiGroundedBot"))
    print(ui.meta("Ask a question, or type /help."))
    while True:
        try:
            line = input(ui.user_prompt("> ")).strip()
        except EOFError:
            break
        if not line:
            continue
        if line in {"/quit", "/exit"}:
            break
        _record_repl_history(readline_module, line)
        if line == "/help":
            _print_help(ui)
            continue
        if line == "/sources":
            if not last_result or not last_result.sources:
                print(ui.meta("No sources for the last answer."))
            else:
                for source in last_result.sources:
                    section = f" ({source.section})" if source.section else ""
                    print(ui.command(f"- {source.title}{section}: {source.url}"))
                    print(f"  {source.extract}")
            continue
        if line == "/debug":
            if not last_result:
                print(ui.meta("No previous turn to debug."))
            else:
                _print_debug(last_result, ui)
            continue
        if line == "/clear":
            last_result = None
            bot.reset()
            print(ui.meta("Conversation cleared."))
            continue
        if line.startswith("/model"):
            _model_command(line.split()[1:], api_key, roles)
            bot = _build_bot_with_roles(offline, api_key, roles)
            continue
        if line.startswith("/eval run"):
            eval_api_key = _resolve_eval_api_key(offline, api_key)
            if eval_api_key is not None:
                _run_evals(eval_api_key, roles)
            continue
        if line == "/eval add":
            if not last_result:
                print(ui.meta("No previous turn to convert into an eval."))
                continue
            proposal = HeuristicEvalAuthor().propose(last_result.trace)
            print(json.dumps(proposal, indent=2))
            response = input("Add this eval? [y/N] ").strip().lower()
            if response == "y":
                _append_eval_case(Config.from_env().eval_dir / "cases.json", proposal)
                print(ui.meta(f"Added eval {proposal['id']}"))
            else:
                print(ui.meta("Eval not added."))
            continue
        if line.startswith("/eval add "):
            print(ui.error(f"Unknown eval command: {line}"))
            print(ui.meta("Use /eval add to review and approve a proposal."))
            continue
        if line == "/eval" or line.startswith("/eval "):
            _print_eval_help(ui)
            continue
        if line.startswith("/"):
            print(ui.error(f"Unknown command: {line.split()[0]}"))
            print(ui.meta("Type /help for available commands."))
            continue

        last_result = bot.answer(line)
        print(
            _render_answer(
                last_result.answer,
                last_result.search_used,
                [source.title for source in last_result.sources],
                ui,
            )
        )
    return 0


def _setup_repl_history() -> ModuleType | None:
    try:
        import readline
    except ImportError:
        return None

    try:
        readline.set_history_length(200)
    except AttributeError:
        pass
    return readline


def _record_repl_history(readline_module: ModuleType | None, line: str) -> None:
    if not readline_module or not line:
        return
    try:
        length = readline_module.get_current_history_length()
        if length > 0 and readline_module.get_history_item(length) == line:
            return
        readline_module.add_history(line)
    except AttributeError:
        return


def _print_help(ui: TerminalUI | None = None) -> None:
    ui = ui or TerminalUI(color=False, clear=False)
    print(ui.system("Commands"))
    print(ui.command("/help") + " - Show this command reference.")
    print(ui.command("/sources") + " - Show Wikipedia source snippets for the last answer.")
    print(ui.command("/debug") + " - Show the last turn's prompt, retrieval trace, and improvement notes.")
    print(ui.command("/model") + " - Show or change the model used for answers.")
    print(ui.command("/model select") + " - Choose which role to update, then pick a model.")
    print(ui.command("/eval run") + " - Run eval cases; simulated cases are explicitly marked.")
    print(ui.command("/eval add") + " - Propose an eval from the last answer and ask before saving.")
    print(ui.command("/clear") + " - Clear the current conversation context.")
    print(ui.command("/quit") + " - Exit the REPL.")


def _print_debug(result, ui: TerminalUI | None = None) -> None:
    ui = ui or TerminalUI(color=False, clear=False)
    trace = result.trace
    print(ui.system("Debug"))
    print(ui.meta(f"Prompt version: {trace.prompt_version or 'unknown'}"))
    print(ui.meta(f"Input classification: {_classify_question(trace.question)}"))
    print(ui.meta(f"Search used: {trace.search_used}"))
    queries = [
        call.arguments.get("query", "")
        for call in trace.tool_calls
        if call.name == "search_wikipedia"
    ]
    print(ui.meta("Search queries: " + (", ".join(queries) if queries else "none")))
    print(ui.meta(f"Search policy: {_search_policy_status(trace)}"))
    print(ui.meta("Retrieved pages"))
    if trace.sources:
        for source in trace.sources:
            section = f", section={source.section}" if source.section else ""
            print(
                ui.command(
                    f"- {source.title} ({source.retrieval_mode}{section}, "
                    f"{len(source.extract)} chars, truncated={source.truncated})"
                )
            )
    else:
        print(ui.meta("- none"))
    print(ui.meta("Unsupported claims: " + _unsupported_claim_note(trace)))
    print(ui.meta("Improvement suggestions: " + _debug_improvement(trace)))
    print(ui.meta("Final answer:"))
    print(trace.answer)
    print(ui.meta("Final prompt:"))
    print(trace.final_prompt or "No model prompt was sent for this turn.")


def _classify_question(question: str) -> str:
    lowered = question.lower()
    if question.strip().startswith("/eval"):
        return "eval command"
    if any(term in lowered for term in ["bomb", "explosive", "weapon", "kill myself", "suicide", "hotwire"]):
        return "unsafe"
    if lowered.strip(" ?.") in {"tell me about mercury", "mercury"}:
        return "ambiguous"
    if "my neighbor" in lowered or "breakfast today" in lowered:
        return "unsupported/private"
    if "who will win" in lowered:
        return "unsupported/future"
    return "factual"


def _search_policy_status(trace) -> str:
    classification = _classify_question(trace.question)
    if classification in {"unsafe", "ambiguous", "unsupported/private", "unsupported/future"}:
        return "followed" if not trace.search_used else "review"
    return "followed" if trace.search_used else "review"


def _unsupported_claim_note(trace) -> str:
    if not trace.answer:
        return "empty answer"
    if trace.search_used and not trace.sources:
        return "answer has no retrieved Wikipedia sources"
    if trace.sources:
        return "none detected by local heuristic"
    if not trace.search_used and _classify_question(trace.question) == "factual":
        return "factual answer without search"
    return "none detected by local heuristic"


def _debug_improvement(trace) -> str:
    if trace.search_used and not trace.sources:
        return "Add a fallback query rewrite or ask a clarification when Wikipedia returns no results."
    if any(source.truncated for source in trace.sources):
        return "Retrieve the most relevant section before sending long truncated extracts."
    if len(trace.sources) > 5:
        return "Limit or rerank retrieved pages before prompt assembly."
    if _classify_question(trace.question) == "ambiguous":
        return "Keep asking a short clarification before searching broad ambiguous topics."
    return "No obvious issue; keep the concise answer and source footer."


def _print_eval_help(ui: TerminalUI | None = None) -> None:
    ui = ui or TerminalUI(color=False, clear=False)
    print(ui.system("Eval commands"))
    print(ui.command("/eval run") + " - Run eval cases from evals/cases.json.")
    print(ui.command("/eval add") + " - Propose an eval from the last answer and ask before saving.")


def _append_eval_case(path, case: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    if path.exists():
        cases = json.loads(path.read_text(encoding="utf-8"))
    cases.append(
        {
            key: value
            for key, value in case.items()
            if key != "author" or isinstance(value, dict)
        }
    )
    path.write_text(json.dumps(cases, indent=2), encoding="utf-8")


def _run_evals(api_key: str | None, roles: ModelRoles | None = None) -> int:
    if api_key is None:
        return 2
    roles = roles or _roles_from_config(Config.from_env())
    config = Config.from_env()
    cases_path = config.eval_dir / "cases.json"
    if not cases_path.exists():
        print(f"No eval cases found at {cases_path}")
        return 1
    print(f"Running evals from {cases_path}...")

    def print_case(case: dict) -> None:
        status = "PASS" if case["pass"] else "FAIL"
        suffix = " [simulated]" if case.get("simulated") else ""
        print(f"{status} {case['case_id']}{suffix}")
        if case.get("error"):
            print(f"  Error: {case['error']}")

    result = EvalRunner(
        _build_bot_with_roles(api_key == "", api_key, roles),
        simulated_bot=WikiGroundedBot(FixtureWikipediaClient()),
    ).run_file(
        cases_path,
        on_case_result=print_case,
    )
    print(f"Eval result: {result.passed}/{result.total} passed")
    return 0 if result.passed == result.total else 1


def _model_command(
    args: list[str],
    api_key: str | None = None,
    roles: ModelRoles | None = None,
) -> int:
    config = Config.from_env()
    roles = roles or _roles_from_config(config)
    resolved_key = api_key or config.anthropic_api_key
    if resolved_key:
        provider = AnthropicModelProvider(resolved_key)
    else:
        provider = StaticModelProvider(
            [
                {"id": config.answer_model, "display_name": config.answer_model},
                {"id": config.judge_model, "display_name": config.judge_model},
                {"id": config.debug_model, "display_name": config.debug_model},
            ]
        )
    manager = ModelManager(
        provider,
        roles,
    )
    if args[:1] == ["select"]:
        _select_model_interactively(manager)
        return 0
    if args[:1] == ["refresh"]:
        _print_available_models(manager, refresh=True)
        return 0
    if args[:1] and args[0] in {"answer", "judge", "debug", "all"}:
        if len(args) < 2:
            print(f"Usage: /model {args[0]} MODEL_ID")
            return 1
        try:
            manager.set_role(args[0], args[1])
        except ValueError as exc:
            print(str(exc))
            return 1
        print(f"{args[0].title()} model set to {args[1]} for this session.")
        return 0
    print(f"Answer model: {manager.roles.answer}")
    print(f"Judge model:  {manager.roles.judge}")
    print(f"Debug model:  {manager.roles.debug}")
    return 0


def _select_model_interactively(manager: ModelManager) -> None:
    role = input("Set which role? [answer/judge/debug/all] ").strip().lower()
    if role not in {"answer", "judge", "debug", "all"}:
        print("Unknown role. Choose answer, judge, debug, or all.")
        return

    models = _print_available_models(manager, refresh=False)
    choice = input("Choose model number: ").strip()
    try:
        model = models[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid model selection.")
        return

    manager.set_role(role, model.id)
    print(f"{role.title()} model set to {model.id} for this session.")


def _print_available_models(
    manager: ModelManager,
    refresh: bool = False,
):
    models = manager.available_models(refresh=refresh)
    for index, model in enumerate(models, 1):
        print(f"{index}. {model.display_name}  {model.id}")
    return models
