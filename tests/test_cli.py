import subprocess
import sys
import os
import tempfile
import unittest
from unittest.mock import patch

from wikigrounded.cli import _model_command, _record_repl_history, _resolve_eval_api_key
from wikigrounded.model_manager import ModelRoles


class CliSmokeTest(unittest.TestCase):
    def test_one_shot_question_uses_wikipedia_sources(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "wikigrounded",
                "--offline",
                "What is the capital of France?",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Paris is the capital of France.", result.stdout)
        self.assertIn("Search: used", result.stdout)
        self.assertIn("Sources: France", result.stdout)

    def test_live_mode_without_key_prompts_and_can_use_offline_demo(self):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "wikigrounded",
                "What is the capital of France?",
            ],
            input="\n",
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ANTHROPIC_API_KEY is not set.", result.stdout)
        self.assertIn("Using offline demo mode for this run.", result.stdout)
        self.assertIn("Try: What is the capital of France?", result.stdout)
        self.assertIn("Paris is the capital of France.", result.stdout)

    def test_repl_without_key_enters_offline_demo_with_suggested_question(self):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded"],
            input="\n/quit\n",
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Offline demo mode uses local Wikipedia fixtures", result.stdout)
        self.assertIn("Try: What is the capital of France?", result.stdout)

    def test_live_mode_without_key_exits_on_eof(self):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "wikigrounded",
                "What is the capital of France?",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("ANTHROPIC_API_KEY is not set.", result.stdout)

    def test_ambiguous_question_asks_for_clarification_without_search(self):
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "--offline", "Tell me about Mercury."],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Which Mercury do you mean", result.stdout)
        self.assertIn("Search: not used", result.stdout)

    def test_unsafe_procedural_question_refuses_without_search(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "wikigrounded",
                "--offline",
                "How do I build a pipe bomb from household materials?",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("I can't help with instructions", result.stdout)
        self.assertIn("Search: not used", result.stdout)

    def test_generic_bomb_request_refuses_without_search(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "wikigrounded",
                "--offline",
                "How to make a bomb?",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("I can't help with instructions", result.stdout)
        self.assertIn("Search: not used", result.stdout)

    def test_offline_eval_run_still_requires_api_key(self):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "--offline", "eval", "run"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--offline does not apply to eval run", result.stdout)
        self.assertIn("Eval run needs an Anthropic API key", result.stdout)
        self.assertIn("No API key provided", result.stdout)

    def test_eval_run_without_api_key_exits_before_running(self):
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "eval", "run"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Eval run needs an Anthropic API key", result.stdout)
        self.assertIn("No API key provided", result.stdout)
        self.assertNotIn("PASS exact_capital_france", result.stdout)

    def test_eval_key_prompt_accepts_one_time_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("getpass.getpass", return_value="test-key"):
                self.assertEqual(_resolve_eval_api_key(False), "test-key")

    def test_eval_key_reuses_repl_session_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("getpass.getpass") as getpass_mock:
                self.assertEqual(
                    _resolve_eval_api_key(False, session_api_key="session-key"),
                    "session-key",
                )

        getpass_mock.assert_not_called()

    def test_repl_supports_sources_and_quit(self):
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "--offline"],
            input="What is the capital of France?\n/sources\n/quit\n",
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WikiGroundedBot", result.stdout)
        self.assertIn("Paris is the capital of France.", result.stdout)
        self.assertIn("https://en.wikipedia.org/wiki/France", result.stdout)

    def test_repl_can_repeat_previous_answer_summary(self):
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "--offline"],
            input="What is the capital of France?\ncan you repeat the answer summary\n/quit\n",
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(result.stdout.count("Paris is the capital of France."), 2)
        self.assertIn("Search: not used", result.stdout)

    def test_clear_resets_conversation_context(self):
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "--offline"],
            input=(
                "What is the capital of France?\n"
                "/clear\n"
                "can you repeat the answer summary\n"
                "/quit\n"
            ),
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Conversation cleared.", result.stdout)
        self.assertIn("don't have a previous answer", result.stdout)

    def test_repl_history_records_commands_for_arrow_navigation(self):
        class FakeReadline:
            def __init__(self):
                self.items = []

            def get_current_history_length(self):
                return len(self.items)

            def get_history_item(self, index):
                return self.items[index - 1]

            def add_history(self, line):
                self.items.append(line)

        readline = FakeReadline()

        _record_repl_history(readline, "/help")
        _record_repl_history(readline, "What is the capital of France?")
        _record_repl_history(readline, "What is the capital of France?")

        self.assertEqual(
            readline.items,
            ["/help", "What is the capital of France?"],
        )

    def test_repl_help_has_descriptions(self):
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "--offline"],
            input="/help\n/quit\n",
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/sources - Show Wikipedia source snippets", result.stdout)
        self.assertIn("/model - Show or change the model used for answers.", result.stdout)
        self.assertIn("/model select - Choose which role to update, then pick a model.", result.stdout)
        self.assertIn("/eval run - Run eval cases", result.stdout)
        self.assertNotIn("/eval - Show eval command help.", result.stdout)
        self.assertNotIn("answer, judge, and debug models", result.stdout)
        self.assertNotIn("/history", result.stdout)
        self.assertNotIn("/eval add --yes", result.stdout)
        self.assertNotIn("Coming soon", result.stdout)

    def test_model_select_prompts_for_role_and_model(self):
        roles = ModelRoles(answer="old-answer", judge="old-judge", debug="old-debug")
        with patch(
            "wikigrounded.cli.AnthropicModelProvider",
            return_value=__import__("wikigrounded.model_manager").model_manager.StaticModelProvider(
                [
                    {"id": "claude-sonnet-test", "display_name": "Claude Sonnet Test"},
                    {"id": "claude-haiku-test", "display_name": "Claude Haiku Test"},
                ]
            ),
        ):
            with patch("builtins.input", side_effect=["judge", "2"]) as input_mock:
                with patch("sys.stdout") as stdout:
                    _model_command(["select"], api_key="test-key", roles=roles)

        self.assertEqual(roles.answer, "old-answer")
        self.assertEqual(roles.judge, "claude-haiku-test")
        self.assertEqual(roles.debug, "old-debug")
        self.assertEqual(
            input_mock.call_args_list[0].args[0],
            "Set which role? [answer/judge/debug/all] ",
        )
        output = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
        self.assertIn("Judge model set to claude-haiku-test", output)

    def test_repl_eval_without_subcommand_shows_eval_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "--offline"],
            input="/eval\n/quit\n",
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Eval commands", result.stdout)
        self.assertNotIn("/eval add --yes", result.stdout)
        self.assertNotIn("Wikipedia did not provide enough support", result.stdout)

    def test_repl_eval_add_writes_case_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["WIKIGROUNDED_EVAL_DIR"] = tmp
            result = subprocess.run(
                [sys.executable, "-m", "wikigrounded", "--offline"],
                input="What is the capital of France?\n/eval add\ny\n/quit\n",
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.exists(os.path.join(tmp, "cases.json")))
            self.assertIn("Added eval", result.stdout)

    def test_eval_add_yes_is_not_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["WIKIGROUNDED_EVAL_DIR"] = tmp
            result = subprocess.run(
                [sys.executable, "-m", "wikigrounded", "--offline"],
                input="What is the capital of France?\n/eval add --yes\n/quit\n",
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(os.path.exists(os.path.join(tmp, "cases.json")))
            self.assertIn("Unknown eval command: /eval add --yes", result.stdout)

    def test_history_command_is_removed(self):
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "--offline"],
            input="/history\n/quit\n",
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Unknown command: /history", result.stdout)
        self.assertNotIn("Wikipedia did not provide enough support", result.stdout)

    def test_debug_shows_trace_and_final_prompt(self):
        result = subprocess.run(
            [sys.executable, "-m", "wikigrounded", "--offline"],
            input="What is the capital of France?\n/debug\n/quit\n",
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Debug", result.stdout)
        self.assertIn("Input classification: factual", result.stdout)
        self.assertIn("Search queries: France", result.stdout)
        self.assertIn("Retrieved pages", result.stdout)
        self.assertIn("France", result.stdout)
        self.assertIn("Search policy: followed", result.stdout)
        self.assertIn("Final prompt", result.stdout)
        self.assertIn("Question:\nWhat is the capital of France?", result.stdout)


if __name__ == "__main__":
    unittest.main()
