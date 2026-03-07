"""
main.py — Jeopardy Game entry point.

Manages switching between Edit Mode and Play Mode inside a single
QMainWindow using a QStackedWidget.
"""
from __future__ import annotations

import os
import sys

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
def _get_assets_dir() -> str:
    """Return absolute path to the assets/ folder next to the executable (or script)."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    assets = os.path.join(base, "assets")
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
            QMainWindow { background: #000033; }
            QScrollBar:vertical {
                background: #000033; width: 12px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #3333aa; border-radius: 5px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal {
                background: #000033; height: 12px;
            }
            QScrollBar::handle:horizontal {
                background: #3333aa; border-radius: 5px; min-width: 20px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            QToolTip { background: #1a1a3e; color: white; border: 1px solid #3333cc; }
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

    # Global font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#000033"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#0d0d3d"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1a1a44"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#060CE9"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3333ff"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFD700"))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
