"""
play_mode.py — Gameplay UI: Jeopardy board grid + cell overlay + scoreboard.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor, QPalette, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy, QDialog,
    QMessageBox, QCheckBox,
)

from board import Board, Cell
from players import PlayerManager
from media_widget import MediaWidget

# ------------------------------------------------------------------ #
#  Colour constants                                                    #
# ------------------------------------------------------------------ #
BOARD_BG = "#000033"
CELL_BLUE = "#060CE9"
CELL_HOVER = "#1a1aff"
CELL_USED_BG = "#111133"
CELL_USED_TEXT = "#333366"
CATEGORY_BG = "#04089A"
GOLD = "#FFD700"
WHITE = "#FFFFFF"
SCORE_BG = "#000022"

CATEGORY_STYLE = """
    QLabel {
        background: #04089A;
        color: white;
        font-size: 15px;
        font-weight: bold;
        border: 2px solid #3333cc;
        border-radius: 4px;
        padding: 6px;
        min-height: 50px;
        qproperty-alignment: AlignCenter;
    }
"""

CELL_STYLE = """
    QPushButton {
        background: #060CE9;
        color: #FFD700;
        font-size: 24px;
        font-weight: bold;
        border: 3px solid #3333ff;
        border-radius: 6px;
        min-height: 70px;
    }
    QPushButton:hover {
        background: #1a1aff;
        border-color: #FFD700;
    }
    QPushButton:pressed {
        background: #04089A;
    }
"""

CELL_USED_STYLE = """
    QPushButton {
        background: #111133;
        color: #333366;
        font-size: 24px;
        font-weight: bold;
        border: 3px solid #1a1a44;
        border-radius: 6px;
        min-height: 70px;
    }
"""

SCOREBOARD_STYLE = """
    QFrame {
        background: #000022;
        border: 2px solid #3333cc;
        border-radius: 6px;
    }
"""


# ------------------------------------------------------------------ #
#  Cell overlay dialog                                                #
# ------------------------------------------------------------------ #
class CellOverlay(QDialog):
    """
    Fullscreen-ish overlay shown when a cell is clicked.
    Shows question + media. Host assigns a winner by clicking a player button.
    """
    winner_selected = pyqtSignal(str, int)   # (player_name, value)

    def __init__(
        self,
        cell: Cell,
        assets_dir: str,
        players: list,
        allow_negatives: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.cell = cell
        self.assets_dir = assets_dir
        self.players = players
        self.allow_negatives = allow_negatives
        self._answered = False

        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setStyleSheet("background: #06001a; color: white;")
        self.setModal(True)
        self._build_ui()

        # Escape key closes
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self.reject)

    def showEvent(self, event):
        super().showEvent(event)
        # Resize to parent window
        if self.parent():
            parent_rect = self.parent().rect()
            global_pos = self.parent().mapToGlobal(parent_rect.topLeft())
            self.setGeometry(
                global_pos.x(), global_pos.y(),
                parent_rect.width(), parent_rect.height()
            )
        self._media.play()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        # Value badge
        val_label = QLabel(f"${self.cell.value:,}")
        val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(28)
        font.setBold(True)
        val_label.setFont(font)
        val_label.setStyleSheet("color: #FFD700;")
        layout.addWidget(val_label)

        # Media widget (hidden if no asset)
        self._media = MediaWidget(auto_play=False)
        self._media.setMinimumHeight(220)
        self._media.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if self.cell.asset_path and self.cell.asset_type:
            full = os.path.join(self.assets_dir, self.cell.asset_path)
            self._media.load(full, self.cell.asset_type)
            layout.addWidget(self._media)
        else:
            self._media.setVisible(False)

        # Question text
        self._question_label = QLabel(self.cell.question or "(No question text)")
        self._question_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._question_label.setWordWrap(True)
        qfont = QFont()
        qfont.setPointSize(22)
        self._question_label.setFont(qfont)
        self._question_label.setStyleSheet("color: white; padding: 16px;")
        layout.addWidget(self._question_label)

        # Answer (hidden initially)
        self._answer_label = QLabel(f"A: {self.cell.answer}" if self.cell.answer else "")
        self._answer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._answer_label.setWordWrap(True)
        afont = QFont()
        afont.setPointSize(18)
        self._answer_label.setFont(afont)
        self._answer_label.setStyleSheet("color: #FFD700; padding: 8px; background: #1a0044; border-radius: 6px;")
        self._answer_label.setVisible(False)
        layout.addWidget(self._answer_label)

        # --- Buttons row ---
        btn_row = QHBoxLayout()

        self._reveal_btn = QPushButton("Reveal Answer")
        self._reveal_btn.setStyleSheet(
            "QPushButton { background:#444400; color:#FFD700; font-weight:bold;"
            " border-radius:6px; padding:10px 20px; font-size:14px; }"
            "QPushButton:hover { background:#666600; }"
        )
        self._reveal_btn.clicked.connect(self._reveal_answer)
        btn_row.addWidget(self._reveal_btn)

        btn_row.addStretch()

        btn_close = QPushButton("Close  [Esc]")
        btn_close.setStyleSheet(
            "QPushButton { background:#330000; color:white; border-radius:6px;"
            " padding:10px 20px; font-size:14px; }"
            "QPushButton:hover { background:#550000; }"
        )
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

        # --- Award section ---
        award_label = QLabel("Award points to:")
        award_label.setStyleSheet("color: #aaaacc; font-size: 13px;")
        award_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(award_label)

        player_row = QHBoxLayout()
        player_row.setSpacing(10)
        for p in self.players:
            btn = QPushButton(f"✓ {p.name}")
            btn.setStyleSheet(
                "QPushButton { background:#004400; color:#aaffaa; font-weight:bold;"
                " font-size:13px; border-radius:6px; padding:8px 14px; }"
                "QPushButton:hover { background:#006600; color:white; }"
            )
            btn.clicked.connect(lambda _, name=p.name: self._award(name, self.cell.value))
            player_row.addWidget(btn)

        if self.allow_negatives:
            deduct_label = QLabel("Deduct (wrong):")
            deduct_label.setStyleSheet("color: #aaaacc; font-size: 13px;")
            layout.addWidget(deduct_label)

            deduct_row = QHBoxLayout()
            deduct_row.setSpacing(10)
            for p in self.players:
                btn = QPushButton(f"✗ {p.name}")
                btn.setStyleSheet(
                    "QPushButton { background:#440000; color:#ffaaaa; font-weight:bold;"
                    " font-size:13px; border-radius:6px; padding:8px 14px; }"
                    "QPushButton:hover { background:#660000; color:white; }"
                )
                btn.clicked.connect(lambda _, name=p.name: self._award(name, -self.cell.value))
                deduct_row.addWidget(btn)
            layout.addLayout(deduct_row)

        layout.addLayout(player_row)

    def _reveal_answer(self):
        self._answer_label.setVisible(True)
        self._reveal_btn.setEnabled(False)

    def _award(self, name: str, delta: int):
        self.winner_selected.emit(name, delta)
        self._media.stop()
        self.accept()

    def reject(self):
        self._media.stop()
        super().reject()


# ------------------------------------------------------------------ #
#  Play Mode main widget                                              #
# ------------------------------------------------------------------ #
class PlayMode(QWidget):
    edit_requested = pyqtSignal()

    def __init__(
        self,
        board: Board,
        player_manager: PlayerManager,
        assets_dir: str,
        parent=None,
    ):
        super().__init__(parent)
        self.board = board
        self.player_manager = player_manager
        self.assets_dir = assets_dir
        self._cell_buttons: list[list[QPushButton]] = []
        self._score_labels: dict[str, QLabel] = {}
        self.setStyleSheet(f"background: {BOARD_BG};")
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  Build UI                                                             #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ---- Top bar ----
        top_bar = QHBoxLayout()

        btn_edit = QPushButton("← Edit Board")
        btn_edit.setStyleSheet(
            "QPushButton { background:#333366; color:white; font-weight:bold;"
            " border-radius:4px; padding:6px 14px; }"
            "QPushButton:hover { background:#4444aa; }"
        )
        btn_edit.clicked.connect(self.edit_requested.emit)
        top_bar.addWidget(btn_edit)

        btn_reset = QPushButton("Reset Board")
        btn_reset.setStyleSheet(
            "QPushButton { background:#442200; color:white; border-radius:4px; padding:6px 14px; }"
            "QPushButton:hover { background:#663300; }"
        )
        btn_reset.clicked.connect(self._on_reset)
        top_bar.addWidget(btn_reset)

        self._neg_checkbox = QCheckBox("Allow negative scores")
        self._neg_checkbox.setChecked(self.board.allow_negatives)
        self._neg_checkbox.setStyleSheet("color: white;")
        self._neg_checkbox.toggled.connect(self._on_neg_toggle)
        top_bar.addWidget(self._neg_checkbox)

        top_bar.addStretch()

        title = QLabel("JEOPARDY!")
        title.setStyleSheet("color:#FFD700; font-size:22px; font-weight:bold; letter-spacing:4px;")
        top_bar.addWidget(title)
        top_bar.addStretch()

        root.addLayout(top_bar)

        # ---- Center: board + scoreboard ----
        center = QHBoxLayout()
        center.setSpacing(10)

        # Board grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:#000033; border:none;")
        self._board_widget = QWidget()
        self._board_widget.setStyleSheet("background:#000033;")
        self._board_layout = QGridLayout(self._board_widget)
        self._board_layout.setSpacing(6)
        scroll.setWidget(self._board_widget)
        center.addWidget(scroll, stretch=5)

        # Scoreboard
        self._score_panel = self._build_scoreboard()
        center.addWidget(self._score_panel, stretch=1)

        root.addLayout(center, stretch=1)

        self._build_board_grid()

    def _build_scoreboard(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(SCOREBOARD_STYLE)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QLabel("SCORES")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("color:#FFD700; font-size:16px; font-weight:bold; letter-spacing:2px;")
        layout.addWidget(header)

        layout.addWidget(self._h_divider())

        self._score_layout = QVBoxLayout()
        self._score_layout.setSpacing(6)
        layout.addLayout(self._score_layout)
        layout.addStretch()

        btn_reset_scores = QPushButton("Reset Scores")
        btn_reset_scores.setStyleSheet(
            "QPushButton { background:#440000; color:white; border-radius:4px; padding:5px; }"
            "QPushButton:hover { background:#660000; }"
        )
        btn_reset_scores.clicked.connect(self._on_reset_scores)
        layout.addWidget(btn_reset_scores)

        self._refresh_scoreboard()
        return frame

    def _h_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #3333cc;")
        return line

    def _build_board_grid(self):
        # Clear
        while self._board_layout.count():
            item = self._board_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cell_buttons.clear()

        b = self.board

        # Category headers
        for c in range(b.num_cols):
            lbl = QLabel(b.categories[c])
            lbl.setStyleSheet(CATEGORY_STYLE)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self._board_layout.addWidget(lbl, 0, c)

        # Cell buttons
        for r in range(b.num_rows):
            row_buttons = []
            for c in range(b.num_cols):
                cell = b.cells[r][c]
                btn = QPushButton(f"${cell.value:,}")
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                btn.setMinimumSize(100, 70)
                if cell.used:
                    btn.setStyleSheet(CELL_USED_STYLE)
                    btn.setEnabled(False)
                else:
                    btn.setStyleSheet(CELL_STYLE)
                    btn.clicked.connect(lambda _, row=r, col=c: self._on_cell_clicked(row, col))
                self._board_layout.addWidget(btn, r + 1, c)
                row_buttons.append(btn)
            self._cell_buttons.append(row_buttons)

    # ------------------------------------------------------------------ #
    #  Scoreboard refresh                                                   #
    # ------------------------------------------------------------------ #
    def _refresh_scoreboard(self):
        # Clear existing score widgets
        while self._score_layout.count():
            item = self._score_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._score_labels.clear()

        for p in self.player_manager.players:
            row = QHBoxLayout()
            name_lbl = QLabel(p.name)
            name_lbl.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
            name_lbl.setWordWrap(True)
            score_lbl = QLabel(f"${p.score:,}")
            score_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            color = "#FFD700" if p.score >= 0 else "#FF4444"
            score_lbl.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
            row.addWidget(name_lbl, stretch=2)
            row.addWidget(score_lbl, stretch=1)
            self._score_layout.addLayout(row)
            self._score_labels[p.name] = score_lbl

    def _update_score_label(self, name: str, score: int):
        lbl = self._score_labels.get(name)
        if lbl:
            color = "#FFD700" if score >= 0 else "#FF4444"
            lbl.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
            lbl.setText(f"${score:,}")

    # ------------------------------------------------------------------ #
    #  Cell click                                                           #
    # ------------------------------------------------------------------ #
    def _on_cell_clicked(self, row: int, col: int):
        cell = self.board.cells[row][col]
        if cell.used:
            return

        players = self.player_manager.players
        overlay = CellOverlay(
            cell=cell,
            assets_dir=self.assets_dir,
            players=players,
            allow_negatives=self.board.allow_negatives,
            parent=self,
        )
        overlay.winner_selected.connect(self._on_winner_selected)
        overlay.exec()

        # Mark cell used after overlay closes (regardless of whether awarded)
        cell.used = True
        btn = self._cell_buttons[row][col]
        btn.setStyleSheet(CELL_USED_STYLE)
        btn.setEnabled(False)

    def _on_winner_selected(self, name: str, delta: int):
        self.player_manager.award(name, delta)
        # Find updated score
        for p in self.player_manager.players:
            if p.name == name:
                self._update_score_label(name, p.score)
                break

    # ------------------------------------------------------------------ #
    #  Controls                                                             #
    # ------------------------------------------------------------------ #
    def _on_reset(self):
        reply = QMessageBox.question(
            self, "Reset Board",
            "Mark all cells as unused and reset board state?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.board.reset_used()
            self._build_board_grid()

    def _on_reset_scores(self):
        reply = QMessageBox.question(
            self, "Reset Scores",
            "Reset all player scores to 0?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.player_manager.reset_scores()
            self._refresh_scoreboard()

    def _on_neg_toggle(self, checked: bool):
        self.board.allow_negatives = checked

    # ------------------------------------------------------------------ #
    #  Called when switching into play mode                                #
    # ------------------------------------------------------------------ #
    def refresh(self):
        self._neg_checkbox.setChecked(self.board.allow_negatives)
        self._build_board_grid()
        self._refresh_scoreboard()
