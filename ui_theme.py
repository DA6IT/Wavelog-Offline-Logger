from __future__ import annotations

from ui_preferences import PALETTES


class ThemeState:
    """Mutable palette view shared by all UI modules."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self.apply("light")

    def apply(self, name: str) -> None:
        palette = PALETTES.get(name, PALETTES["light"])
        self._values = dict(palette)

    def __getattr__(self, name: str) -> str:
        try:
            return self._values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


theme = ThemeState()


def set_theme(name: str) -> None:
    theme.apply(name)
