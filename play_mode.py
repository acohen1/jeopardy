"""
play_mode.py — Gameplay UI: Jeopardy board grid + cell overlay + scoreboard.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QCursor, QKeySequence, QShortcut
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy, QDialog,
    QMessageBox, QCheckBox, QMenu,
)

from board import Board, Cell
from players import PlayerManager
from slide_widgets import SlideRenderer, _font

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
    """Two-page gameplay overlay: question slide → answer slide."""
    winner_selected = pyqtSignal(str, int)   # (player_name, delta)

    def __init__(self, cell: Cell, assets_dir: str, players: list,
                 allow_negatives: bool, parent=None, start_page: int = 0):
        super().__init__(parent)
        self.cell = cell
        self.assets_dir = assets_dir
        self.players = players
        self.allow_negatives = allow_negatives
        self._start_page = start_page

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
        self._q_renderer.play()

    def _build_ui(self):
        from PyQt6.QtWidgets import QStackedWidget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 32, 48, 32)
        layout.setSpacing(16)

        # Top bar: nav buttons flanking the value badge
        _nav_btn_style = (
            f"QPushButton {{ background:transparent; color:{TEXT_MUT}; border-radius:5px;"
            f" padding:4px 12px; font-size:12px; border:1px solid {BORDER}; }}"
            f"QPushButton:hover {{ background:{BG_MID}; color:{TEXT_PRI}; border-color:#707070; }}"
        )
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        self._back_btn = QPushButton("← Question  [Q]")
        self._back_btn.setStyleSheet(_nav_btn_style)
        self._back_btn.setFixedHeight(28)
        self._back_btn.setVisible(False)
        self._back_btn.clicked.connect(self._back_to_question)
        back_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Q), self)
        back_shortcut.activated.connect(self._back_to_question)

        val_label = QLabel(f"${self.cell.value:,}")
        val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_label.setFont(_font(30, bold=True))
        val_label.setStyleSheet(f"color: {DOLLAR_TEXT};")

        self._close_btn = QPushButton("Close  [Esc]")
        self._close_btn.setStyleSheet(_nav_btn_style)
        self._close_btn.setFixedHeight(28)
        self._close_btn.setVisible(False)
        self._close_btn.clicked.connect(self.reject)

        self._reveal_btn = QPushButton("Reveal Answer  →  [A]")
        self._reveal_btn.setStyleSheet(_nav_btn_style)
        self._reveal_btn.setFixedHeight(28)
        self._reveal_btn.clicked.connect(self._reveal_answer)
        reveal_shortcut = QShortcut(QKeySequence(Qt.Key.Key_A), self)
        reveal_shortcut.activated.connect(self._reveal_answer)

        top_bar.addWidget(self._back_btn)
        top_bar.addStretch()
        top_bar.addWidget(val_label)
        top_bar.addStretch()
        top_bar.addWidget(self._reveal_btn)
        top_bar.addWidget(self._close_btn)
        layout.addLayout(top_bar)

        # Stacked pages: question (0) and answer (1)
        self._pages = QStackedWidget()
        layout.addWidget(self._pages, stretch=1)

        # Toast notification (hidden by default)
        self._toast = QLabel("")
        self._toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast.setStyleSheet(
            "background:#5a1a1a; color:#ffaaaa; border-radius:8px;"
            " padding:8px 20px; font-size:14px; font-weight:bold;"
        )
        self._toast.setVisible(False)
        self._toast_effect = QGraphicsOpacityEffect(self._toast)
        self._toast.setGraphicsEffect(self._toast_effect)
        self._toast_anim = QPropertyAnimation(self._toast_effect, b"opacity")
        self._toast_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._toast_hide_timer = QTimer(self)
        self._toast_hide_timer.setSingleShot(True)
        self._toast_hide_timer.timeout.connect(self._hide_toast)
        self._toast_anim.finished.connect(lambda: self._toast.setVisible(False))
        # Toast is a free-floating child — not in any layout
        self._toast.setParent(self)
        self._toast.setVisible(False)

        # ---- Page 0: Question ----
        q_page = QWidget()
        q_layout = QVBoxLayout(q_page)
        q_layout.setContentsMargins(0, 0, 0, 0)
        q_layout.setSpacing(12)

        self._q_renderer = SlideRenderer(auto_play=False, show_controls=True)
        self._q_renderer.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Expanding)
        self._q_renderer.load_slide(self.cell.question_slide, self.assets_dir)
        q_layout.addWidget(self._q_renderer, stretch=1)

        award_lbl_q = QLabel("Award points to:")
        award_lbl_q.setStyleSheet(f"color: {TEXT_MUT}; font-size: 14px;")
        award_lbl_q.setAlignment(Qt.AlignmentFlag.AlignCenter)
        q_layout.addWidget(award_lbl_q)

        award_row_q = QHBoxLayout()
        award_row_q.setSpacing(10)
        for p in self.players:
            btn = QPushButton(f"+ {p.name}")
            btn.setStyleSheet(
                f"QPushButton {{ background:#283828; color:#aaddaa; font-weight:bold;"
                f" font-size:14px; border-radius:6px; padding:9px 16px;"
                f" border:1px solid {ACCENT_DRK}; }}"
                f"QPushButton:hover {{ background:#385038; color:{TEXT_PRI}; }}"
            )
            btn.clicked.connect(lambda _, name=p.name: self._award_no_close(name, self.cell.value))
            award_row_q.addWidget(btn)
        q_layout.addLayout(award_row_q)

        if self.allow_negatives:
            deduct_lbl_q = QLabel("Deduct (wrong answer):")
            deduct_lbl_q.setStyleSheet(f"color: {TEXT_MUT}; font-size: 14px;")
            deduct_lbl_q.setAlignment(Qt.AlignmentFlag.AlignCenter)
            q_layout.addWidget(deduct_lbl_q)

            deduct_row_q = QHBoxLayout()
            deduct_row_q.setSpacing(10)
            for p in self.players:
                btn = QPushButton(f"- {p.name}")
                btn.setStyleSheet(
                    f"QPushButton {{ background:#382828; color:#ddaaaa; font-weight:bold;"
                    f" font-size:14px; border-radius:6px; padding:9px 16px;"
                    f" border:1px solid #7a4040; }}"
                    f"QPushButton:hover {{ background:#503838; color:{TEXT_PRI}; }}"
                )
                btn.clicked.connect(lambda _, name=p.name, b=btn: self._deduct_with_feedback(b, name))
                deduct_row_q.addWidget(btn)
            q_layout.addLayout(deduct_row_q)


        self._pages.addWidget(q_page)

        # ---- Page 1: Answer ----
        a_page = QWidget()
        a_layout = QVBoxLayout(a_page)
        a_layout.setContentsMargins(0, 0, 0, 0)
        a_layout.setSpacing(12)

        self._a_renderer = SlideRenderer(auto_play=False, show_controls=True)
        self._a_renderer.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Expanding)
        self._a_renderer.load_slide(self.cell.answer_slide, self.assets_dir)
        a_layout.addWidget(self._a_renderer, stretch=1)

        # Award section
        award_lbl = QLabel("Award points to:")
        award_lbl.setStyleSheet(f"color: {TEXT_MUT}; font-size: 14px;")
        award_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        a_layout.addWidget(award_lbl)

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
        a_layout.addLayout(award_row)

        if self.allow_negatives:
            deduct_lbl = QLabel("Deduct (wrong answer):")
            deduct_lbl.setStyleSheet(f"color: {TEXT_MUT}; font-size: 14px;")
            deduct_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            a_layout.addWidget(deduct_lbl)

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
            a_layout.addLayout(deduct_row)

        self._pages.addWidget(a_page)
        self._pages.setCurrentIndex(self._start_page)
        if self._start_page == 1:
            self._reveal_btn.setVisible(False)
            self._back_btn.setVisible(True)
            self._close_btn.setVisible(True)
            self._a_renderer.play()
        else:
            self._q_renderer.play()

    def _reveal_answer(self):
        self._q_renderer.stop()
        self._pages.setCurrentIndex(1)
        self._reveal_btn.setVisible(False)
        self._back_btn.setVisible(True)
        self._close_btn.setVisible(True)
        self._a_renderer.play()

    def _back_to_question(self):
        self._a_renderer.stop()
        self._pages.setCurrentIndex(0)
        self._reveal_btn.setVisible(True)
        self._back_btn.setVisible(False)
        self._close_btn.setVisible(False)
        self._q_renderer.play()

    def _award(self, name: str, delta: int):
        self.winner_selected.emit(name, delta)
        if delta > 0:
            self._q_renderer.stop()
            self._a_renderer.stop()
            self.accept()

    def _award_no_close(self, name: str, delta: int):
        self.winner_selected.emit(name, delta)
        self._show_toast(f"+ ${delta:,}  to  {name}", positive=True)

    def _deduct_with_feedback(self, btn: QPushButton, name: str):
        self._award(name, -self.cell.value)
        self._flash_button(btn)
        self._show_toast(f"- ${self.cell.value:,}  from  {name}", positive=False)

    def _flash_button(self, btn: QPushButton):
        normal_style = btn.styleSheet()
        btn.setStyleSheet(
            "QPushButton { background:#cc2222; color:#ffffff; font-weight:bold;"
            " font-size:14px; border-radius:6px; padding:9px 16px; border:1px solid #ff4444; }"
        )
        QTimer.singleShot(300, lambda: btn.setStyleSheet(normal_style))

    def _show_toast(self, text: str, positive: bool = False):
        self._toast_hide_timer.stop()
        self._toast_anim.stop()
        self._toast.setText(text)
        if positive:
            self._toast.setStyleSheet(
                "background:#1a5a1a; color:#aaffaa; border-radius:8px;"
                " padding:8px 20px; font-size:14px; font-weight:bold;"
            )
        else:
            self._toast.setStyleSheet(
                "background:#5a1a1a; color:#ffaaaa; border-radius:8px;"
                " padding:8px 20px; font-size:14px; font-weight:bold;"
            )
        self._toast.adjustSize()
        # Position bottom-centre, just above the reveal button (~150px from bottom)
        margin = 140
        x = (self.width() - self._toast.width()) // 2
        y = self.height() - self._toast.height() - margin
        self._toast.setGeometry(x, y, self._toast.width(), self._toast.height())
        self._toast.raise_()
        self._toast_effect.setOpacity(1.0)
        self._toast.setVisible(True)
        self._toast_hide_timer.start(1500)

    def _hide_toast(self):
        self._toast_anim.setDuration(400)
        self._toast_anim.setStartValue(1.0)
        self._toast_anim.setEndValue(0.0)
        self._toast_anim.start()

    def reject(self):
        self._q_renderer.stop()
        self._a_renderer.stop()
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
                    btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    btn.customContextMenuRequested.connect(
                        lambda _, row=r, col=c: self._on_cell_right_clicked(row, col)
                    )
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
        self._open_overlay(row, col, start_page=0)
        cell.used = True
        btn = self._cell_buttons[row][col]
        btn.setStyleSheet(CELL_USED_STYLE)
        btn.clicked.disconnect()
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda _, r=row, c=col: self._on_cell_right_clicked(r, c)
        )

    def _open_overlay(self, row: int, col: int, start_page: int = 0):
        overlay = CellOverlay(
            cell=self.board.cells[row][col],
            assets_dir=self.assets_dir,
            players=self.player_manager.players,
            allow_negatives=self.board.allow_negatives,
            parent=self,
            start_page=start_page,
        )
        overlay.winner_selected.connect(self._on_winner_selected)
        overlay.exec()

    def _on_cell_right_clicked(self, row: int, col: int):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_MID}; color:{TEXT_PRI}; border:1px solid {BORDER};"
            f" font-size:14px; padding:4px; }}"
            f"QMenu::item {{ padding:8px 20px; border-radius:4px; }}"
            f"QMenu::item:selected {{ background:{ACCENT_DRK}; }}"
            f"QMenu::separator {{ height:1px; background:{BORDER}; margin:4px 8px; }}"
        )
        act_review = menu.addAction("Review")
        menu.addSeparator()
        act_reset = menu.addAction("Reset Cell")

        action = menu.exec(QCursor.pos())
        if action == act_review:
            self._open_overlay(row, col, start_page=0)
        elif action == act_reset:
            self._reset_cell(row, col)

    def _reset_cell(self, row: int, col: int):
        cell = self.board.cells[row][col]
        cell.used = False
        btn = self._cell_buttons[row][col]
        btn.setStyleSheet(CELL_STYLE)
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        btn.customContextMenuRequested.disconnect()
        btn.clicked.connect(lambda _, r=row, c=col: self._on_cell_clicked(r, c))

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
