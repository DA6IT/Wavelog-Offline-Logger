from __future__ import annotations

import unittest
from datetime import date

from qsl_eqsl import (
    EQSL_MEMBER_LIST_URL,
    EqslMemberIndex,
    EqslMemberListError,
    _EqslHttpsRedirectHandler,
    _validate_eqsl_https_url,
    parse_member_csv,
    subtract_months,
)


class EqslMemberListTests(unittest.TestCase):
    def test_csv_header_and_latest_duplicate_date(self):
        index = parse_member_csv(
            (
                "Callsign,Grid,AG,Last_Log_Update\n"
                "DL1ABC,JO31,1,2026-08-01\n"
                "DL1ABC,JO32,1,2026-09-01\n"
                "PA3XYZ,JO21,0,0000-00-00\n"
            ).encode("utf-8")
        )

        self.assertEqual(
            index.members["DL1ABC"],
            date(2026, 9, 1),
        )
        self.assertIsNone(index.members["PA3XYZ"])

    def test_headerless_csv_uses_first_and_last_columns(self):
        index = parse_member_csv(
            (
                "DL1ABC,JO31,1,2026-08-01\n"
                "PA3XYZ,JO21,0,2025-01-15\n"
            ).encode("utf-8")
        )

        self.assertEqual(index.members["DL1ABC"], date(2026, 8, 1))
        self.assertEqual(index.members["PA3XYZ"], date(2025, 1, 15))

    def test_six_month_activity_threshold(self):
        index = EqslMemberIndex(
            {
                "DL1NEW": date(2026, 4, 1),
                "DL1OLD": date(2026, 3, 10),
                "DL1NONE": None,
            }
        )
        today = date(2026, 9, 11)

        self.assertEqual(index.classify("DL1NEW", today=today)[0], "active")
        self.assertEqual(index.classify("DL1OLD", today=today)[0], "inactive")
        self.assertEqual(index.classify("DL1NONE", today=today)[0], "inactive")
        self.assertEqual(index.classify("DL1MISS", today=today)[0], "missing")

    def test_subtract_months_clamps_end_of_month(self):
        self.assertEqual(
            subtract_months(date(2026, 8, 31), 6),
            date(2026, 2, 28),
        )

    def test_eqsl_url_policy_accepts_only_expected_https_hosts(self):
        self.assertEqual(
            _validate_eqsl_https_url(EQSL_MEMBER_LIST_URL),
            EQSL_MEMBER_LIST_URL,
        )

        for value in (
            "file:///tmp/eQSLMemberList.csv",
            "http://www.eqsl.cc/DownloadedFiles/eQSLMemberList.csv",
            "https://evil.example/eQSLMemberList.csv",
            "https://" + "test-user" + ":" + "test-value" + "@www.eqsl.cc/DownloadedFiles/eQSLMemberList.csv",
            "https://www.eqsl.cc:8443/DownloadedFiles/eQSLMemberList.csv",
        ):
            with self.subTest(value=value):
                with self.assertRaises(EqslMemberListError):
                    _validate_eqsl_https_url(value)

    def test_eqsl_redirect_policy_rejects_foreign_host(self):
        handler = _EqslHttpsRedirectHandler()

        with self.assertRaises(EqslMemberListError):
            handler.redirect_request(
                None,
                None,
                302,
                "Found",
                {},
                "https://evil.example/eQSLMemberList.csv",
            )


if __name__ == "__main__":
    unittest.main()
