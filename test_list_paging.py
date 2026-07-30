import unittest
from unittest.mock import patch

import main


class ListPagingTests(unittest.TestCase):
    def make_words(self, count=30):
        return [
            {
                "id": index,
                "english": f"word-{index}",
                "chinese": f"释义-{index}",
                "createdAt": index,
            }
            for index in range(1, count + 1)
        ]

    def test_page_contains_only_visible_slots(self):
        shown, page, page_count, page_words = main.App._page_word_list(
            self.make_words(), "", 0)
        self.assertEqual(len(shown), 30)
        self.assertEqual(page, 0)
        self.assertEqual(page_count, 3)
        self.assertEqual(len(page_words), main.LIST_PAGE_SIZE)
        self.assertEqual(page_words[0]["id"], 30)

    def test_search_and_out_of_range_page_are_clamped(self):
        shown, page, page_count, page_words = main.App._page_word_list(
            self.make_words(), "word-2", 99)
        self.assertEqual(page, page_count - 1)
        self.assertTrue(page_words)
        self.assertTrue(all("word-2" in word["english"] for word in shown))

    def test_startup_theme_is_detected_once(self):
        with patch.object(main.darkdetect, "isDark", return_value=True):
            self.assertEqual(main.initial_appearance_mode(), "dark")
        with patch.object(main.darkdetect, "isDark", return_value=False):
            self.assertEqual(main.initial_appearance_mode(), "light")


if __name__ == "__main__":
    unittest.main()
