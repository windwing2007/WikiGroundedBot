import unittest

from wikigrounded.agent import WikiGroundedBot
from wikigrounded.evals.author import HeuristicEvalAuthor
from wikigrounded.wiki import FixtureWikipediaClient


class EvalAuthorTest(unittest.TestCase):
    def test_proposes_exact_eval_from_grounded_trace(self):
        bot = WikiGroundedBot(FixtureWikipediaClient())
        trace = bot.answer("What is the capital of France?").trace

        proposal = HeuristicEvalAuthor().propose(trace)

        self.assertEqual(proposal["suite"], "exact_groundtruth")
        self.assertEqual(proposal["expected_answer"]["value"], "Paris")
        self.assertGreaterEqual(proposal["author"]["confidence"], 0.9)
        self.assertEqual(proposal["author"]["needs_review"], [])


if __name__ == "__main__":
    unittest.main()
