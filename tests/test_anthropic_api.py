import copy
import unittest
from unittest.mock import patch

from wikigrounded.anthropic_api import AnthropicAnswerer
from wikigrounded.models import WikiEvidence


class AnthropicAnswererTest(unittest.TestCase):
    def test_final_answer_call_does_not_expose_unhandled_tools(self):
        captured = {}

        def fake_post(api_key, url, body):
            captured["body"] = body
            return {"content": [{"type": "text", "text": "Use clear instructions."}]}

        evidence = [
            WikiEvidence(
                title="Prompt engineering",
                url="https://en.wikipedia.org/wiki/Prompt_engineering",
                extract="Prompt engineering is the process of structuring text for a generative AI model.",
            )
        ]

        with patch("wikigrounded.anthropic_api._anthropic_post", fake_post):
            answer = AnthropicAnswerer("test-key", "claude-test").answer(
                "How to write a good prompt?",
                evidence,
            )

        self.assertEqual(answer, "Use clear instructions.")
        self.assertNotIn("tools", captured["body"])

    def test_empty_model_text_returns_clear_fallback(self):
        with patch(
            "wikigrounded.anthropic_api._anthropic_post",
            return_value={"content": [{"type": "tool_use", "name": "search_wikipedia"}]},
        ):
            answer = AnthropicAnswerer("test-key", "claude-test").answer(
                "How to write a good prompt?",
                [],
            )

        self.assertIn("couldn't generate an answer", answer)

    def test_tool_loop_allows_multiple_model_chosen_searches(self):
        calls = []

        def fake_post(api_key, url, body):
            calls.append(copy.deepcopy(body))
            if len(calls) == 1:
                return {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "search_wikipedia",
                            "input": {"query": "Oxygen-evolving complex"},
                        }
                    ]
                }
            if len(calls) == 2:
                return {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_2",
                            "name": "search_wikipedia",
                            "input": {"query": "Photosystem II"},
                        }
                    ]
                }
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Manganese is the heaviest mentioned cofactor.",
                    }
                ]
            }

        def fake_search(query):
            return [
                WikiEvidence(
                    title=query,
                    url=f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}",
                    extract=f"{query} evidence.",
                )
            ]

        with patch("wikigrounded.anthropic_api._anthropic_post", fake_post):
            result = AnthropicAnswerer(
                "test-key",
                "claude-test",
                max_tool_rounds=3,
            ).answer_with_tools(
                "Complex question",
                fake_search,
            )

        self.assertEqual(
            [call.arguments["query"] for call in result.tool_calls],
            ["Oxygen-evolving complex", "Photosystem II"],
        )
        self.assertEqual(
            [source.title for source in result.sources],
            ["Oxygen-evolving complex", "Photosystem II"],
        )
        self.assertIn("Manganese", result.answer)
        self.assertIn("tools", calls[0])
        self.assertIn("tool_result", calls[1]["messages"][-1]["content"][0]["type"])

    def test_tool_loop_initial_user_message_is_only_context_and_question(self):
        calls = []

        def fake_post(api_key, url, body):
            calls.append(body)
            return {"content": [{"type": "text", "text": "Paris."}]}

        with patch("wikigrounded.anthropic_api._anthropic_post", fake_post):
            result = AnthropicAnswerer("test-key", "claude-test").answer_with_tools(
                "can you repeat the answer summary",
                lambda query: [],
            )

        first_message = calls[0]["messages"][0]["content"]
        self.assertEqual(first_message, "Question:\ncan you repeat the answer summary")
        self.assertNotIn("Answer the question using Wikipedia evidence", first_message)
        self.assertIn("Use the search_wikipedia tool by default", calls[0]["system"])
        self.assertIn("Examples:", calls[0]["system"])
        self.assertIn('"prompt_version"', result.final_prompt)

    def test_tool_loop_reprompts_when_searchable_answer_skips_tool(self):
        calls = []

        def fake_post(api_key, url, body):
            calls.append(copy.deepcopy(body))
            if len(calls) == 1:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "I wasn't able to find Wikipedia information.",
                        }
                    ]
                }
            if len(calls) == 2:
                return {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "search_wikipedia",
                            "input": {"query": "zzqplm nonexistent topic 184729"},
                        }
                    ]
                }
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Wikipedia returned no results for that query.",
                    }
                ]
            }

        with patch("wikigrounded.anthropic_api._anthropic_post", fake_post):
            result = AnthropicAnswerer("test-key", "claude-test").answer_with_tools(
                "zzqplm nonexistent topic 184729",
                lambda query: [],
            )

        self.assertEqual(
            [call.arguments["query"] for call in result.tool_calls],
            ["zzqplm nonexistent topic 184729"],
        )
        self.assertIn("no results", result.answer.casefold())
        self.assertIn("You need to call search_wikipedia", calls[1]["messages"][-1]["content"])

    def test_tool_loop_does_not_reprompt_repeat_request_without_search(self):
        calls = []

        def fake_post(api_key, url, body):
            calls.append(body)
            return {"content": [{"type": "text", "text": "Paris is the capital of France."}]}

        with patch("wikigrounded.anthropic_api._anthropic_post", fake_post):
            result = AnthropicAnswerer("test-key", "claude-test").answer_with_tools(
                "can you repeat the answer summary",
                lambda query: [],
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(result.tool_calls, [])


if __name__ == "__main__":
    unittest.main()
