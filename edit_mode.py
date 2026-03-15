"""
edit_mode.py — Board editor UI.

Layout:
  Top toolbar: New / Save / Load / Play buttons + board-size spinboxes
  Center: scrollable grid — category headers (top row) + cell buttons
  Right panel: player list editor
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QPushButton, QLabel, QLineEdit, QSpinBox, QFileDialog,
    QDialog, QDialogButtonBox, QFormLayout, QMessageBox, QGroupBox,
    QListWidget, QListWidgetItem, QInputDialog, QSizePolicy, QFrame,
    QTabWidget, QMenu,
)

from board import Board, Cell
from players import PlayerManager

# ---- colour palette (matches play_mode.py) ----
BG_DARK     = "#252525"
BG_MID      = "#2f2f2f"
BG_WARM     = "#38332e"
ACCENT      = "#7daf8d"
ACCENT_HOV  = "#91c4a1"
ACCENT_DRK  = "#5a8a6a"
TEXT_PRI    = "#e5ddd5"
TEXT_MUT    = "#9a9080"
DOLLAR_TEXT = "#c8a96a"
BORDER      = "#505050"

HEADER_STYLE = f"""
    QLineEdit {{
        background: {BG_WARM};
        color: {TEXT_PRI};
        font-family: 'Segoe UI', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji';
        font-size: 15px;
        font-weight: bold;
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 5px;
        min-height: 42px;
    }}
"""

CELL_BUTTON_STYLE = f"""
    QPushButton {{
        background: {BG_MID};
        color: {TEXT_MUT};
        font-size: 14px;
        font-weight: bold;
        border: 1px solid {BORDER};
        border-radius: 5px;
        min-height: 54px;
    }}
    QPushButton:hover {{
        background: #3a3a3a;
        border-color: {ACCENT};
        color: {TEXT_PRI};
    }}
    QPushButton:pressed {{
        background: {BG_DARK};
    }}
"""

VALUE_EDIT_STYLE = f"""
    QLineEdit {{
        background: {BG_WARM};
        color: {DOLLAR_TEXT};
        font-size: 14px;
        font-weight: bold;
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 3px;
        min-height: 34px;
    }}
"""

# Full QSpinBox stylesheet — must include ::up-button / ::down-button rules
# or Qt hides the arrow buttons entirely when a partial stylesheet is applied.
_SPINBOX_STYLE = f"""
    QSpinBox {{
        background: {BG_WARM};
        color: {TEXT_PRI};
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 2px 22px 2px 6px;
    }}
    QSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 20px;
        border-left: 1px solid {BORDER};
        border-bottom: 1px solid {BORDER};
        border-top-right-radius: 5px;
        background: #3a3a3a;
    }}
    QSpinBox::up-button:hover   {{ background: {ACCENT_DRK}; }}
    QSpinBox::up-button:pressed {{ background: {ACCENT}; }}
    QSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 20px;
        border-left: 1px solid {BORDER};
        border-top: 1px solid {BORDER};
        border-bottom-right-radius: 5px;
        background: #3a3a3a;
    }}
    QSpinBox::down-button:hover   {{ background: {ACCENT_DRK}; }}
    QSpinBox::down-button:pressed {{ background: {ACCENT}; }}
"""


class CellEditorDialog(QDialog):
    """Tabbed editor for a cell's question and answer slides."""

    def __init__(self, cell: Cell, assets_dir: str, parent=None):
        super().__init__(parent)
        self.cell = cell
        self.assets_dir = assets_dir
        self.setWindowTitle("Edit Cell")
        self.setMinimumSize(720, 580)
        self.setStyleSheet(f"background: {BG_DARK}; color: {TEXT_PRI};")
        self._build_ui()

    def _build_ui(self):
        from slide_widgets import SlideEditor
        layout = QVBoxLayout(self)

        # Tab widget with Question / Answer tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 5px;"
            f" background: {BG_DARK}; }}"
            f"QTabBar::tab {{ background: {BG_MID}; color: {TEXT_MUT};"
            f" padding: 8px 20px; border: 1px solid {BORDER};"
            f" border-bottom: none; border-top-left-radius: 5px;"
            f" border-top-right-radius: 5px; margin-right: 2px; }}"
            f"QTabBar::tab:selected {{ background: {BG_WARM}; color: {ACCENT_HOV};"
            f" font-weight: bold; }}"
        )

        self._q_editor = SlideEditor(self.cell.question_slide, self.assets_dir, self)
        self._a_editor = SlideEditor(self.cell.answer_slide, self.assets_dir, self)
        self._tabs.addTab(self._q_editor, "Question")
        self._tabs.addTab(self._a_editor, "Answer")
        layout.addWidget(self._tabs, stretch=1)

        # OK / Cancel
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.setStyleSheet(f"color: {TEXT_PRI};")
        layout.addWidget(btns)

    def accept(self):
        self.cell.question_slide = self._q_editor.get_slide()
        self.cell.answer_slide = self._a_editor.get_slide()
        self._q_editor.stop_preview()
        self._a_editor.stop_preview()
        super().accept()

    def reject(self):
        self._q_editor.stop_preview()
        self._a_editor.stop_preview()
        super().reject()


class EditMode(QWidget):
    """
    Full edit-mode widget. Emits play_requested when the user clicks Play.
    """
    play_requested = pyqtSignal()

    def __init__(self, board: Board, player_manager: PlayerManager, assets_dir: str, parent=None):
        super().__init__(parent)
        self.board = board
        self.player_manager = player_manager
        self.assets_dir = assets_dir
        self._save_path: str = ""
        self._category_edits: list[QLineEdit] = []
        self._value_edits: list[QLineEdit] = []   # one per row
        self._cell_buttons: list[list[QPushButton]] = []
        self._build_ui()
        self._refresh_grid()

    # ------------------------------------------------------------------ #
    #  UI construction                                                      #
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ---- Toolbar ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        btn_new = QPushButton("New Board")
        btn_new.clicked.connect(self._on_new_board)
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._on_save)
        btn_save_as = QPushButton("Save As…")
        btn_save_as.clicked.connect(self._on_save_as)
        btn_load = QPushButton("Load…")
        btn_load.clicked.connect(self._on_load)

        for b in (btn_new, btn_save, btn_save_as, btn_load):
            b.setStyleSheet(
                f"QPushButton {{ background:{BG_MID}; color:{TEXT_PRI}; font-weight:bold;"
                f" border-radius:5px; padding:6px 16px; border:1px solid {BORDER}; font-size:13px; }}"
                f"QPushButton:hover {{ background:#3a3a3a; border-color:{ACCENT}; }}"
            )
            toolbar.addWidget(b)

        toolbar.addSpacing(20)

        # Board size controls
        size_label = QLabel("Cols:")
        size_label.setStyleSheet(f"color:{TEXT_MUT}; font-weight:bold;")
        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(1, 12)
        self._cols_spin.setValue(self.board.num_cols)
        self._cols_spin.setStyleSheet(_SPINBOX_STYLE)

        rows_label = QLabel("Rows:")
        rows_label.setStyleSheet(f"color:{TEXT_MUT}; font-weight:bold;")
        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, 10)
        self._rows_spin.setValue(self.board.num_rows)
        self._rows_spin.setStyleSheet(_SPINBOX_STYLE)

        btn_apply_size = QPushButton("Apply Size")
        btn_apply_size.clicked.connect(self._on_apply_size)
        btn_apply_size.setStyleSheet(
            f"QPushButton {{ background:{BG_MID}; color:{TEXT_PRI}; border-radius:5px;"
            f" padding:6px 12px; border:1px solid {BORDER}; }}"
            f"QPushButton:hover {{ background:#3a3a3a; border-color:{ACCENT}; }}"
        )

        toolbar.addWidget(size_label)
        toolbar.addWidget(self._cols_spin)
        toolbar.addWidget(rows_label)
        toolbar.addWidget(self._rows_spin)
        toolbar.addWidget(btn_apply_size)

        toolbar.addStretch()

        btn_play = QPushButton("▶  Play Game")
        btn_play.setStyleSheet(
            f"QPushButton {{ background:{ACCENT_DRK}; color:{TEXT_PRI}; font-weight:bold; font-size:15px;"
            f" border-radius:6px; padding:8px 22px; border:1px solid {ACCENT}; }}"
            f"QPushButton:hover {{ background:{ACCENT}; color:#111; }}"
        )
        btn_play.clicked.connect(self.play_requested.emit)
        toolbar.addWidget(btn_play)

        root.addLayout(toolbar)

        # ---- Main horizontal split: grid | players ----
        h_split = QHBoxLayout()
        h_split.setSpacing(8)

        # Grid (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{BG_DARK}; border:none;")
        self._grid_container = QWidget()
        self._grid_container.setStyleSheet(f"background:{BG_DARK};")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(6)
        scroll.setWidget(self._grid_container)
        h_split.addWidget(scroll, stretch=4)

        # Player panel
        player_panel = self._build_player_panel()
        h_split.addWidget(player_panel, stretch=1)

        root.addLayout(h_split)

    def _build_player_panel(self) -> QWidget:
        panel = QGroupBox("Players")
        panel.setStyleSheet(
            f"QGroupBox {{ color:{ACCENT_HOV}; font-weight:bold; font-size:13px;"
            f" border:1px solid {BORDER}; border-radius:5px; margin-top:8px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left:10px; }}"
        )
        layout = QVBoxLayout(panel)

        self._player_list = QListWidget()
        self._player_list.setStyleSheet(
            f"background:{BG_MID}; color:{TEXT_PRI}; border:1px solid {BORDER};"
            f" font-size:13px;"
        )
        layout.addWidget(self._player_list)

        btn_add = QPushButton("Add Player")
        btn_add.setStyleSheet(
            f"QPushButton {{ background:#283828; color:#aaddaa; border-radius:5px;"
            f" padding:6px; border:1px solid {ACCENT_DRK}; font-size:13px; }}"
            f"QPushButton:hover {{ background:#385038; }}"
        )
        btn_add.clicked.connect(self._on_add_player)

        btn_remove = QPushButton("Remove Selected")
        btn_remove.setStyleSheet(
            f"QPushButton {{ background:#3a2828; color:#ddaaaa; border-radius:5px;"
            f" padding:6px; border:1px solid #5a3838; font-size:13px; }}"
            f"QPushButton:hover {{ background:#503535; }}"
        )
        btn_remove.clicked.connect(self._on_remove_player)

        layout.addWidget(btn_add)
        layout.addWidget(btn_remove)

        neg_hint = QLabel("Negative scores: ON by default\n(toggle in Play Mode)")
        neg_hint.setStyleSheet(f"color:{TEXT_MUT}; font-size:11px;")
        neg_hint.setWordWrap(True)
        layout.addWidget(neg_hint)

        self._refresh_player_list()
        return panel

    # ------------------------------------------------------------------ #
    #  Grid refresh                                                         #
    # ------------------------------------------------------------------ #
    def _clear_grid(self):
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._category_edits.clear()
        self._value_edits.clear()
        self._cell_buttons.clear()

    def _refresh_grid(self):
        self._clear_grid()
        b = self.board

        # Row-value column (col 0) header placeholder
        placeholder = QLabel("")
        self._grid_layout.addWidget(placeholder, 0, 0)

        # Category headers — row 0, cols 1..num_cols
        for c in range(b.num_cols):
            edit = QLineEdit(b.categories[c])
            edit.setStyleSheet(HEADER_STYLE)
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit.textChanged.connect(lambda text, col=c: self._on_category_changed(col, text))
            self._grid_layout.addWidget(edit, 0, c + 1)
            self._category_edits.append(edit)

        # Rows 1..num_rows
        for r in range(b.num_rows):
            # Row value editor (col 0)
            val_edit = QLineEdit(f"${b.row_values[r]}")
            val_edit.setStyleSheet(VALUE_EDIT_STYLE)
            val_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_edit.setFixedWidth(80)
            val_edit.editingFinished.connect(
                lambda row=r, ed=val_edit: self._on_value_changed(row, ed.text())
            )
            self._grid_layout.addWidget(val_edit, r + 1, 0)
            self._value_edits.append(val_edit)

            row_buttons = []
            for c in range(b.num_cols):
                cell = b.cells[r][c]
                btn = QPushButton(self._cell_label(cell))
                btn.setStyleSheet(CELL_BUTTON_STYLE)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                btn.setMinimumSize(100, 55)
                btn.clicked.connect(lambda _, row=r, col=c: self._open_cell_editor(row, col))
                btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda _, row=r, col=c: self._on_cell_right_clicked(row, col)
                )
                self._grid_layout.addWidget(btn, r + 1, c + 1)
                row_buttons.append(btn)
            self._cell_buttons.append(row_buttons)

    def _cell_label(self, cell: Cell) -> str:
        parts = []
        if cell.question:
            q_short = cell.question[:28] + "…" if len(cell.question) > 28 else cell.question
            parts.append(q_short)
        total = len(cell.question_slide.assets) + len(cell.answer_slide.assets)
        if total:
            parts.append(f"[{total} asset{'s' if total != 1 else ''}]")
        return "\n".join(parts) if parts else "(empty)"

    # ------------------------------------------------------------------ #
    #  Event handlers                                                       #
    # ------------------------------------------------------------------ #
    def _on_category_changed(self, col: int, text: str):
        self.board.categories[col] = text

    def _on_value_changed(self, row: int, text: str):
        clean = text.replace("$", "").replace(",", "").strip()
        try:
            val = int(clean)
            self.board.row_values[row] = val
            for c in range(self.board.num_cols):
                self.board.cells[row][c].value = val
        except ValueError:
            pass

    def _on_cell_right_clicked(self, row: int, col: int):
        _menu_style = (
            f"QMenu {{ background:{BG_MID}; color:{TEXT_PRI}; border:1px solid {BORDER};"
            f" font-size:14px; padding:4px; }}"
            f"QMenu::item {{ padding:8px 20px; border-radius:4px; }}"
            f"QMenu::item:selected {{ background:{ACCENT}; }}"
            f"QMenu::separator {{ height:1px; background:{BORDER}; margin:4px 8px; }}"
        )
        menu = QMenu(self)
        menu.setStyleSheet(_menu_style)

        swap_menu = menu.addMenu("Swap With…")
        swap_menu.setStyleSheet(_menu_style)
        swap_actions = {}
        for r in range(self.board.num_rows):
            if r == row:
                continue
            other = self.board.cells[r][col]
            label = f"Row {r + 1}  (${other.value:,})"
            act = swap_menu.addAction(label)
            swap_actions[act] = r

        action = menu.exec(QCursor.pos())
        if action in swap_actions:
            self._swap_cells(row, swap_actions[action], col)

    def _swap_cells(self, row_a: int, row_b: int, col: int):
        a = self.board.cells[row_a][col]
        b = self.board.cells[row_b][col]
        a.question_slide, b.question_slide = b.question_slide, a.question_slide
        a.answer_slide, b.answer_slide = b.answer_slide, a.answer_slide
        self._cell_buttons[row_a][col].setText(self._cell_label(a))
        self._cell_buttons[row_b][col].setText(self._cell_label(b))

    def _open_cell_editor(self, row: int, col: int):
        cell = self.board.cells[row][col]
        dlg = CellEditorDialog(cell, self.assets_dir, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._cell_buttons[row][col].setText(self._cell_label(cell))

    def _on_apply_size(self):
        new_cols = self._cols_spin.value()
        new_rows = self._rows_spin.value()
        self.board.set_dimensions(new_rows, new_cols)
        self._refresh_grid()

    def _on_new_board(self):
        reply = QMessageBox.question(
            self, "New Board",
            "Create a blank new board? Unsaved changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.board.__init__()
            self._cols_spin.setValue(self.board.num_cols)
            self._rows_spin.setValue(self.board.num_rows)
            self._refresh_grid()

    def _on_save(self):
        if self._save_path:
            self.board.save(self._save_path, self.assets_dir)
        else:
            self._on_save_as()

    def _on_save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Board", "", "Jeopardy Board (*.json)"
        )
        if path:
            if not path.endswith(".json"):
                path += ".json"
            self._save_path = path
            self.board.save(path, self.assets_dir)

    def _on_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Board", "", "Jeopardy Board (*.json)"
        )
        if path:
            try:
                loaded = Board.load(path)
                self.board.__dict__.update(loaded.__dict__)
                self._save_path = path
                self._cols_spin.setValue(self.board.num_cols)
                self._rows_spin.setValue(self.board.num_rows)
                self._refresh_grid()
            except Exception as e:
                QMessageBox.critical(self, "Load Error", str(e))

    # ------------------------------------------------------------------ #
    #  Player panel                                                         #
    # ------------------------------------------------------------------ #
    def _refresh_player_list(self):
        self._player_list.clear()
        for p in self.player_manager.players:
            self._player_list.addItem(p.name)

    def _on_add_player(self):
        name, ok = QInputDialog.getText(self, "Add Player", "Player name:")
        if ok and name.strip():
            try:
                self.player_manager.add_player(name.strip())
                self._refresh_player_list()
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))

    def _on_remove_player(self):
        item = self._player_list.currentItem()
        if item:
            self.player_manager.remove_player(item.text())
            self._refresh_player_list()

    # ------------------------------------------------------------------ #
    #  Called from main when switching back from play mode                 #
    # ------------------------------------------------------------------ #
    def refresh(self):
        self._refresh_grid()
        self._refresh_player_list()
