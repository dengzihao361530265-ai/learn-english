import io
import json
import os
import struct
import tempfile
import time
import unittest
from unittest import mock

import native_host


class NativeHostTests(unittest.TestCase):
    def test_frame_round_trip(self):
        stream = io.BytesIO()
        message = {"type": "translate", "english": "hello"}
        native_host.write_message(stream, message)
        stream.seek(0)
        self.assertEqual(native_host.read_message(stream), message)

    def test_rejects_invalid_word(self):
        english, error = native_host.validate_request(
            {"type": "translate", "english": "你好"}
        )
        self.assertIsNone(english)
        self.assertEqual(error["code"], "WORD_INVALID")

    def test_success_add_update_and_rate_limit(self):
        original_words_file = native_host.WORDS_FILE
        with tempfile.TemporaryDirectory() as temp_dir:
            native_host.WORDS_FILE = os.path.join(temp_dir, "words.json")
            try:
                with mock.patch.dict(os.environ, {"LLM_API_KEY": "test-key"}):
                    with mock.patch.object(native_host, "call_llm", return_value="你好"):
                        response, last = native_host.handle_request(
                            {"type": "translate", "english": "hello"}, None
                        )
                        self.assertEqual(response["status"], "ok")
                        self.assertTrue(response["added"])
                        limited, _ = native_host.handle_request(
                            {"type": "translate", "english": "world"}, last
                        )
                        self.assertEqual(limited["code"], "RATE_LIMITED")
                        with mock.patch.object(native_host, "call_llm", return_value="您好"):
                            updated, _ = native_host.handle_request(
                                {"type": "translate", "english": "HELLO"},
                                time.monotonic() - 2,
                            )
                        self.assertFalse(updated["added"])
                with open(native_host.WORDS_FILE, encoding="utf-8") as file:
                    words = json.load(file)
                self.assertEqual(len(words), 1)
                self.assertEqual(words[0]["chinese"], "您好")
            finally:
                native_host.WORDS_FILE = original_words_file


if __name__ == "__main__":
    unittest.main()
