import json
import unittest

from wikigrounded.models import WikiEvidence
from wikigrounded.prompts import (
    SYSTEM_PROMPT,
    build_answer_user_content,
    build_final_prompt,
    build_question_user_content,
    tool_definition,
)


class PromptTest(unittest.TestCase):
    def test_static_prompt_contains_search_rules_and_examples(self):
        self.assertIn("Use the search_wikipedia tool by default", SYSTEM_PROMPT)
        self.assertIn("Examples:", SYSTEM_PROMPT)
        self.assertIn("What is the capital of France?", SYSTEM_PROMPT)
        self.assertIn("Tell me about Mercury.", SYSTEM_PROMPT)
        self.assertIn("For superlatives", SYSTEM_PROMPT)
        self.assertIn("creative requests", SYSTEM_PROMPT)

    def test_recent_conversation_context_is_preserved_as_user_context(self):
        content = build_question_user_content(
            "Recent conversation:\n"
            "User: What is the capital of France?\n"
            "Assistant: Paris is the capital of France.\n\n"
            "Question:\ncan you repeat the answer summary"
        )

        self.assertTrue(content.startswith("Recent conversation:"))
        self.assertIn("Question:\ncan you repeat the answer summary", content)

    def test_regular_question_is_wrapped_as_question(self):
        content = build_question_user_content("What is the largest ocean on Earth?")

        self.assertEqual(content, "Question:\nWhat is the largest ocean on Earth?")

    def test_final_prompt_includes_static_prompt_and_evidence(self):
        prompt = build_final_prompt(
            "What is the capital of France?",
            [
                WikiEvidence(
                    title="France",
                    url="https://en.wikipedia.org/wiki/France",
                    extract="France's capital is Paris.",
                )
            ],
        )

        self.assertIn("Examples:", prompt)
        self.assertIn("Question:\nWhat is the capital of France?", prompt)
        self.assertIn("Retrieved Wikipedia evidence", prompt)
        self.assertIn("France", prompt)

    def test_answer_user_content_keeps_evidence_structured(self):
        content = build_answer_user_content(
            "What is the capital of France?",
            [
                WikiEvidence(
                    title="France",
                    url="https://en.wikipedia.org/wiki/France",
                    extract="France's capital is Paris.",
                )
            ],
        )
        packet = content.split("Retrieved Wikipedia evidence:\n", 1)[1]

        self.assertEqual(json.loads(packet)[0]["title"], "France")

    def test_tool_definition_guides_superlative_and_non_english_queries(self):
        tool = tool_definition()
        query_description = tool["input_schema"]["properties"]["query"]["description"]

        self.assertIn("targets English Wikipedia", tool["description"])
        self.assertIn("non-English user questions", tool["description"])
        self.assertIn("superlatives", tool["description"])
        self.assertIn("list/ranking pages", tool["description"])
        self.assertIn("Avoid broad category-only queries", query_description)


if __name__ == "__main__":
    unittest.main()
