"""
play_mode.py — Gameplay UI: Jeopardy board grid + cell overlay + scoreboard.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy, QDialog,
    QMessageBox, QCheckBox,
)

from board import Board, Cell
from players import PlayerManager
from media_widget import MediaWidget

_EMOJI_FAMILIES = ["Segoe UI", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"]

def _font(size: int, bold: bool = False) -> QFont:
    """Create a QFont with emoji fallback support."""
    f = QFont("Segoe UI", size)
    f.setFamilies(_EMOJI_FAMILIES)
    f.setBold(bold)
    return f

# ------------------------------------------------------------------ #
#  Colour palette — dark grey / warm brown / sage green               #
# ------------------------------------------------------------------ #
BG_DARK      = "#252525"   # main window / board background
BG_MID       = "#2f2f2f"   # panels, cards
BG_WARM      = "#38332e"   # warm brownish surface
ACCENT       = "#7daf8d"   # sage green
ACCENT_HOV   = "#91c4a1"   # hover
ACCENT_DRK   = "#5a8a6a"   # pressed
TEXT_PRI     = "#e5ddd5"   # primary text (warm off-white)
TEXT_MUT     = "#9a9080"   # muted/secondary text
CELL_BG      = "#3a3a3a"   # board cell background
CELL_HOV     = "#4a4a4a"   # cell hover
CELL_PRESS   = "#2a2a2a"   # cell pressed
CELL_USED    = "#282828"   # used cell
CELL_USED_T  = "#454545"   # used cell text
CAT_BG       = "#2e332e"   # category header (slightly green-tinted)
SCORE_POS    = "#7daf8d"   # positive score
SCORE_NEG    = "#c97878"   # negative score
BORDER       = "#505050"   # general border
OVERLAY_BG   = "#1c1c1c"   # overlay dialog background
ANSWER_BG    = "#252e25"   # answer reveal background
DOLLAR_TEXT  = "#c8a96a"   # warm amber for dollar amounts

CATEGORY_STYLE = f"""
    QLabel {{
        background: {CAT_BG};
        color: {TEXT_PRI};
        font-family: 'Segoe UI', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji';
        font-size: 16px;
        font-weight: bold;
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 8px;
        min-height: 54px;
        qproperty-alignment: AlignCenter;
    }}
"""

CELL_STYLE = f"""
    QPushButton {{
        background: {CELL_BG};
        color: {DOLLAR_TEXT};
        font-size: 26px;
        font-weight: bold;
        border: 1px solid {BORDER};
        border-radius: 6px;
        min-height: 75px;
    }}
    QPushButton:hover {{
        background: {CELL_HOV};
        border-color: {ACCENT};
        color: {ACCENT_HOV};
    }}
    QPushButton:pressed {{
        background: {CELL_PRESS};
    }}
"""

CELL_USED_STYLE = f"""
    QPushButton {{
        background: {CELL_USED};
        color: {CELL_USED_T};
        font-size: 26px;
        font-weight: bold;
        border: 1px solid #353535;
        border-radius: 6px;
        min-height: 75px;
    }}
"""

SCOREBOARD_STYLE = f"""
    QFrame {{
        background: {BG_MID};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
"""


def _btn(bg, fg, bd, hov):
    return (
        f"QPushButton {{ background:{bg}; color:{fg}; font-weight:bold;"
        f" border-radius:5px; padding:6px 14px; border:1px solid {bd}; }}"
        f"QPushButton:hover {{ background:{hov}; }}"
    )


# ------------------------------------------------------------------ #
#  Cell overlay dialog                                                #
# ------------------------------------------------------------------ #
class CellOverlay(QDialog):
    winner_selected = pyqtSignal(str, int)   # (player_name, delta)

    def __init__(self, cell: Cell, assets_dir: str, players: list,
                 allow_negatives: bool, parent=None):
        super().__init__(parent)
        self.cell = cell
        self.assets_dir = assets_dir
        self.players = players
        self.allow_negatives = allow_negatives

        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"background: {OVERLAY_BG}; color: {TEXT_PRI};")
        self.setModal(True)
        self._build_ui()

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self.reject)

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            r = self.parent().rect()
            g = self.parent().mapToGlobal(r.topLeft())
            self.setGeometry(g.x(), g.y(), r.width(), r.height())
        self._media.play()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 32, 48, 32)
        layout.setSpacing(16)

        # Value badge
        val_label = QLabel(f"${self.cell.value:,}")
        val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_label.setFont(_font(30, bold=True))
        val_label.setStyleSheet(f"color: {DOLLAR_TEXT};")
        layout.addWidget(val_label)

        # Media widget — show_controls=True for video/audio transport bar
        self._media = MediaWidget(auto_play=False, show_controls=True)
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
        self._question_label.setFont(_font(23))
        self._question_label.setStyleSheet(f"color: {TEXT_PRI}; padding: 16px;")
        layout.addWidget(self._question_label)

        # Answer (hidden initially)
        self._answer_label = QLabel(f"A: {self.cell.answer}" if self.cell.answer else "")
        self._answer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._answer_label.setWordWrap(True)
        self._answer_label.setFont(_font(19))
        self._answer_label.setStyleSheet(
            f"color: {ACCENT_HOV}; padding: 12px;"
            f" background: {ANSWER_BG}; border-radius: 8px;"
            f" border: 1px solid {ACCENT_DRK};"
        )
        self._answer_label.setVisible(False)
        layout.addWidget(self._answer_label)

        # Reveal / Close row
        btn_row = QHBoxLayout()

        self._reveal_btn = QPushButton("Reveal Answer")
        self._reveal_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_WARM}; color:{DOLLAR_TEXT}; font-weight:bold;"
            f" border-radius:6px; padding:10px 22px; font-size:15px;"
            f" border:1px solid #60502a; }}"
            f"QPushButton:hover {{ background:#4a4030; }}"
        )
        self._reveal_btn.clicked.connect(self._reveal_answer)
        btn_row.addWidget(self._reveal_btn)

        btn_row.addStretch()

        btn_close = QPushButton("Close  [Esc]")
        btn_close.setStyleSheet(
            f"QPushButton {{ background:#3a2828; color:{TEXT_PRI}; border-radius:6px;"
            f" padding:10px 22px; font-size:15px; border:1px solid #5a3838; }}"
            f"QPushButton:hover {{ background:#503535; }}"
        )
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        # Award section
        award_lbl = QLabel("Award points to:")
        award_lbl.setStyleSheet(f"color: {TEXT_MUT}; font-size: 14px;")
        award_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(award_lbl)

        award_row = QHBoxLayout()
        award_row.setSpacing(10)
        for p in self.players:
            btn = QPushButton(f"+ {p.name}")
            btn.setStyleSheet(
                f"QPushButton {{ background:#283828; color:#aaddaa; font-weight:bold;"
                f" font-size:14px; border-radius:6px; padding:9px 16px;"
                f" border:1px solid {ACCENT_DRK}; }}"
                f"QPushButton:hover {{ background:#385038; color:{TEXT_PRI}; }}"
            )
            btn.clicked.connect(lambda _, name=p.name: self._award(name, self.cell.value))
            award_row.addWidget(btn)
        layout.addLayout(award_row)

        if self.allow_negatives:
            deduct_lbl = QLabel("Deduct (wrong answer):")
            deduct_lbl.setStyleSheet(f"color: {TEXT_MUT}; font-size: 14px;")
            deduct_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(deduct_lbl)

            deduct_row = QHBoxLayout()
            deduct_row.setSpacing(10)
            for p in self.players:
                btn = QPushButton(f"- {p.name}")
                btn.setStyleSheet(
                    f"QPushButton {{ background:#382828; color:#ddaaaa; font-weight:bold;"
                    f" font-size:14px; border-radius:6px; padding:9px 16px;"
                    f" border:1px solid #7a4040; }}"
                    f"QPushButton:hover {{ background:#503838; color:{TEXT_PRI}; }}"
                )
                btn.clicked.connect(lambda _, name=p.name: self._award(name, -self.cell.value))
                deduct_row.addWidget(btn)
            layout.addLayout(deduct_row)

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

    def __init__(self, board: Board, player_manager: PlayerManager,
                 assets_dir: str, parent=None):
        super().__init__(parent)
        self.board = board
        self.player_manager = player_manager
        self.assets_dir = assets_dir
        self._cell_buttons: list[list[QPushButton]] = []
        self._score_labels: dict[str, QLabel] = {}
        self.setStyleSheet(f"background: {BG_DARK};")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ---- Top bar ----
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        btn_edit = QPushButton("← Edit Board")
        btn_edit.setStyleSheet(_btn(BG_MID, TEXT_PRI, BORDER, "#3a3a3a"))
        btn_edit.clicked.connect(self.edit_requested.emit)
        top_bar.addWidget(btn_edit)

        btn_reset = QPushButton("Reset Board")
        btn_reset.setStyleSheet(_btn("#3a2828", TEXT_PRI, "#5a3838", "#503535"))
        btn_reset.clicked.connect(self._on_reset)
        top_bar.addWidget(btn_reset)

        self._neg_checkbox = QCheckBox("Allow negative scores")
        self._neg_checkbox.setChecked(self.board.allow_negatives)
        self._neg_checkbox.setStyleSheet(f"color: {TEXT_MUT};")
        self._neg_checkbox.toggled.connect(self._on_neg_toggle)
        top_bar.addWidget(self._neg_checkbox)

        top_bar.addStretch()

        title = QLabel("JEOPARDY!")
        title.setStyleSheet(
            f"color: {ACCENT}; font-size: 24px; font-weight: bold; letter-spacing: 5px;"
        )
        top_bar.addWidget(title)
        top_bar.addStretch()

        root.addLayout(top_bar)

        # ---- Center: board + scoreboard ----
        center = QHBoxLayout()
        center.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{BG_DARK}; border:none;")
        self._board_widget = QWidget()
        self._board_widget.setStyleSheet(f"background:{BG_DARK};")
        self._board_layout = QGridLayout(self._board_widget)
        self._board_layout.setSpacing(6)
        scroll.setWidget(self._board_widget)
        center.addWidget(scroll, stretch=5)

        self._score_panel = self._build_scoreboard()
        center.addWidget(self._score_panel, stretch=1)

        root.addLayout(center, stretch=1)

        self._build_board_grid()

    def _build_scoreboard(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(SCOREBOARD_STYLE)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        frame.setMinimumWidth(180)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QLabel("SCORES")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFont(_font(14, bold=True))
        header.setStyleSheet(f"color: {ACCENT}; letter-spacing: 3px;")
        layout.addWidget(header)

        layout.addWidget(self._h_divider())

        self._score_layout = QVBoxLayout()
        self._score_layout.setSpacing(10)
        layout.addLayout(self._score_layout)
        layout.addStretch()

        btn_reset_scores = QPushButton("Reset Scores")
        btn_reset_scores.setStyleSheet(_btn("#3a2828", TEXT_PRI, "#5a3838", "#503535"))
        btn_reset_scores.clicked.connect(self._on_reset_scores)
        layout.addWidget(btn_reset_scores)

        self._refresh_scoreboard()
        return frame

    def _h_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER};")
        return line

    def _build_board_grid(self):
        while self._board_layout.count():
            item = self._board_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cell_buttons.clear()

        b = self.board

        for c in range(b.num_cols):
            lbl = QLabel(b.categories[c])
            lbl.setStyleSheet(CATEGORY_STYLE)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self._board_layout.addWidget(lbl, 0, c)

        for r in range(b.num_rows):
            row_buttons = []
            for c in range(b.num_cols):
                cell = b.cells[r][c]
                btn = QPushButton(f"${cell.value:,}")
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                btn.setMinimumSize(100, 75)
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
    #  Scoreboard                                                           #
    # ------------------------------------------------------------------ #
    def _refresh_scoreboard(self):
        while self._score_layout.count():
            item = self._score_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # clean up nested layout items
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
        self._score_labels.clear()

        for p in self.player_manager.players:
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background: {BG_WARM}; border-radius: 7px;"
                f" border: 1px solid {BORDER}; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(2)

            name_lbl = QLabel(p.name)
            name_lbl.setWordWrap(True)
            name_lbl.setFont(_font(13, bold=True))
            name_lbl.setStyleSheet(f"color: {TEXT_PRI}; border: none;")

            score_lbl = QLabel(f"${p.score:,}")
            score_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            score_lbl.setFont(_font(20, bold=True))
            color = SCORE_POS if p.score >= 0 else SCORE_NEG
            score_lbl.setStyleSheet(f"color: {color}; border: none;")

            card_layout.addWidget(name_lbl)
            card_layout.addWidget(score_lbl)
            self._score_layout.addWidget(card)
            self._score_labels[p.name] = score_lbl

    def _update_score_label(self, name: str, score: int):
        lbl = self._score_labels.get(name)
        if lbl:
            color = SCORE_POS if score >= 0 else SCORE_NEG
            # Only update colour — font is already set via setFont() at creation
            lbl.setStyleSheet(f"color: {color}; border: none;")
            lbl.setText(f"${score:,}")

    # ------------------------------------------------------------------ #
    #  Cell click                                                           #
    # ------------------------------------------------------------------ #
    def _on_cell_clicked(self, row: int, col: int):
        cell = self.board.cells[row][col]
        if cell.used:
            return

        overlay = CellOverlay(
            cell=cell,
            assets_dir=self.assets_dir,
            players=self.player_manager.players,
            allow_negatives=self.board.allow_negatives,
            parent=self,
        )
        overlay.winner_selected.connect(self._on_winner_selected)
        overlay.exec()

        cell.used = True
        btn = self._cell_buttons[row][col]
        btn.setStyleSheet(CELL_USED_STYLE)
        btn.setEnabled(False)

    def _on_winner_selected(self, name: str, delta: int):
        self.player_manager.award(name, delta)
        for p in self.player_manager.players:
            if p.name == name:
                self._update_score_label(name, p.score)
                break

    # ------------------------------------------------------------------ #
    #  Controls                                                             #
    # ------------------------------------------------------------------ #
    def _on_reset(self):
        reply = QMessageBox.question(
            self, "Reset Board", "Mark all cells as unused?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.board.reset_used()
            self._build_board_grid()

    def _on_reset_scores(self):
        reply = QMessageBox.question(
            self, "Reset Scores", "Reset all player scores to 0?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.player_manager.reset_scores()
            self._refresh_scoreboard()

    def _on_neg_toggle(self, checked: bool):
        self.board.allow_negatives = checked

    def refresh(self):
        self._neg_checkbox.setChecked(self.board.allow_negatives)
        self._build_board_grid()
        self._refresh_scoreboard()
