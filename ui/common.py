"""Small UI helpers shared by the three windows."""

from ui.dialogs import show_message


def center_window(window):
    screen = window.screen()
    if screen is not None:
        geometry = window.frameGeometry()
        geometry.moveCenter(screen.availableGeometry().center())
        window.move(geometry.topLeft())


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if widget := item.widget():
            widget.hide()
            widget.deleteLater()
        if nested := item.layout():
            clear_layout(nested)


class WindowSupport:
    """Context is set by each window before any messages can be shown."""

    def text(self, section: str, key: str) -> str:
        return self.context.translations.text(section, key)

    def show_warning(self, message):
        show_message(self, self.context.translations, message, "warning")

    def show_info(self, message):
        show_message(self, self.context.translations, message)

    def remember(self, **values):
        try:
            self.context.settings.update(**values)
        except OSError as error:
            self.show_warning(f"{self.text('common', 'settings_error')}\n{error}")

    def change_language(self, _checked=False):
        language = "kr" if self.sender() is self.kr_btn else "en"
        self.context.translations.set_language(language)
        self.update_texts()
        self.remember(language=language)

    def sync_language_buttons(self):
        korean = self.context.translations.language == "kr"
        self.kr_btn.setChecked(korean)
        self.en_btn.setChecked(not korean)
