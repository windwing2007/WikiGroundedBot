import unittest

from wikigrounded.agent import WikiGroundedBot
from wikigrounded.models import ToolCall, ToolDrivenAnswer
from wikigrounded.wiki import FixtureWikipediaClient, MediaWikiClient


class RetrievalTest(unittest.TestCase):
    def test_late_section_evidence_uses_full_chunked_mode(self):
        evidence = FixtureWikipediaClient().search_wikipedia(
            "Which honor did Example Person receive late in life?"
        )

        self.assertTrue(evidence)
        self.assertEqual(evidence[0].title, "Example Person")
        self.assertEqual(evidence[0].retrieval_mode, "full_chunked")
        self.assertIn("Order of the Example", evidence[0].extract)

    def test_mediawiki_prefers_direct_title_match(self):
        class FakeMediaWiki(MediaWikiClient):
            def _get_json(self, url: str) -> dict:
                if "titles=France" in url:
                    return {
                        "query": {
                            "pages": {
                                "5843419": {
                                    "title": "France",
                                    "fullurl": "https://en.wikipedia.org/wiki/France",
                                    "extract": "France's capital is Paris.",
                                    "lastrevid": 1,
                                }
                            }
                        }
                    }
                return {"query": {"search": []}}

        evidence = FakeMediaWiki(min_request_interval=0).search_wikipedia("France")

        self.assertEqual(evidence[0].title, "France")

    def test_mediawiki_reuses_cached_responses(self):
        class FakeMediaWiki(MediaWikiClient):
            def __init__(self):
                super().__init__(min_request_interval=0)
                self.calls = 0

            def _throttle(self) -> None:
                return None

            def _get_json(self, url: str) -> dict:
                if url in self._cache:
                    return self._cache[url]
                self.calls += 1
                data = {
                    "query": {
                        "pages": {
                            "5843419": {
                                "title": "France",
                                "fullurl": "https://en.wikipedia.org/wiki/France",
                                "extract": "France's capital is Paris.",
                                "lastrevid": 1,
                            }
                        }
                    }
                }
                self._cache[url] = data
                return data

        client = FakeMediaWiki()

        client.search_wikipedia("France")
        client.search_wikipedia("France")

        self.assertEqual(client.calls, 1)

    def test_prompt_writing_query_retrieves_prompt_engineering(self):
        evidence = FixtureWikipediaClient().search_wikipedia("Prompt engineering")

        self.assertTrue(evidence)
        self.assertEqual(evidence[0].title, "Prompt engineering")

    def test_prompt_writing_question_searches_prompt_engineering(self):
        result = WikiGroundedBot(FixtureWikipediaClient()).answer(
            "How to write a good prompt?"
        )

        self.assertTrue(result.search_used)
        self.assertEqual(
            result.trace.tool_calls[0].arguments["query"],
            "Prompt engineering",
        )
        self.assertIn("Prompt engineering", [source.title for source in result.sources])
        self.assertIn("prompt", result.answer.lower())

    def test_long_oxygen_evolving_complex_question_uses_entity_query(self):
        result = WikiGroundedBot(FixtureWikipediaClient()).answer(
            "Of all the chemical elements listed in the periodic table, which is "
            "the heaviest element explicitly mentioned as a required cofactor in "
            "the core oxygen-evolving complex text, and which liquid besides water "
            "is noted as being entirely excluded from this reaction zone?"
        )

        self.assertTrue(result.search_used)
        self.assertEqual(
            result.trace.tool_calls[0].arguments["query"],
            "Oxygen-evolving complex",
        )
        self.assertIn(
            "Oxygen-evolving complex",
            [source.title for source in result.sources],
        )
        self.assertIn("manganese", result.answer.lower())

    def test_multiple_questions_use_combined_entity_query(self):
        result = WikiGroundedBot(FixtureWikipediaClient()).answer(
            "Who wrote Hamlet, and who composed The Magic Flute?"
        )

        self.assertTrue(result.search_used)
        self.assertEqual(
            result.trace.tool_calls[0].arguments["query"],
            "Hamlet The Magic Flute",
        )
        self.assertIn("Hamlet", [source.title for source in result.sources])
        self.assertIn("The Magic Flute", [source.title for source in result.sources])
        self.assertIn("Shakespeare", result.answer)
        self.assertIn("Mozart", result.answer)

    def test_open_ended_grounded_generation_searches_anchor_entities(self):
        result = WikiGroundedBot(FixtureWikipediaClient()).answer(
            "Write a short poem for the largest ocean and the highest mountain."
        )

        self.assertTrue(result.search_used)
        self.assertEqual(
            result.trace.tool_calls[0].arguments["query"],
            "Pacific Ocean Mount Everest",
        )
        self.assertIn("Pacific Ocean", [source.title for source in result.sources])
        self.assertIn("Mount Everest", [source.title for source in result.sources])
        self.assertIn("Pacific", result.answer)
        self.assertIn("Everest", result.answer)

    def test_non_english_question_searches_wikipedia(self):
        result = WikiGroundedBot(FixtureWikipediaClient()).answer(
            "¿Cuál es la capital de Francia?"
        )

        self.assertTrue(result.search_used)
        self.assertEqual(result.trace.tool_calls[0].arguments["query"], "France")
        self.assertIn("Paris", result.answer)

    def test_followup_question_uses_recent_turn_context(self):
        bot = WikiGroundedBot(FixtureWikipediaClient())
        bot.answer("Who wrote Pride and Prejudice?")

        result = bot.answer("Where was she born?")

        self.assertTrue(result.search_used)
        self.assertEqual(result.trace.tool_calls[0].arguments["query"], "Jane Austen")
        self.assertIn("Steventon", result.answer)
        self.assertIn("Recent conversation:", result.trace.final_prompt)
        self.assertIn("Who wrote Pride and Prejudice?", result.trace.final_prompt)

    def test_repeat_previous_answer_uses_conversation_context_without_search(self):
        bot = WikiGroundedBot(FixtureWikipediaClient())
        bot.answer("What is the capital of France?")

        result = bot.answer("can you repeat the answer summary")

        self.assertFalse(result.search_used)
        self.assertEqual(result.trace.tool_calls, [])
        self.assertIn("Paris", result.answer)
        self.assertIn("France", [source.title for source in result.sources])

    def test_repeat_previous_answer_without_history_is_clear(self):
        result = WikiGroundedBot(FixtureWikipediaClient()).answer(
            "can you repeat the answer summary"
        )

        self.assertFalse(result.search_used)
        self.assertIn("don't have a previous answer", result.answer)

    def test_new_question_after_history_includes_context_but_uses_current_query(self):
        bot = WikiGroundedBot(FixtureWikipediaClient())
        bot.answer("Who wrote Pride and Prejudice?")

        result = bot.answer("What is the largest ocean on Earth?")

        self.assertTrue(result.search_used)
        self.assertEqual(result.trace.tool_calls[0].arguments["query"], "Pacific Ocean")
        self.assertIn("Recent conversation:", result.trace.final_prompt)
        self.assertIn("Who wrote Pride and Prejudice?", result.trace.final_prompt)
        self.assertIn("Question:\nWhat is the largest ocean on Earth?", result.trace.final_prompt)
        self.assertIn("Pacific Ocean", result.answer)

    def test_wikipedia_image_question_reports_text_only_limitation(self):
        result = WikiGroundedBot(FixtureWikipediaClient()).answer(
            "What is shown in the first image on the Wikipedia article for France?"
        )

        self.assertFalse(result.search_used)
        self.assertIn("text-only", result.answer)

    def test_tool_loop_answerer_chooses_search_query(self):
        class ToolLoopAnswerer:
            def answer_with_tools(self, question, search_wikipedia):
                evidence = search_wikipedia("Prompt engineering")
                return ToolDrivenAnswer(
                    answer="Prompt engineering evidence was used.",
                    sources=evidence,
                    tool_calls=[
                        ToolCall(
                            "search_wikipedia",
                            {"query": "Prompt engineering"},
                        )
                    ],
                    final_prompt="tool loop prompt",
                )

        result = WikiGroundedBot(
            FixtureWikipediaClient(),
            ToolLoopAnswerer(),
        ).answer("How do I write a better instruction for an AI model?")

        self.assertEqual(result.trace.tool_calls[0].arguments["query"], "Prompt engineering")
        self.assertIn("Prompt engineering", [source.title for source in result.sources])


if __name__ == "__main__":
    unittest.main()
