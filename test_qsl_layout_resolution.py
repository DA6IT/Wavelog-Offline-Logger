from __future__ import annotations

import unittest

from qsl_templates import (
    QslTemplateError,
    choose_template_profile_response,
)


def template(
    template_id: int,
    *,
    personal: bool,
):
    return {
        "schema": "da6it-qsl-template",
        "schemaVersion": 1,
        "rendererVersion": "1",
        "id": template_id,
        "revision": 1,
        "updatedAt": "",
        "ownerId": 1,
        "isSystem": True,
        "locked": True,
        "canEdit": False,
        "name": "Community Light",
        "stationProfile": "DA6IT",
        "canvas": {
            "width": 1400,
            "height": 900,
            "background": {
                "type": "color",
                "color": "#ffffff",
                "attachmentId": 0,
                "url": "",
            },
        },
        "fields": [
            {
                "id": "light_rst_rcvd",
                "source": "qso.rst_received",
                "prefix": "",
                "suffix": "",
                "x": 36.0 if personal else 29.0,
                "y": 68.8,
                "width": 17.0,
                "fontSize": 28,
                "fontFamily": "Arial",
                "fontWeight": 700,
                "color": "#0d3555",
                "align": "left",
                "rotation": 0,
                "visible": True,
            }
        ],
        "hasPersonalLayout": personal,
        "personalLayoutSavedAt": (
            "2026-09-08 17:00:00"
            if personal
            else ""
        ),
    }


class QslLayoutResolutionTests(unittest.TestCase):
    def test_personal_layout_wins_over_first_candidate(self):
        responses = {
            "DA6IT-ZUHAUSE": {
                "stationProfile": "DA6IT-ZUHAUSE",
                "templates": [
                    template(
                        10,
                        personal=False,
                    )
                ],
            },
            "DA6IT": {
                "stationProfile": "DA6IT",
                "templates": [
                    template(
                        10,
                        personal=True,
                    )
                ],
            },
        }

        profile, response, personal_count = (
            choose_template_profile_response(
                [
                    "DA6IT-ZUHAUSE",
                    "DA6IT",
                ],
                responses,
            )
        )

        self.assertEqual(
            profile,
            "DA6IT",
        )
        self.assertEqual(
            personal_count,
            1,
        )
        self.assertTrue(
            response["templates"][0][
                "hasPersonalLayout"
            ]
        )
        self.assertEqual(
            response["templates"][0]["fields"][0]["x"],
            36.0,
        )

    def test_tie_prefers_local_profile_name(self):
        responses = {
            "DA6IT-ZUHAUSE": {
                "stationProfile": "DA6IT-ZUHAUSE",
                "templates": [
                    template(
                        10,
                        personal=True,
                    )
                ],
            },
            "DA6IT": {
                "stationProfile": "DA6IT",
                "templates": [
                    template(
                        10,
                        personal=True,
                    )
                ],
            },
        }

        profile, _response, count = (
            choose_template_profile_response(
                [
                    "DA6IT-ZUHAUSE",
                    "DA6IT",
                ],
                responses,
            )
        )

        self.assertEqual(
            profile,
            "DA6IT-ZUHAUSE",
        )
        self.assertEqual(
            count,
            1,
        )

    def test_no_personal_layout_keeps_first_candidate(self):
        responses = {
            "DA6IT-ZUHAUSE": {
                "stationProfile": "DA6IT-ZUHAUSE",
                "templates": [
                    template(
                        10,
                        personal=False,
                    )
                ],
            },
            "DA6IT": {
                "stationProfile": "DA6IT",
                "templates": [
                    template(
                        10,
                        personal=False,
                    )
                ],
            },
        }

        profile, _response, count = (
            choose_template_profile_response(
                [
                    "DA6IT-ZUHAUSE",
                    "DA6IT",
                ],
                responses,
            )
        )

        self.assertEqual(
            profile,
            "DA6IT-ZUHAUSE",
        )
        self.assertEqual(
            count,
            0,
        )

    def test_requires_one_successful_response(self):
        with self.assertRaises(
            QslTemplateError
        ):
            choose_template_profile_response(
                [
                    "DA6IT-ZUHAUSE",
                    "DA6IT",
                ],
                {},
            )


if __name__ == "__main__":
    unittest.main()
