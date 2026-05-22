import json
import tempfile
import unittest
from pathlib import Path

from wikigrounded.agent import WikiGroundedBot
from wikigrounded.evals.runner import EvalRunner
from wikigrounded.models import AnswerResult, AnswerTrace
from wikigrounded.wiki import FixtureWikipediaClient, WikipediaClient


class RateLimitedWikipediaClient(WikipediaClient):
    def search_wikipedia(self, query):
        raise RuntimeError("MediaWiki request failed: HTTP Error 429: Too Many Requests")


class FakeBot:
    def __init__(self, answer: str) -> None:
        self.answer_text = answer
        self.questions = []

    def answer(self, question: str):
        self.questions.append(question)
        trace = AnswerTrace(
            question=question,
            answer=self.answer_text,
            search_used=True,
        )
        return AnswerResult(self.answer_text, True, [], trace)


class EvalRunnerTest(unittest.TestCase):
    def test_exact_groundtruth_case_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "exact_capital_france",
                            "suite": "exact_groundtruth",
                            "question": "What is the capital of France?",
                            "expect_search": True,
                            "expected_answer": {"type": "contains", "value": "Paris"},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(WikiGroundedBot(FixtureWikipediaClient()))

            result = runner.run_file(cases_path)

        self.assertEqual(result.total, 1)
        self.assertEqual(result.passed, 1)
        self.assertTrue(result.cases[0]["pass"])

    def test_rate_limited_retrieval_fails_case_without_aborting_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "rate_limited_case",
                            "suite": "retrieval_errors",
                            "question": "What is the capital of France?",
                            "expect_search": True,
                            "expected_answer": {"type": "contains", "value": "Paris"},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(WikiGroundedBot(RateLimitedWikipediaClient()))

            result = runner.run_file(cases_path)

        self.assertEqual(result.total, 1)
        self.assertEqual(result.passed, 0)
        self.assertFalse(result.cases[0]["pass"])
        self.assertIn("HTTP Error 429", result.cases[0]["failure_reason"])
        self.assertIn("Wikipedia search failed", result.cases[0]["answer"])

    def test_run_file_reports_each_case_as_it_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "exact_capital_france",
                            "suite": "exact_groundtruth",
                            "question": "What is the capital of France?",
                            "expect_search": True,
                            "expected_answer": {"type": "contains", "value": "Paris"},
                        },
                        {
                            "id": "ambiguous_mercury",
                            "suite": "ambiguity",
                            "question": "Tell me about Mercury.",
                            "expect_search": False,
                            "expected_answer": {"type": "contains", "value": "Which Mercury"},
                        },
                    ]
                ),
                encoding="utf-8",
            )
            seen = []
            runner = EvalRunner(WikiGroundedBot(FixtureWikipediaClient()))

            result = runner.run_file(cases_path, on_case_result=seen.append)

        self.assertEqual(result.total, 2)
        self.assertEqual([case["case_id"] for case in seen], ["exact_capital_france", "ambiguous_mercury"])
        self.assertTrue(all(case["pass"] for case in seen))

    def test_expected_retrieval_mode_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "late_evidence",
                            "suite": "retrieval_errors",
                            "question": "Which honor did Example Person receive late in life?",
                            "expect_search": True,
                            "expected_answer": {
                                "type": "contains",
                                "value": "Order of the Example",
                            },
                            "expected_retrieval_mode": "full_chunked",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(WikiGroundedBot(FixtureWikipediaClient()))

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 1)

    def test_contains_all_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "multi_question",
                            "suite": "retrieval",
                            "question": "Who wrote Hamlet, and who composed The Magic Flute?",
                            "expect_search": True,
                            "expected_answer": {
                                "type": "contains_all",
                                "values": ["Shakespeare", "Mozart"],
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(WikiGroundedBot(FixtureWikipediaClient()))

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 1)

    def test_contains_any_accepts_alternate_wording(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "no_results_wording",
                            "suite": "retrieval_errors",
                            "question": "zzqplm nonexistent topic 184729",
                            "expect_search": True,
                            "expected_answer": {
                                "type": "contains_any",
                                "values": [
                                    "did not provide enough support",
                                    "could not find",
                                    "not enough information",
                                ],
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(
                FakeBot("I could not find useful Wikipedia evidence for that topic.")
            )

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 1)

    def test_contains_checks_ignore_accents(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "spanish_answer",
                            "suite": "exact_groundtruth",
                            "question": "¿Cuál es la capital de Francia?",
                            "expected_answer": {
                                "type": "contains",
                                "value": "Paris",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(FakeBot("La capital de Francia es **París**."))

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 1)

    def test_no_results_wording_accepts_direct_no_results_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "no_results_wording",
                            "suite": "retrieval_errors",
                            "question": "zzqplm nonexistent topic 184729",
                            "expected_answer": {
                                "type": "contains_any",
                                "values": [
                                    "did not provide enough support",
                                    "no results",
                                    "no Wikipedia evidence",
                                ],
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(
                FakeBot(
                    "The Wikipedia search returned **no results** for that query. "
                    "No Wikipedia evidence exists, so I will not guess."
                )
            )

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 1)

    def test_no_results_wording_accepts_unable_to_find_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "no_results_wording",
                            "suite": "retrieval_errors",
                            "question": "zzqplm nonexistent topic 184729",
                            "expected_answer": {
                                "type": "contains_any",
                                "values": [
                                    "wasn't able to find",
                                    "no Wikipedia information",
                                    "does not appear to correspond",
                                ],
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(
                FakeBot(
                    "I wasn't able to find any Wikipedia information on this, "
                    "as it does not appear to correspond to any real topic."
                )
            )

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 1)

    def test_simulated_cases_use_simulated_bot_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "simulated_edge_case",
                            "suite": "retrieval_errors",
                            "question": "Which honor did Example Person receive late in life?",
                            "simulated": True,
                            "expected_answer": {
                                "type": "contains",
                                "value": "Order of the Example",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            live_bot = FakeBot("live answer")
            simulated_bot = FakeBot("Order of the Example")
            runner = EvalRunner(live_bot, simulated_bot=simulated_bot)

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 1)
        self.assertEqual(live_bot.questions, [])
        self.assertEqual(simulated_bot.questions, ["Which honor did Example Person receive late in life?"])
        self.assertTrue(result.cases[0]["simulated"])

    def test_conversation_turns_are_run_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "conversation_followup",
                            "suite": "conversation",
                            "simulated": True,
                            "turns": [
                                {
                                    "question": "Who wrote Pride and Prejudice?",
                                    "expect_search": True,
                                    "expected_answer": {
                                        "type": "contains",
                                        "value": "Jane Austen",
                                    },
                                },
                                {
                                    "question": "Where was she born?",
                                    "expect_search": True,
                                    "expected_answer": {
                                        "type": "contains",
                                        "value": "Steventon",
                                    },
                                },
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(
                FakeBot("unused"),
                simulated_bot=WikiGroundedBot(FixtureWikipediaClient()),
            )

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 1)
        self.assertEqual(result.cases[0]["question"], "Where was she born?")
        self.assertEqual(len(result.cases[0]["turns"]), 2)
        self.assertTrue(all(turn["pass"] for turn in result.cases[0]["turns"]))
        self.assertIn("Jane Austen", result.cases[0]["turns"][0]["answer"])
        self.assertIn("Steventon", result.cases[0]["turns"][1]["answer"])

    def test_conversation_repeat_answer_case_does_not_search_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "conversation_repeat",
                            "suite": "conversation",
                            "turns": [
                                {
                                    "question": "What is the capital of France?",
                                    "expect_search": True,
                                    "expected_answer": {
                                        "type": "contains",
                                        "value": "Paris",
                                    },
                                },
                                {
                                    "question": "can you repeat the answer summary",
                                    "expect_search": False,
                                    "expected_answer": {
                                        "type": "contains",
                                        "value": "Paris",
                                    },
                                },
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(WikiGroundedBot(FixtureWikipediaClient()))

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 1)
        self.assertEqual(
            result.cases[0]["question"],
            "can you repeat the answer summary",
        )
        self.assertEqual(result.cases[0]["turns"][0]["search_used"], True)
        self.assertEqual(result.cases[0]["turns"][1]["search_used"], False)

    def test_conversation_case_fails_when_any_turn_expectation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "conversation_bad_setup",
                            "suite": "conversation",
                            "turns": [
                                {
                                    "question": "What is the capital of France?",
                                    "expect_search": False,
                                    "expected_answer": {
                                        "type": "contains",
                                        "value": "Paris",
                                    },
                                },
                                {
                                    "question": "can you repeat the answer summary",
                                    "expect_search": False,
                                    "expected_answer": {
                                        "type": "contains",
                                        "value": "Paris",
                                    },
                                },
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            runner = EvalRunner(WikiGroundedBot(FixtureWikipediaClient()))

            result = runner.run_file(cases_path)

        self.assertEqual(result.passed, 0)
        self.assertFalse(result.cases[0]["turns"][0]["pass"])
        self.assertTrue(result.cases[0]["turns"][1]["pass"])
        self.assertIn("Conversation turn check failed", result.cases[0]["failure_reason"])


if __name__ == "__main__":
    unittest.main()
