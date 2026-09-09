from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont, ImageOps

from logger_core import secure_urlopen


MAX_ASSET_BYTES = 16 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_EDGE = 8000


class QslRenderError(RuntimeError):
    pass


def _safe_asset_url(
    value: str,
) -> str:
    url = str(value or "").strip()

    if not url:
        return ""

    parsed = urlsplit(url)

    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname != "da6it.de"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise QslRenderError(
            "QSL-Hintergrund verweist auf eine nicht erlaubte URL"
        )

    return url


def _open_image_bytes(
    raw: bytes,
) -> Image.Image:
    if not raw:
        raise QslRenderError(
            "QSL-Hintergrund ist leer"
        )

    old_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

    try:
        image = Image.open(
            io.BytesIO(raw)
        )
        image.load()
    except Exception as exc:
        raise QslRenderError(
            "QSL-Hintergrund konnte nicht als Bild gelesen werden"
        ) from exc
    finally:
        Image.MAX_IMAGE_PIXELS = old_limit

    width, height = image.size

    if (
        width < 1
        or height < 1
        or width > MAX_IMAGE_EDGE
        or height > MAX_IMAGE_EDGE
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise QslRenderError(
            "QSL-Hintergrund hat eine nicht erlaubte Bildgröße"
        )

    return image.convert("RGB")


class QslAssetCache:
    def __init__(
        self,
        root: Path,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _path_for_url(
        self,
        url: str,
    ) -> Path:
        digest = hashlib.sha256(
            url.encode("utf-8")
        ).hexdigest()

        return self.root / (
            digest + ".asset"
        )

    def get_background_bytes(
        self,
        url: str,
    ) -> bytes | None:
        url = _safe_asset_url(
            url
        )

        if not url:
            return None

        target = self._path_for_url(
            url
        )

        if target.is_file():
            try:
                raw = target.read_bytes()

                if (
                    raw
                    and len(raw) <= MAX_ASSET_BYTES
                ):
                    _open_image_bytes(raw)
                    return raw
            except Exception:
                try:
                    target.unlink()
                except OSError:
                    pass

        request = __import__(
            "urllib.request",
            fromlist=["Request"],
        ).Request(
            url,
            headers={
                "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.5",
                "User-Agent": "DA6IT-Wavelog-Offline-Logger-QSL/0.20",
            },
            method="GET",
        )

        try:
            with secure_urlopen(
                request,
                timeout=20,
            ) as response:
                final_url = str(
                    response.geturl()
                    if hasattr(
                        response,
                        "geturl",
                    )
                    else url
                )

                _safe_asset_url(
                    final_url
                )

                raw = response.read(
                    MAX_ASSET_BYTES + 1
                )
        except Exception as exc:
            raise QslRenderError(
                "QSL-Hintergrund konnte nicht geladen werden"
            ) from exc

        if len(raw) > MAX_ASSET_BYTES:
            raise QslRenderError(
                "QSL-Hintergrund ist zu groß"
            )

        _open_image_bytes(
            raw
        )

        temp = target.with_suffix(
            ".tmp"
        )

        try:
            temp.write_bytes(
                raw
            )
            os.replace(
                temp,
                target,
            )
        finally:
            try:
                temp.unlink()
            except OSError:
                pass

        return raw


def _display_date(
    value: Any,
) -> str:
    digits = "".join(
        character
        for character in str(value or "")
        if character.isdigit()
    )

    if len(digits) >= 8:
        return (
            f"{digits[6:8]}."
            f"{digits[4:6]}."
            f"{digits[0:4]}"
        )

    return str(
        value or ""
    ).strip()


def _display_time(
    value: Any,
) -> str:
    digits = "".join(
        character
        for character in str(value or "")
        if character.isdigit()
    )

    if len(digits) >= 4:
        return (
            f"{digits[0:2]}:"
            f"{digits[2:4]}"
        )

    return str(
        value or ""
    ).strip()


def _display_freq(
    value: Any,
) -> str:
    raw = str(
        value or ""
    ).strip().replace(
        ",",
        ".",
    )

    if not raw:
        return ""

    try:
        number = float(raw)
    except ValueError:
        return raw[:32]

    text = (
        f"{number:.6f}"
        .rstrip("0")
        .rstrip(".")
    )

    return text + " MHz"


def qso_designer_values(
    qso: dict[str, Any],
) -> dict[str, str]:
    return {
        "station.callsign": str(
            qso.get("station_call")
            or qso.get("operator_call")
            or ""
        ).strip().upper(),
        "station.name": "",
        "station.qth": str(
            qso.get("my_qth")
            or ""
        ).strip(),
        "station.locator": str(
            qso.get("my_gridsquare")
            or ""
        ).strip().upper(),
        "qso.call": str(
            qso.get("call")
            or ""
        ).strip().upper(),
        "qso.date": _display_date(
            qso.get("qso_date")
        ),
        "qso.time_utc": _display_time(
            qso.get("time_on")
        ),
        "qso.band": str(
            qso.get("band")
            or ""
        ).strip().lower(),
        "qso.frequency": _display_freq(
            qso.get("freq")
        ),
        "qso.mode": str(
            qso.get("mode")
            or ""
        ).strip().upper(),
        "qso.rst_sent": str(
            qso.get("rst_sent")
            or ""
        ).strip(),
        "qso.rst_received": str(
            qso.get("rst_rcvd")
            or ""
        ).strip(),
        "qso.locator": str(
            qso.get("gridsquare")
            or ""
        ).strip().upper(),
        "qso.qth": str(
            qso.get("qth")
            or ""
        ).strip(),
        "activity.pota_ref": str(
            qso.get("my_pota_ref")
            or qso.get("pota_ref")
            or ""
        ).strip().upper(),
        "activity.sota_ref": str(
            qso.get("my_sota_ref")
            or qso.get("sota_ref")
            or ""
        ).strip().upper(),
        "activity.contest": str(
            qso.get("contest_id")
            or ""
        ).strip(),
        "custom.text": "",
    }


_FONT_FILES = {
    "Arial": (
        ("arial.ttf", "arialbd.ttf"),
        ("Arial.ttf", "Arial Bold.ttf"),
    ),
    "Helvetica": (
        ("arial.ttf", "arialbd.ttf"),
        ("Helvetica.ttc", "Helvetica.ttc"),
    ),
    "Georgia": (
        ("georgia.ttf", "georgiab.ttf"),
        ("Georgia.ttf", "Georgia Bold.ttf"),
    ),
    "Verdana": (
        ("verdana.ttf", "verdanab.ttf"),
        ("Verdana.ttf", "Verdana Bold.ttf"),
    ),
    "Trebuchet MS": (
        ("trebuc.ttf", "trebucbd.ttf"),
        ("Trebuchet MS.ttf", "Trebuchet MS Bold.ttf"),
    ),
    "Courier New": (
        ("cour.ttf", "courbd.ttf"),
        ("Courier New.ttf", "Courier New Bold.ttf"),
    ),
    "monospace": (
        ("cour.ttf", "courbd.ttf"),
        ("DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf"),
    ),
}


def _font_roots() -> list[Path]:
    roots: list[Path] = []

    windir = os.environ.get(
        "WINDIR",
        "",
    )

    if windir:
        roots.append(
            Path(windir) / "Fonts"
        )

    roots.extend(
        [
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"),
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/truetype/liberation2"),
        ]
    )

    return roots


def _font(
    family: str,
    size: int,
    weight: int,
) -> ImageFont.ImageFont:
    family = str(
        family or "Arial"
    )

    size = max(
        8,
        int(size),
    )

    bold = int(
        weight or 400
    ) >= 600

    pairs = _FONT_FILES.get(
        family,
        _FONT_FILES["Arial"],
    )

    filenames = [
        pair[1 if bold else 0]
        for pair in pairs
    ]

    for filename in filenames:
        try:
            return ImageFont.truetype(
                filename,
                size=size,
            )
        except OSError:
            pass

        for root in _font_roots():
            candidate = (
                root / filename
            )

            if not candidate.is_file():
                continue

            try:
                return ImageFont.truetype(
                    str(candidate),
                    size=size,
                )
            except OSError:
                pass

    try:
        return ImageFont.load_default(
            size=size
        )
    except TypeError:
        return ImageFont.load_default()


def _fitted_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    family: str,
    requested_size: int,
    weight: int,
    max_width: int,
) -> ImageFont.ImageFont:
    size = max(
        8,
        int(requested_size),
    )

    while size > 8:
        font = _font(
            family,
            size,
            weight,
        )

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font,
        )

        if (
            bbox[2] - bbox[0]
            <= max_width
        ):
            return font

        size -= 1

    return _font(
        family,
        8,
        weight,
    )


def _draw_field(
    image: Image.Image,
    field: dict[str, Any],
    text: str,
) -> None:
    if not text:
        return

    width, height = image.size

    # The browser designer renders each field with 4px horizontal and
    # 2px vertical padding. Its PNG capture uses the padded text origin.
    # Mirror that here so desktop PNGs line up with the web preview.
    x = int(
        round(
            float(field.get("x", 0))
            * width
            / 100
        )
    ) + 4

    y = int(
        round(
            float(field.get("y", 0))
            * height
            / 100
        )
    ) + 2

    field_width = max(
        8,
        int(
            round(
                float(
                    field.get(
                        "width",
                        30,
                    )
                )
                * width
                / 100
            )
        ),
    )

    requested_size = max(
        8,
        int(
            field.get(
                "fontSize",
                28,
            )
        ),
    )

    family = str(
        field.get(
            "fontFamily",
            "Arial",
        )
    )

    weight = int(
        field.get(
            "fontWeight",
            400,
        )
    )

    color = str(
        field.get(
            "color",
            "#000000",
        )
    )

    align = str(
        field.get(
            "align",
            "left",
        )
    ).lower()

    rotation = int(
        field.get(
            "rotation",
            0,
        )
    )

    scratch = Image.new(
        "RGBA",
        (
            field_width,
            max(
                requested_size * 4,
                96,
            ),
        ),
        (
            0,
            0,
            0,
            0,
        ),
    )

    draw = ImageDraw.Draw(
        scratch
    )

    font = _fitted_font(
        draw,
        text,
        family=family,
        requested_size=requested_size,
        weight=weight,
        max_width=field_width,
    )

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    text_width = max(
        1,
        bbox[2] - bbox[0],
    )

    if align == "center":
        draw_x = (
            field_width - text_width
        ) / 2
    elif align == "right":
        draw_x = (
            field_width - text_width
        )
    else:
        draw_x = 0

    draw.text(
        (draw_x, 0),
        text,
        font=font,
        fill=color,
    )

    # IMPORTANT: keep the complete transparent field box.
    #
    # The browser renderer calculates center/right alignment inside the full
    # configured field width. Cropping the transparent left/right area here
    # destroys that alignment because the text is then pasted back at the
    # field's left edge.
    if not scratch.getbbox():
        return

    if rotation:
        scratch = scratch.rotate(
            -rotation,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )

    image.paste(
        scratch,
        (x, y),
        scratch,
    )


def render_qsl_image(
    template: dict[str, Any],
    values: dict[str, str],
    *,
    background_bytes: bytes | None = None,
) -> Image.Image:
    canvas = template.get(
        "canvas"
    )

    if not isinstance(
        canvas,
        dict,
    ):
        raise QslRenderError(
            "Template enthält keinen Canvas"
        )

    try:
        width = int(
            canvas.get(
                "width",
                1400,
            )
        )
        height = int(
            canvas.get(
                "height",
                900,
            )
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise QslRenderError(
            "Template enthält eine ungültige Canvas-Größe"
        ) from exc

    if (
        width < 700
        or height < 450
        or width > 2800
        or height > 1800
    ):
        raise QslRenderError(
            "Template-Canvas außerhalb des erlaubten Bereichs"
        )

    background = canvas.get(
        "background"
    )

    background = (
        background
        if isinstance(
            background,
            dict,
        )
        else {}
    )

    color = str(
        background.get(
            "color",
            "#ffffff",
        )
    )

    image = Image.new(
        "RGB",
        (width, height),
        color,
    )

    if background_bytes:
        background_image = (
            _open_image_bytes(
                background_bytes
            )
        )

        fitted = ImageOps.fit(
            background_image,
            (width, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )

        image.paste(
            fitted,
            (0, 0),
        )

    fields = template.get(
        "fields"
    )

    if not isinstance(
        fields,
        list,
    ):
        raise QslRenderError(
            "Template enthält keine Feldliste"
        )

    for field in fields:
        if (
            not isinstance(
                field,
                dict,
            )
            or not bool(
                field.get(
                    "visible",
                    True,
                )
            )
        ):
            continue

        source = str(
            field.get(
                "source",
                "",
            )
        )

        value = str(
            values.get(
                source,
                "",
            )
            or ""
        )

        text = (
            str(
                field.get(
                    "prefix",
                    "",
                )
                or ""
            )
            + value
            + str(
                field.get(
                    "suffix",
                    "",
                )
                or ""
            )
        )

        _draw_field(
            image,
            field,
            text,
        )

    return image


def render_qsl_png(
    template: dict[str, Any],
    values: dict[str, str],
    *,
    background_bytes: bytes | None = None,
) -> bytes:
    image = render_qsl_image(
        template,
        values,
        background_bytes=background_bytes,
    )

    output = io.BytesIO()

    image.save(
        output,
        format="PNG",
        optimize=True,
    )

    return output.getvalue()


def latest_qso(
    qsos: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not qsos:
        return None

    return max(
        qsos,
        key=lambda qso: (
            str(
                qso.get(
                    "qso_date",
                    "",
                )
            ),
            str(
                qso.get(
                    "time_on",
                    "",
                )
            ),
            str(
                qso.get(
                    "local_id",
                    "",
                )
            ),
        ),
    )
