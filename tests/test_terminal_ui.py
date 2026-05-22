import unittest

from wikigrounded.terminal_ui import TerminalUI


class TerminalUITest(unittest.TestCase):
    def test_color_styles_can_be_forced(self):
        ui = TerminalUI(color=True, clear=True)

        self.assertIn("\033[", ui.system("WikiGroundedBot"))
        self.assertIn("\033[", ui.user_prompt("> "))
        self.assertIn("\033[2J\033[H", ui.clear_screen())

    def test_plain_mode_has_no_escape_sequences(self):
        ui = TerminalUI(color=False, clear=False)

        self.assertEqual(ui.system("WikiGroundedBot"), "WikiGroundedBot")
        self.assertEqual(ui.user_prompt("> "), "> ")
        self.assertEqual(ui.clear_screen(), "")


if __name__ == "__main__":
    unittest.main()
