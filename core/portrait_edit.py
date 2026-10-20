"""Editable text layers expressed in original image pixels, independent of Qt."""

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class TextOverlay:
    text: str = ""
    x: float = 0
    y: float = 0
    width: int = 300
    height: float | None = None
    font_family: str = "맑은 고딕"
    font_file: str | None = None
    font_style: str = ""
    font_weight: int | None = None
    font_slant: str = "normal"
    font_size: int = 28
    bold: bool = False
    italic: bool = False
    intense: bool = False
    shadow: bool = False
    alignment: str = "center"
    text_color: str = "#ffffff"
    text_opacity: int = 100
    background_color: str = "#000000"
    background_opacity: int = 50
    padding: int = 10
    radius: int = 0
    id: str = field(default_factory=lambda: uuid4().hex)
