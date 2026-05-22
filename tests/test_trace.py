import json
import tempfile
import unittest
from pathlib import Path

from wikigrounded.agent import WikiGroundedBot
from wikigrounded.trace import TraceStore
from wikigrounded.wiki import FixtureWikipediaClient


class TraceStoreTest(unittest.TestCase):
    def test_trace_store_persists_search_usage_and_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot = WikiGroundedBot(FixtureWikipediaClient())
            result = bot.answer("What is the capital of France?")

            path = TraceStore(Path(tmp)).save(result.trace)
            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(saved["search_used"])
        self.assertEqual(saved["sources"][0]["title"], "France")
        self.assertEqual(saved["tool_calls"][0]["name"], "search_wikipedia")
        self.assertEqual(saved["tool_calls"][0]["arguments"]["query"], "France")

    def test_no_results_still_records_search_used(self):
        bot = WikiGroundedBot(FixtureWikipediaClient())
        result = bot.answer("zzqplm nonexistent topic 184729")

        self.assertTrue(result.search_used)
        self.assertEqual(result.sources, [])
        self.assertEqual(result.trace.tool_calls[0].name, "search_wikipedia")


if __name__ == "__main__":
    unittest.main()
