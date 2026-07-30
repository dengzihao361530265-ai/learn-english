import unittest
from collections import deque

import main


class ReviewRoundTests(unittest.TestCase):
    def make_app(self):
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
            for index in range(1, 4)
        ]
        app._round_ids = {1, 2, 3}
        app._round_queue = deque([1, 2, 3])
        app._round_missed_ids = []
        return app

    def test_round_has_at_most_25_words(self):
        words = [
            {
                "id": index,
                "createdAt": index,
                "lastReviewed": index * 100,
            }
            for index in range(1, 41)
        ]
        order = main.App._build_round_order(words)
        self.assertEqual(len(order), 25)

    def test_previous_mistakes_are_selected_before_oldest_words(self):
        words = [
            {
                "id": index,
                "createdAt": index,
                "lastReviewed": index * 100,
            }
            for index in range(1, 31)
        ]
        order = main.App._build_round_order(words, [30, 29])
        self.assertEqual(order[:2], [30, 29])
        self.assertEqual(order[2:], list(range(1, 24)))

    def test_never_reviewed_words_are_oldest(self):
        words = [
            {"id": 1, "createdAt": 1, "lastReviewed": 100},
            {"id": 2, "createdAt": 2, "lastReviewed": None},
            {"id": 3, "createdAt": 3, "lastReviewed": 50},
        ]
        self.assertEqual(main.App._build_round_order(words), [2, 3, 1])

    def test_unknown_word_moves_to_queue_tail(self):
        app = self.make_app()
        app._advance_round_queue(1, known=False)
        self.assertEqual(list(app._round_queue), [2, 3, 1])
        self.assertEqual(app.pick_word()["id"], 2)

    def test_round_ends_only_after_every_word_is_known(self):
        app = self.make_app()

        app._advance_round_queue(1, known=False)
        app._advance_round_queue(2, known=True)
        app._advance_round_queue(3, known=True)
        self.assertEqual(list(app._round_queue), [1])

        app._advance_round_queue(1, known=True)
        self.assertEqual(list(app._round_queue), [])
        self.assertIsNone(app.pick_word())


if __name__ == "__main__":
    unittest.main()
