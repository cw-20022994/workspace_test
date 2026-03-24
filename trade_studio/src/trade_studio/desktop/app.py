from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from trade_studio.desktop.main_window import MainWindow
from trade_studio.storage.settings import ProfileRepository


def run_desktop_app() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Trade Studio")
    app.setOrganizationName("Trade Studio")

    repository = ProfileRepository()
    window = MainWindow(repository)
    window.show()

    return app.exec()

