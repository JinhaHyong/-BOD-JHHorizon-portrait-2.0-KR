"""Shared dependencies passed to windows before they build their UI."""

from dataclasses import dataclass

from core.settings import Settings
from core.translations import Translations
from services.font_service import FontService
from services.portrait_service import PortraitService


@dataclass
class AppContext:
    settings: Settings
    translations: Translations
    portraits: PortraitService
    fonts: FontService

    @classmethod
    def create(cls, settings: Settings | None = None):
        settings = settings if settings is not None else Settings()
        return cls(settings, Translations(settings.get("language", "kr")),
                   PortraitService(), FontService())
