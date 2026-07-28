import unittest

import main


class ReviewRoundTests(unittest.TestCase):
    def test_each_word_is_selected_at_most_once_per_round(self):
        app = main.App.__new__(main.App)
        app.words = [
            {
                "id": index,
                "english": f"word-{index}",
                "chinese": f"释义-{index}",
                "createdAt": index,
                "lastReviewed": None,
                "reviewCount": 0,
            }
            for index in range(1, 6)
        ]
        app._round_remaining = {1, 2, 3, 4, 5}

        selected = []
        while app._round_remaining:
            word = app.pick_word()
            self.assertIsNotNone(word)
            self.assertNotIn(word["id"], selected)
            selected.append(word["id"])
            app._round_remaining.discard(word["id"])

        self.assertCountEqual(selected, [1, 2, 3, 4, 5])
        self.assertIsNone(app.pick_word())


if __name__ == "__main__":
    unittest.main()
