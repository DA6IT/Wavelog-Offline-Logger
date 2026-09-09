from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from qsl_renderer import (
    QslAssetCache,
    QslRenderError,
    latest_qso,
    qso_designer_values,
    render_qsl_png,
)


def template(
    *,
    background_url="",
):
    return {
        "id": 10,
        "name": "Community Test",
        "canvas": {
            "width": 1400,
            "height": 900,
            "background": {
                "color": "#ffffff",
                "url": background_url,
            },
        },
        "fields": [
            {
                "id": "call",
                "source": "qso.call",
                "prefix": "To ",
                "suffix": "",
                "x": 10,
                "y": 20,
                "width": 80,
                "fontSize": 72,
                "fontFamily": "Arial",
                "fontWeight": 700,
                "color": "#000000",
                "align": "center",
                "rotation": 0,
                "visible": True,
            }
        ],
    }


class FakeResponse:
    def __init__(
        self,
        raw,
        url,
    ):
        self.raw = raw
        self.url = url

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False

    def read(
        self,
        _limit=-1,
    ):
        return self.raw

    def geturl(self):
        return self.url


class QslRendererTests(unittest.TestCase):
    def test_qso_values_match_server_style(self):
        values = qso_designer_values(
            {
                "call": "dl1abc",
                "qso_date": "20260908",
                "time_on": "170501",
                "band": "20m",
                "freq": "14.074000",
                "mode": "ft8",
                "station_call": "da6it",
                "my_gridsquare": "jo31ej",
                "my_qth": "Wachtendonk",
                "rst_sent": "-08",
                "rst_rcvd": "-12",
            }
        )

        self.assertEqual(
            values["qso.call"],
            "DL1ABC",
        )
        self.assertEqual(
            values["qso.date"],
            "08.09.2026",
        )
        self.assertEqual(
            values["qso.time_utc"],
            "17:05",
        )
        self.assertEqual(
            values["qso.frequency"],
            "14.074 MHz",
        )
        self.assertEqual(
            values["station.callsign"],
            "DA6IT",
        )

    def test_png_renderer_produces_expected_size(self):
        raw = render_qsl_png(
            template(),
            {
                "qso.call": "DL1ABC",
            },
        )

        self.assertTrue(
            raw.startswith(
                b"\x89PNG\r\n\x1a\n"
            )
        )

        image = Image.open(
            io.BytesIO(raw)
        )

        self.assertEqual(
            image.size,
            (1400, 900),
        )

    def test_center_alignment_preserves_full_field_box(self):
        raw = render_qsl_png(
            template(),
            {
                "qso.call": "DL1ABC",
            },
        )

        image = Image.open(
            io.BytesIO(raw)
        ).convert("RGB")

        background = Image.new(
            "RGB",
            image.size,
            "#ffffff",
        )

        from PIL import ImageChops

        bbox = ImageChops.difference(
            image,
            background,
        ).getbbox()

        self.assertIsNotNone(
            bbox
        )

        center_x = (
            bbox[0] + bbox[2]
        ) / 2

        # Field: x=10%, width=80% on a 1400px canvas.
        self.assertGreater(
            center_x,
            620,
        )
        self.assertLess(
            center_x,
            780,
        )

    def test_right_alignment_preserves_full_field_box(self):
        current = template()
        current["fields"][0]["align"] = "right"

        raw = render_qsl_png(
            current,
            {
                "qso.call": "DL1ABC",
            },
        )

        image = Image.open(
            io.BytesIO(raw)
        ).convert("RGB")

        background = Image.new(
            "RGB",
            image.size,
            "#ffffff",
        )

        from PIL import ImageChops

        bbox = ImageChops.difference(
            image,
            background,
        ).getbbox()

        self.assertIsNotNone(
            bbox
        )

        self.assertGreater(
            bbox[2],
            1150,
        )

    def test_asset_cache_reuses_download(self):
        image = Image.new(
            "RGB",
            (100, 80),
            "#ffffff",
        )

        buffer = io.BytesIO()
        image.save(
            buffer,
            format="WEBP",
        )

        url = (
            "https://da6it.de/"
            "wp-content/plugins/da6it-core/"
            "assets/qsl/templates/community-light.webp"
        )

        response = FakeResponse(
            buffer.getvalue(),
            url,
        )

        with tempfile.TemporaryDirectory() as tmp:
            cache = QslAssetCache(
                Path(tmp)
            )

            with patch(
                "qsl_renderer.secure_urlopen",
                return_value=response,
            ) as mocked:
                first = cache.get_background_bytes(
                    url
                )
                second = cache.get_background_bytes(
                    url
                )

            self.assertEqual(
                first,
                second,
            )
            self.assertEqual(
                mocked.call_count,
                1,
            )

    def test_asset_cache_rejects_external_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = QslAssetCache(
                Path(tmp)
            )

            with self.assertRaises(
                QslRenderError
            ):
                cache.get_background_bytes(
                    "https://example.org/qsl.webp"
                )

    def test_latest_qso_uses_date_and_time(self):
        result = latest_qso(
            [
                {
                    "local_id": "1",
                    "qso_date": "20260907",
                    "time_on": "230000",
                },
                {
                    "local_id": "2",
                    "qso_date": "20260908",
                    "time_on": "010000",
                },
            ]
        )

        self.assertEqual(
            result["local_id"],
            "2",
        )


if __name__ == "__main__":
    unittest.main()
