from __future__ import annotations

import inspect
import unittest

from feature_qsl import QslFeatureMixin


class QslPreviewParityTests(unittest.TestCase):
    def test_preview_uses_delivery_png_renderer(self):
        source = inspect.getsource(
            QslFeatureMixin.preview_qsl_template
        )

        self.assertIn(
            "render_selected_qsl(",
            source,
        )
        self.assertNotIn(
            "render_qsl_image(",
            source,
        )
        self.assertNotIn(
            "QslAssetCache(",
            source,
        )


if __name__ == "__main__":
    unittest.main()
