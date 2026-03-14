"""
main.py — Jeopardy Game entry point.

Manages switching between Edit Mode and Play Mode inside a single
QMainWindow using a QStackedWidget.
"""
from __future__ import annotations

import ctypes
import os
import sys

# Tell Windows this is its own app (not python.exe) so the taskbar icon works
if sys.platform == "win32":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "chaewon.jeopardy.game"
    )

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget,
    QVBoxLayout, QLabel, QMessageBox,
)

from board import Board
from players import PlayerManager
from edit_mode import EditMode
from play_mode import PlayMode

# ------------------------------------------------------------------ #
#  Resolve assets directory                                           #
# ------------------------------------------------------------------ #
def _get_data_dir() -> str:
    """Return a persistent user-data directory that survives app updates.

    - Built app: %APPDATA%/Chaewon Jeopardy/
    - Dev mode:  project directory (next to main.py)
    """
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                            "Chaewon Jeopardy")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base, exist_ok=True)
    return base


def _get_assets_dir() -> str:
    """Return absolute path to the assets/ folder inside the data directory."""
    assets = os.path.join(_get_data_dir(), "assets")
    os.makedirs(assets, exist_ok=True)
    return assets


# ------------------------------------------------------------------ #
#  Main Window                                                        #
# ------------------------------------------------------------------ #
class MainWindow(QMainWindow):
    EDIT_IDX = 0
    PLAY_IDX = 1

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jeopardy! Game Builder")
        _base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
        self.setWindowIcon(QIcon(os.path.join(_base, "icon.ico")))
        self.resize(1280, 800)
        self.setMinimumSize(800, 600)

        self.assets_dir = _get_assets_dir()
        self.board = Board()
        self.player_manager = PlayerManager()

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._edit_mode = EditMode(self.board, self.player_manager, self.assets_dir)
        self._play_mode = PlayMode(self.board, self.player_manager, self.assets_dir)

        self._stack.addWidget(self._edit_mode)   # index 0
        self._stack.addWidget(self._play_mode)   # index 1

        self._edit_mode.play_requested.connect(self._switch_to_play)
        self._play_mode.edit_requested.connect(self._switch_to_edit)

        self._stack.setCurrentIndex(self.EDIT_IDX)
        self._apply_global_style()

    # ------------------------------------------------------------------ #
    #  Mode switching                                                       #
    # ------------------------------------------------------------------ #
    def _switch_to_play(self):
        if not self.player_manager.players:
            QMessageBox.warning(
                self, "No Players",
                "Add at least one player in Edit Mode before starting the game.",
            )
            return
        self._play_mode.refresh()
        self._stack.setCurrentIndex(self.PLAY_IDX)
        self.setWindowTitle("Jeopardy! — Play Mode")

    def _switch_to_edit(self):
        self._edit_mode.refresh()
        self._stack.setCurrentIndex(self.EDIT_IDX)
        self.setWindowTitle("Jeopardy! — Edit Mode")

    # ------------------------------------------------------------------ #
    #  Global style                                                         #
    # ------------------------------------------------------------------ #
    def _apply_global_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #252525; }
            QScrollBar:vertical {
                background: #2f2f2f; width: 12px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #505050; border-radius: 5px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #7daf8d; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal {
                background: #2f2f2f; height: 12px;
            }
            QScrollBar::handle:horizontal {
                background: #505050; border-radius: 5px; min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover { background: #7daf8d; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            QToolTip { background: #38332e; color: #e5ddd5; border: 1px solid #505050; }
        """)


# ------------------------------------------------------------------ #
#  Entry point                                                        #
# ------------------------------------------------------------------ #
def main():
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Jeopardy Game Builder")
    app.setApplicationVersion("1.0.0")

    # Global font — slightly larger base, with emoji fallback
    font = QFont("Segoe UI", 11)
    font.setFamilies(["Segoe UI", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"])
    app.setFont(font)

    # Dark warm-grey palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor("#252525"))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor("#e5ddd5"))
    palette.setColor(QPalette.ColorRole.Base,            QColor("#2f2f2f"))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor("#38332e"))
    palette.setColor(QPalette.ColorRole.Text,            QColor("#e5ddd5"))
    palette.setColor(QPalette.ColorRole.Button,          QColor("#3a3a3a"))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor("#e5ddd5"))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor("#5a8a6a"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#e5ddd5"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9a9080"))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
