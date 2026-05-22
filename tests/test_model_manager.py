import os
import unittest
from unittest.mock import patch

from wikigrounded.config import Config
from wikigrounded.model_manager import ModelManager, ModelRoles, StaticModelProvider


class ModelManagerTest(unittest.TestCase):
    def test_default_roles_use_sonnet_4_6(self):
        roles = ModelRoles()

        self.assertEqual(roles.answer, "claude-sonnet-4-6")
        self.assertEqual(roles.judge, "claude-sonnet-4-6")
        self.assertEqual(roles.debug, "claude-sonnet-4-6")

    def test_env_defaults_use_sonnet_4_6(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()

        self.assertEqual(config.answer_model, "claude-sonnet-4-6")
        self.assertEqual(config.judge_model, "claude-sonnet-4-6")
        self.assertEqual(config.debug_model, "claude-sonnet-4-6")

    def test_selects_available_model_for_role(self):
        manager = ModelManager(
            StaticModelProvider(
                [
                    {"id": "claude-sonnet-test", "display_name": "Claude Sonnet Test"},
                    {"id": "claude-haiku-test", "display_name": "Claude Haiku Test"},
                ]
            )
        )

        models = manager.available_models()
        manager.set_role("judge", models[1].id)

        self.assertEqual(manager.roles.judge, "claude-haiku-test")

    def test_selects_same_model_for_all_roles(self):
        manager = ModelManager(
            StaticModelProvider(
                [
                    {"id": "claude-sonnet-test", "display_name": "Claude Sonnet Test"},
                ]
            )
        )

        manager.set_role("all", "claude-sonnet-test")

        self.assertEqual(manager.roles.answer, "claude-sonnet-test")
        self.assertEqual(manager.roles.judge, "claude-sonnet-test")
        self.assertEqual(manager.roles.debug, "claude-sonnet-test")


if __name__ == "__main__":
    unittest.main()
