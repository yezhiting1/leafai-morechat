import unittest
from unittest.mock import patch

from common.time_check import time_checker


class TimeCheckerTest(unittest.TestCase):
    @staticmethod
    def _handler(calls):
        @time_checker
        def handler(_self):
            calls.append("handled")

        return handler

    def test_default_end_of_day_stop_time_allows_messages(self):
        calls = []
        handler = self._handler(calls)

        with patch(
            "common.time_check.config.conf",
            return_value={"chat_time_module": True},
        ):
            handler(object())

        self.assertEqual(calls, ["handled"])

    def test_invalid_24th_hour_stop_time_is_rejected_without_crashing(self):
        calls = []
        handler = self._handler(calls)

        with patch(
            "common.time_check.config.conf",
            return_value={
                "chat_time_module": True,
                "chat_start_time": "00:00",
                "chat_stop_time": "24:01",
            },
        ):
            handler(object())

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
