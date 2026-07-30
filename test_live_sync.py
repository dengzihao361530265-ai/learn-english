import json
import os
import tempfile
import unittest
from collections import deque

import main


class FakeTabView:
    def __init__(self, current="背单词"):
        self.current = current

    def get(self):
        return self.current


class LiveSyncTests(unittest.TestCase):
    def test_external_word_refreshes_model_and_current_word(self):
        original_words_file = main.WORDS_FILE
        with tempfile.TemporaryDirectory() as temp_dir:
            main.WORDS_FILE = os.path.join(temp_dir, "words.json")
            initial = [{
                "id": 1, "english": "hello", "chinese": "你好",
                "createdAt": 1, "lastReviewed": None, "reviewCount": 0,
            }]
            with open(main.WORDS_FILE, "w", encoding="utf-8") as file:
                json.dump(initial, file)

            app = main.App.__new__(main.App)
            app.tabview = FakeTabView()
            app.words = initial
            app.current = initial[0]
            app.revealed = True
            app._list_dirty = False
            app._round_ids = {1}
            app._round_queue = deque([1])
            app._round_missed_ids = []
            app._previous_round_missed_ids = []
            app._round_completed = False
            app._word_snapshot = {1: dict(initial[0])}
            app._words_signature = app._get_words_signature()
            calls = {"list": 0, "review": 0}
            app.render_list = (
                lambda **_kwargs:
                calls.__setitem__("list", calls["list"] + 1)
            )
            app.refresh_review_ui = (
                lambda: calls.__setitem__("review", calls["review"] + 1)
            )

            updated = [
                {**initial[0], "chinese": "您好"},
                {
                    "id": 2, "english": "world", "chinese": "世界",
                    "createdAt": 2, "lastReviewed": None, "reviewCount": 0,
                },
            ]
            with open(main.WORDS_FILE, "w", encoding="utf-8") as file:
                json.dump(updated, file)
                file.write(" ")

            try:
                signature = app._get_words_signature()
                app._apply_external_words(signature, updated)
                self.assertEqual(len(app.words), 2)
                self.assertEqual(app.current["chinese"], "您好")
                self.assertEqual(calls, {"list": 0, "review": 1})
                self.assertTrue(app._list_dirty)
                self.assertEqual(list(app._round_queue), [1])
            finally:
                main.WORDS_FILE = original_words_file


if __name__ == "__main__":
    unittest.main()
