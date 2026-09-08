from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from logger_core import MetadataDB
from qsl_templates import (
    QslTemplateCatalog,
    QslTemplateError,
    normalize_template_response,
)


def template(
    template_id=10,
    *,
    name="Community Light",
    system=True,
):
    return {
        "schema": "da6it-qsl-template",
        "schemaVersion": 1,
        "rendererVersion": "1",
        "id": template_id,
        "revision": 3,
        "updatedAt": "2026-09-08T17:00:00+00:00",
        "ownerId": 1,
        "isSystem": system,
        "locked": system,
        "canEdit": not system,
        "name": name,
        "stationProfile": "DA6IT",
        "canvas": {
            "width": 1400,
            "height": 900,
            "background": {
                "type": "image",
                "color": "#eef8f4",
                "attachmentId": 0,
                "url": (
                    "https://da6it.de/wp-content/plugins/"
                    "da6it-core/assets/qsl/templates/light.png"
                ),
            },
        },
        "fields": [
            {
                "id": "qso_call",
                "source": "qso.call",
                "prefix": "",
                "suffix": "",
                "x": 18.2,
                "y": 21.5,
                "width": 42,
                "fontSize": 72,
                "fontFamily": "Arial",
                "fontWeight": 700,
                "color": "#15382e",
                "align": "left",
                "rotation": 0,
                "visible": True,
            }
        ],
        "hasPersonalLayout": True,
        "personalLayoutSavedAt": "2026-09-08T17:00:00+00:00",
    }


class QslTemplateTests(unittest.TestCase):
    def test_real_contract_shape_is_normalized(self):
        result = normalize_template_response(
            {
                "apiVersion": "1.0",
                "stationProfile": "DA6IT",
                "templates": [
                    template()
                ],
            },
            station_profile="DA6IT",
        )

        self.assertEqual(
            len(result),
            1,
        )
        self.assertEqual(
            result[0]["id"],
            10,
        )
        self.assertTrue(
            result[0]["isSystem"]
        )
        self.assertTrue(
            result[0]["hasPersonalLayout"]
        )
        self.assertEqual(
            result[0]["fields"][0]["x"],
            18.2,
        )

    def test_other_station_profile_is_rejected(self):
        with self.assertRaisesRegex(
            QslTemplateError,
            "anderen Stationsprofil",
        ):
            normalize_template_response(
                {
                    "stationProfile": "DA6IT/P",
                    "templates": [],
                },
                station_profile="DA6IT",
            )

    def test_external_background_url_is_rejected(self):
        item = template()
        item["canvas"]["background"]["url"] = (
            "https://example.org/card.png"
        )

        with self.assertRaisesRegex(
            QslTemplateError,
            "Hintergrund-URL",
        ):
            normalize_template_response(
                {
                    "stationProfile": "DA6IT",
                    "templates": [item],
                },
                station_profile="DA6IT",
            )

    def test_catalog_cache_and_selection_survive_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.db"

            db = MetadataDB(path)

            catalog = QslTemplateCatalog(db)
            cached = catalog.cache_response(
                "DA6IT",
                {
                    "stationProfile": "DA6IT",
                    "templates": [
                        template(10),
                        template(
                            11,
                            name="My Template",
                            system=False,
                        ),
                    ],
                },
            )

            self.assertEqual(
                len(cached),
                2,
            )

            catalog.set_selected_template(
                "DA6IT",
                11,
            )

            db.close()

            reopened = MetadataDB(path)

            try:
                catalog = QslTemplateCatalog(
                    reopened
                )

                self.assertEqual(
                    len(
                        catalog.cached_templates(
                            "DA6IT"
                        )
                    ),
                    2,
                )
                self.assertEqual(
                    catalog.selected_template_id(
                        "DA6IT"
                    ),
                    11,
                )
            finally:
                reopened.close()

    def test_removed_template_clears_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MetadataDB(
                Path(tmp) / "metadata.db"
            )

            try:
                catalog = QslTemplateCatalog(db)

                catalog.cache_response(
                    "DA6IT",
                    {
                        "stationProfile": "DA6IT",
                        "templates": [
                            template(10),
                            template(11),
                        ],
                    },
                )

                catalog.set_selected_template(
                    "DA6IT",
                    11,
                )

                catalog.cache_response(
                    "DA6IT",
                    {
                        "stationProfile": "DA6IT",
                        "templates": [
                            template(10)
                        ],
                    },
                )

                self.assertIsNone(
                    catalog.selected_template_id(
                        "DA6IT"
                    )
                )
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
