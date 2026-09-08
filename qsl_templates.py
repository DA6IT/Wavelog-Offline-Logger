from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


MAX_TEMPLATES = 100
MAX_FIELDS = 64
_ALLOWED_FONTS = {
    "Arial",
    "Helvetica",
    "Georgia",
    "Verdana",
    "Trebuchet MS",
    "Courier New",
    "monospace",
}
_ALLOWED_ALIGNMENTS = {
    "left",
    "center",
    "right",
}
_ALLOWED_WEIGHTS = {
    400,
    600,
    700,
}
_COLOR_RE = re.compile(
    r"^#[0-9a-fA-F]{6}$"
)


class QslTemplateError(ValueError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).replace(
        microsecond=0
    ).isoformat()


def normalize_station_profile(
    value: str,
) -> str:
    profile = " ".join(
        str(value or "").split()
    ).strip().upper()

    if not profile:
        raise QslTemplateError(
            "Stationsprofil fehlt"
        )

    if len(profile) > 40:
        raise QslTemplateError(
            "Stationsprofil ist zu lang"
        )

    return profile


def _number(
    value: Any,
    *,
    field: str,
    minimum: float,
    maximum: float,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise QslTemplateError(
            f"Ungültiger Zahlenwert für {field}"
        ) from exc

    if number < minimum or number > maximum:
        raise QslTemplateError(
            f"{field} außerhalb des erlaubten Bereichs"
        )

    return number


def _integer(
    value: Any,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    number = _number(
        value,
        field=field,
        minimum=minimum,
        maximum=maximum,
    )

    if int(number) != number:
        raise QslTemplateError(
            f"{field} muss ganzzahlig sein"
        )

    return int(number)


def _safe_background_url(
    value: Any,
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
        raise QslTemplateError(
            "Template enthält eine nicht erlaubte Hintergrund-URL"
        )

    return url


def _field(
    raw: Any,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise QslTemplateError(
            "Template-Feld muss ein Objekt sein"
        )

    field_id = str(
        raw.get("id") or ""
    ).strip()

    source = str(
        raw.get("source") or ""
    ).strip()

    if not field_id or len(field_id) > 96:
        raise QslTemplateError(
            "Template-Feld hat keine gültige ID"
        )

    if not source or len(source) > 96:
        raise QslTemplateError(
            "Template-Feld hat keine gültige Quelle"
        )

    font_family = str(
        raw.get("fontFamily") or "Arial"
    ).strip()

    if font_family not in _ALLOWED_FONTS:
        raise QslTemplateError(
            "Template verwendet eine nicht unterstützte Schrift"
        )

    align = str(
        raw.get("align") or "left"
    ).strip().lower()

    if align not in _ALLOWED_ALIGNMENTS:
        raise QslTemplateError(
            "Template verwendet eine ungültige Ausrichtung"
        )

    weight = _integer(
        raw.get("fontWeight", 400),
        field="fontWeight",
        minimum=400,
        maximum=700,
    )

    if weight not in _ALLOWED_WEIGHTS:
        raise QslTemplateError(
            "Template verwendet ein ungültiges Schriftgewicht"
        )

    color = str(
        raw.get("color") or "#000000"
    ).strip()

    if not _COLOR_RE.fullmatch(color):
        raise QslTemplateError(
            "Template verwendet eine ungültige Textfarbe"
        )

    return {
        "id": field_id,
        "source": source,
        "prefix": str(
            raw.get("prefix") or ""
        )[:80],
        "suffix": str(
            raw.get("suffix") or ""
        )[:80],
        "x": _number(
            raw.get("x", 5),
            field="x",
            minimum=0,
            maximum=100,
        ),
        "y": _number(
            raw.get("y", 5),
            field="y",
            minimum=0,
            maximum=100,
        ),
        "width": _number(
            raw.get("width", 30),
            field="width",
            minimum=2,
            maximum=100,
        ),
        "fontSize": _integer(
            raw.get("fontSize", 28),
            field="fontSize",
            minimum=8,
            maximum=220,
        ),
        "fontFamily": font_family,
        "fontWeight": weight,
        "color": color.lower(),
        "align": align,
        "rotation": _integer(
            raw.get("rotation", 0),
            field="rotation",
            minimum=-180,
            maximum=180,
        ),
        "visible": bool(
            raw.get("visible", True)
        ),
    }


def normalize_template(
    raw: Any,
    *,
    station_profile: str,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise QslTemplateError(
            "Template muss ein Objekt sein"
        )

    template_id = _integer(
        raw.get("id", 0),
        field="template id",
        minimum=1,
        maximum=2_147_483_647,
    )

    revision = _integer(
        raw.get("revision", 1),
        field="revision",
        minimum=1,
        maximum=2_147_483_647,
    )

    name = " ".join(
        str(
            raw.get("name")
            or "QSL Template"
        ).split()
    )[:80]

    if not name:
        raise QslTemplateError(
            "Template-Name fehlt"
        )

    canvas = raw.get("canvas")

    if not isinstance(canvas, dict):
        raise QslTemplateError(
            "Template enthält keinen Canvas"
        )

    background = canvas.get("background")
    background = (
        background
        if isinstance(background, dict)
        else {}
    )

    bg_color = str(
        background.get("color")
        or "#eef8f4"
    ).strip()

    if not _COLOR_RE.fullmatch(bg_color):
        raise QslTemplateError(
            "Template verwendet eine ungültige Hintergrundfarbe"
        )

    fields = raw.get("fields")

    if not isinstance(fields, list):
        raise QslTemplateError(
            "Template enthält keine Feldliste"
        )

    if len(fields) > MAX_FIELDS:
        raise QslTemplateError(
            "Template enthält zu viele Felder"
        )

    normalized_fields = [
        _field(item)
        for item in fields
    ]

    result = {
        "schema": str(
            raw.get("schema") or ""
        )[:80],
        "schemaVersion": _integer(
            raw.get("schemaVersion", 1),
            field="schemaVersion",
            minimum=1,
            maximum=1000,
        ),
        "rendererVersion": str(
            raw.get("rendererVersion") or ""
        )[:80],
        "id": template_id,
        "revision": revision,
        "updatedAt": str(
            raw.get("updatedAt") or ""
        )[:80],
        "ownerId": _integer(
            raw.get("ownerId", 0),
            field="ownerId",
            minimum=0,
            maximum=2_147_483_647,
        ),
        "isSystem": bool(
            raw.get("isSystem", False)
        ),
        "locked": bool(
            raw.get("locked", False)
        ),
        "canEdit": bool(
            raw.get("canEdit", False)
        ),
        "name": name,
        "stationProfile": normalize_station_profile(
            raw.get("stationProfile")
            or station_profile
        ),
        "canvas": {
            "width": _integer(
                canvas.get("width", 1400),
                field="canvas width",
                minimum=700,
                maximum=2800,
            ),
            "height": _integer(
                canvas.get("height", 900),
                field="canvas height",
                minimum=450,
                maximum=1800,
            ),
            "background": {
                "type": str(
                    background.get("type")
                    or (
                        "image"
                        if background.get("url")
                        else "color"
                    )
                )[:20],
                "color": bg_color.lower(),
                "attachmentId": _integer(
                    background.get(
                        "attachmentId",
                        0,
                    ),
                    field="background attachmentId",
                    minimum=0,
                    maximum=2_147_483_647,
                ),
                "url": _safe_background_url(
                    background.get("url")
                ),
            },
        },
        "fields": normalized_fields,
        "hasPersonalLayout": bool(
            raw.get(
                "hasPersonalLayout",
                False,
            )
        ),
        "personalLayoutSavedAt": str(
            raw.get(
                "personalLayoutSavedAt",
                "",
            )
        )[:80],
    }

    return result


def normalize_template_response(
    response: Any,
    *,
    station_profile: str,
) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise QslTemplateError(
            "Template-Antwort muss ein Objekt sein"
        )

    requested = normalize_station_profile(
        station_profile
    )

    returned = normalize_station_profile(
        response.get("stationProfile")
        or requested
    )

    if returned != requested:
        raise QslTemplateError(
            "Template-Antwort gehört zu einem anderen Stationsprofil"
        )

    templates = response.get("templates")

    if not isinstance(templates, list):
        raise QslTemplateError(
            "Template-Antwort enthält kein templates[]"
        )

    if len(templates) > MAX_TEMPLATES:
        raise QslTemplateError(
            "Template-Antwort enthält zu viele Motive"
        )

    normalized = [
        normalize_template(
            item,
            station_profile=requested,
        )
        for item in templates
    ]

    ids = [
        item["id"]
        for item in normalized
    ]

    if len(ids) != len(set(ids)):
        raise QslTemplateError(
            "Template-Antwort enthält doppelte IDs"
        )

    return normalized


def choose_template_profile_response(
    candidates: list[str],
    responses: dict[str, Any],
) -> tuple[str, dict[str, Any], int]:
    ordered: list[str] = []

    for raw in candidates:
        try:
            profile = normalize_station_profile(
                raw
            )
        except QslTemplateError:
            continue

        if profile not in ordered:
            ordered.append(
                profile
            )

    choices: list[
        tuple[int, int, str, dict[str, Any]]
    ] = []

    for index, profile in enumerate(
        ordered
    ):
        response = responses.get(
            profile
        )

        if response is None:
            continue

        templates = normalize_template_response(
            response,
            station_profile=profile,
        )

        personal_count = sum(
            1
            for item in templates
            if bool(
                item.get(
                    "isSystem"
                )
            )
            and bool(
                item.get(
                    "hasPersonalLayout"
                )
            )
        )

        normalized_response = {
            "stationProfile": profile,
            "templates": templates,
        }

        choices.append(
            (
                personal_count,
                -index,
                profile,
                normalized_response,
            )
        )

    if not choices:
        raise QslTemplateError(
            "Für kein Stationsprofil konnte ein Motiv-Katalog geladen werden"
        )

    personal_count, _order, profile, response = max(
        choices,
        key=lambda item: (
            item[0],
            item[1],
        ),
    )

    return (
        profile,
        response,
        personal_count,
    )


class QslTemplateCatalog:
    def __init__(
        self,
        db,
    ) -> None:
        self.db = db
        self._ensure_schema()

    def _ensure_schema(
        self,
    ) -> None:
        with self.db.lock:
            self.db.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS da6it_qsl_template_cache (
                    station_profile TEXT NOT NULL,
                    template_id INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY(station_profile, template_id)
                );

                CREATE TABLE IF NOT EXISTS da6it_qsl_template_selection (
                    station_profile TEXT PRIMARY KEY,
                    template_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self.db.conn.commit()

    def cache_response(
        self,
        station_profile: str,
        response: Any,
    ) -> list[dict[str, Any]]:
        profile = normalize_station_profile(
            station_profile
        )

        templates = normalize_template_response(
            response,
            station_profile=profile,
        )

        fetched_at = _utc_now_iso()

        with self.db.lock:
            self.db.conn.execute(
                """
                DELETE FROM da6it_qsl_template_cache
                WHERE station_profile=?
                """,
                (profile,),
            )

            for item in templates:
                self.db.conn.execute(
                    """
                    INSERT INTO da6it_qsl_template_cache(
                        station_profile,
                        template_id,
                        revision,
                        payload,
                        fetched_at
                    )
                    VALUES(?,?,?,?,?)
                    """,
                    (
                        profile,
                        int(item["id"]),
                        int(item["revision"]),
                        json.dumps(
                            item,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        fetched_at,
                    ),
                )

            self.db.conn.commit()

        selected = self.selected_template_id(
            profile
        )

        if (
            selected is not None
            and selected not in {
                item["id"]
                for item in templates
            }
        ):
            self.clear_selection(
                profile
            )

        return templates

    def cached_templates(
        self,
        station_profile: str,
    ) -> list[dict[str, Any]]:
        profile = normalize_station_profile(
            station_profile
        )

        with self.db.lock:
            rows = self.db.conn.execute(
                """
                SELECT payload
                FROM da6it_qsl_template_cache
                WHERE station_profile=?
                ORDER BY template_id ASC
                """,
                (profile,),
            ).fetchall()

        templates: list[dict[str, Any]] = []

        for row in rows:
            try:
                payload = json.loads(
                    str(row["payload"] or "")
                )
                templates.append(
                    normalize_template(
                        payload,
                        station_profile=profile,
                    )
                )
            except (
                json.JSONDecodeError,
                QslTemplateError,
            ):
                continue

        return templates

    def selected_template_id(
        self,
        station_profile: str,
    ) -> int | None:
        profile = normalize_station_profile(
            station_profile
        )

        with self.db.lock:
            row = self.db.conn.execute(
                """
                SELECT template_id
                FROM da6it_qsl_template_selection
                WHERE station_profile=?
                """,
                (profile,),
            ).fetchone()

        if not row:
            return None

        try:
            return int(
                row["template_id"]
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    def set_selected_template(
        self,
        station_profile: str,
        template_id: int,
    ) -> None:
        profile = normalize_station_profile(
            station_profile
        )

        template_id = int(
            template_id
        )

        available = {
            item["id"]
            for item in self.cached_templates(
                profile
            )
        }

        if template_id not in available:
            raise QslTemplateError(
                "Das ausgewählte Motiv ist nicht im lokalen Katalog"
            )

        now = _utc_now_iso()

        with self.db.lock:
            self.db.conn.execute(
                """
                INSERT INTO da6it_qsl_template_selection(
                    station_profile,
                    template_id,
                    updated_at
                )
                VALUES(?,?,?)
                ON CONFLICT(station_profile) DO UPDATE SET
                    template_id=excluded.template_id,
                    updated_at=excluded.updated_at
                """,
                (
                    profile,
                    template_id,
                    now,
                ),
            )
            self.db.conn.commit()

    def clear_selection(
        self,
        station_profile: str,
    ) -> None:
        profile = normalize_station_profile(
            station_profile
        )

        with self.db.lock:
            self.db.conn.execute(
                """
                DELETE FROM da6it_qsl_template_selection
                WHERE station_profile=?
                """,
                (profile,),
            )
            self.db.conn.commit()
