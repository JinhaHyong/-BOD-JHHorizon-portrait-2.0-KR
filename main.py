"""Run with: python main.py"""

import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from core.context import AppContext
from core.paths import resource_path
from core.settings import Settings
from services.single_instance import SingleInstance, SingleInstanceError
from ui.portrait_window import PortraitWindow
from ui.theme import install_theme


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setApplicationName("JHnode")
    app.setOrganizationName("JHnode")
    app.setStyle("Fusion")
    settings = Settings()
    try:
        instance = SingleInstance(settings.path, app)
        if not instance.start():
            return 0
    except (OSError, SingleInstanceError) as error:
        logging.exception("Cannot establish the application instance")
        QMessageBox.critical(None, "JHnode", "프로그램을 시작하지 못했습니다.\n이미 실행 중이라면 기존 창을 확인해주세요.\n\n" + str(error))
        return 1
    try:
        context = AppContext.create(settings)
        install_theme(app, context.settings)
        app.setWindowIcon(QIcon(str(resource_path("아이콘.ico"))))
        window = PortraitWindow(context)
        instance.set_window(window)
        app.aboutToQuit.connect(instance.close)
        window.show()
        return app.exec()
    finally:
        instance.close()


if __name__ == "__main__":
    sys.exit(main())
