"""
slide_widgets.py — Reusable widgets for slide editing and rendering.

CollageWidget   — displays 1-4 images in auto-arranged layouts
SlideRenderer   — plays back a Slide (collage / video / audio + text)
SlideEditor     — edits a Slide (text + asset list + preview)
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QEvent, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QMovie, QFont, QDragEnterEvent, QDropEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QTextEdit, QCheckBox, QFrame, QStackedWidget,
    QFileDialog, QMessageBox, QSizePolicy, QAbstractItemView, QSlider,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

from board import Slide, SlideAsset, copy_asset_to_assets_dir, _ext_to_type
from media_widget import MediaWidget
import audio_utils

# ---- shared palette (matches play_mode / edit_mode) ----
_BG_DARK  = "#252525"
_BG_MID   = "#2f2f2f"
_BG_WARM  = "#38332e"
_ACCENT   = "#7daf8d"
_ACCENT_H = "#91c4a1"
_ACCENT_D = "#5a8a6a"
_TEXT_PRI  = "#e5ddd5"
_TEXT_MUT  = "#9a9080"
_BORDER   = "#505050"

# Active-cell border for media items in a SlideGrid (constant 2px width so
# toggling the colour never reflows the layout).
_CELL_QSS     = "QFrame#slideCell { border: 2px solid transparent; border-radius: 4px; }"
_CELL_QSS_ACT = f"QFrame#slideCell {{ border: 2px solid {_ACCENT}; border-radius: 4px; }}"

_EMOJI_FAMILIES = ["Segoe UI", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"]

def _font(size: int, bold: bool = False) -> QFont:
    f = QFont("Segoe UI", size)
    f.setFamilies(_EMOJI_FAMILIES)
    f.setBold(bold)
    return f


# ------------------------------------------------------------------ #
#  Plain-text QTextEdit (pastes plain text to preserve emoji)         #
# ------------------------------------------------------------------ #
class _PlainTextEdit(QTextEdit):
    def insertFromMimeData(self, source):
        self.insertPlainText(source.text())


# ------------------------------------------------------------------ #
#  CollageWidget — 1-4 images in auto-arranged layout                 #
# ------------------------------------------------------------------ #
class CollageWidget(QWidget):
    """Displays 1-4 images in a responsive collage layout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmaps: list[QPixmap] = []
        self._labels: list[QLabel] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def load(self, paths: list[str]):
        """Load 1-4 image paths and arrange in collage."""
        self.clear()
        for p in paths[:4]:
            px = QPixmap(p)
            if px.isNull():
                continue
            self._pixmaps.append(px)
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background: transparent;")
            self._labels.append(lbl)

        n = len(self._labels)
        if n == 1:
            self._grid.addWidget(self._labels[0], 0, 0)
        elif n == 2:
            self._grid.addWidget(self._labels[0], 0, 0)
            self._grid.addWidget(self._labels[1], 0, 1)
        elif n == 3:
            self._grid.addWidget(self._labels[0], 0, 0)
            self._grid.addWidget(self._labels[1], 0, 1)
            self._grid.addWidget(self._labels[2], 1, 0, 1, 2,
                                 Qt.AlignmentFlag.AlignCenter)
        elif n == 4:
            self._grid.addWidget(self._labels[0], 0, 0)
            self._grid.addWidget(self._labels[1], 0, 1)
            self._grid.addWidget(self._labels[2], 1, 0)
            self._grid.addWidget(self._labels[3], 1, 1)

        self._fit_all()

    def clear(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pixmaps.clear()
        self._labels.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_all()

    def _fit_all(self):
        n = len(self._labels)
        if n == 0:
            return
        w = self.width()
        h = self.height()
        if n == 1:
            cell_w, cell_h = w, h
        elif n == 2:
            cell_w, cell_h = w // 2 - 2, h
        elif n == 3:
            cell_w, cell_h = w // 2 - 2, h // 2 - 2
        else:  # 4
            cell_w, cell_h = w // 2 - 2, h // 2 - 2

        from PyQt6.QtCore import QSize
        target = QSize(max(cell_w, 1), max(cell_h, 1))
        for px, lbl in zip(self._pixmaps, self._labels):
            scaled = px.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            lbl.setPixmap(scaled)


# ------------------------------------------------------------------ #
#  _MixWorker — background thread for audio mixing                    #
# ------------------------------------------------------------------ #
class _MixWorker(QThread):
    done  = pyqtSignal(str)   # mixed output path
    error = pyqtSignal(str)   # error message

    def __init__(self, paths: list[str], assets_dir: str, volumes: list[float]):
        super().__init__()
        self._paths = paths
        self._assets_dir = assets_dir
        self._volumes = volumes

    def run(self):
        try:
            result = audio_utils.mix_audio_overlay(
                self._paths, self._assets_dir, self._volumes)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ------------------------------------------------------------------ #
#  Collage placement helpers (shared by CollageWidget & SlideGrid)    #
# ------------------------------------------------------------------ #
def grid_positions(n: int) -> list[tuple[int, int, int, int]]:
    """(row, col, rowspan, colspan) for each of n cells (1-4), mirroring
    CollageWidget.load()'s arrangement (incl. the centered 1x2 span for
    the 3rd of 3)."""
    if n <= 1:
        return [(0, 0, 1, 1)]
    if n == 2:
        return [(0, 0, 1, 1), (0, 1, 1, 1)]
    if n == 3:
        return [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 2)]
    return [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)]


def cell_target_size(n: int, w: int, h: int) -> tuple[int, int]:
    """Target (width, height) for each cell given n cells in a w x h area,
    mirroring CollageWidget._fit_all (the 3rd of 3 is sized to a half-cell
    and centered)."""
    if n <= 1:
        return w, h
    if n == 2:
        return w // 2 - 2, h
    return w // 2 - 2, h // 2 - 2


# ------------------------------------------------------------------ #
#  SlideGrid — 1-4 mixed media items, each video/audio self-controlled #
# ------------------------------------------------------------------ #
class _GridCell:
    """Bookkeeping for one cell placed in a SlideGrid."""

    def __init__(self, kind: str):
        self.kind = kind            # "image" | "gif" | "video" | "audio"
        self.asset_index = -1       # index into the slide's assets list
        self.container: QFrame | None = None  # frame that gets the active border
        self.wrapper = None         # optional centering wrapper (3rd of 3)
        self.media = None           # MediaWidget (video/audio) or None
        self.label: QLabel | None = None      # QLabel (image/gif) or None
        self.pixmap: QPixmap | None = None    # raw pixmap (image)
        self.movie: QMovie | None = None      # QMovie (gif)
        self.gif_native: QSize | None = None  # native gif frame size
        # stacked-audio specifics
        self.is_stacked = False
        self.mixing = False
        self.play_requested = False
        self.worker = None
        self.stack: QStackedWidget | None = None
        self.stack_fallback = ""

    @property
    def is_timed(self) -> bool:
        return self.kind in ("video", "audio")


class SlideGrid(QWidget):
    """
    Lays out 1-4 media items (any mix of image / gif / video / audio) in the
    same arrangement as the image collage. Images/gifs are lightweight labels;
    video and audio are MediaWidgets with their own compact transport bar.

    A single app-level key filter routes hotkeys (Space, Left/Right, F, R) to
    the most-recently-focused ("active") timed cell. Nothing auto-plays —
    play() only starts gif animation.
    """

    def __init__(self, parent=None, show_controls: bool = True):
        super().__init__(parent)
        self._show_controls = show_controls
        self._cells: list[_GridCell] = []
        self._active_cell: _GridCell | None = None
        self._multi_timed = False
        self._key_filter_app = None
        self._suspend_hotkeys = False

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ---- build ----
    def load(self, assets: list, assets_dir: str, audio_stack: bool):
        self.clear()
        specs = self._build_cell_specs(assets, audio_stack)[:4]
        n = len(specs)
        positions = grid_positions(n)
        for i, (spec, pos) in enumerate(zip(specs, positions)):
            cell = self._create_cell(spec, assets_dir)
            self._cells.append(cell)
            row, col, rs, cs = pos
            if n == 3 and i == 2:
                self._place_third_of_three(cell, row, col, rs, cs)
            else:
                self._grid.addWidget(cell.container, row, col, rs, cs)
        self._apply_stretch(n)

        timed = [c for c in self._cells if c.is_timed]
        self._multi_timed = len(timed) >= 2
        if timed:
            self._set_active_cell(timed[0])
        self._fit_static()
        self._maybe_install_filter()

    def _place_third_of_three(self, cell: "_GridCell", row, col, rs, cs):
        """The 3rd of 3 items spans the bottom row, centered at half width
        (matching the image-collage look). Every cell type is wrapped with
        stretches so the half-width sizing never depends on a content size
        hint — AlignCenter would size a video to its unreliable hint, and an
        image to its pixmap (which drives a layout feedback loop)."""
        wrapper = QWidget()
        hb = QHBoxLayout(wrapper)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(0)
        hb.addStretch(1)
        hb.addWidget(cell.container, 2)
        hb.addStretch(1)
        cell.wrapper = wrapper
        self._grid.addWidget(wrapper, row, col, rs, cs)

    def _apply_stretch(self, n: int):
        """Give every used row/column equal stretch so cells divide the area
        evenly from the first layout pass — independent of each media widget's
        (late-arriving) size hint."""
        if n <= 1:
            cols, rows = 1, 1
        elif n == 2:
            cols, rows = 2, 1
        else:
            cols, rows = 2, 2
        for c in (0, 1):
            self._grid.setColumnStretch(c, 1 if c < cols else 0)
        for r in (0, 1):
            self._grid.setRowStretch(r, 1 if r < rows else 0)

    def _build_cell_specs(self, assets: list, audio_stack: bool) -> list[dict]:
        """Resolve the ordered asset list into per-cell specs. Audio items
        collapse into one stacked cell (at the first audio's slot) when
        stacking is on and possible."""
        audios = [a for a in assets if a.asset_type == "audio"]
        do_stack = (audio_stack and len(audios) >= 2 and audio_utils.is_available())
        specs: list[dict] = []
        stacked_inserted = False
        for i, a in enumerate(assets):
            if a.asset_type == "audio":
                if do_stack:
                    if not stacked_inserted:
                        specs.append({
                            "kind": "audio", "stacked": True, "asset_index": i,
                            "paths": [x.path for x in audios],
                            "volumes": [x.volume for x in audios],
                        })
                        stacked_inserted = True
                    continue  # other audios fold into the stacked cell
                specs.append({"kind": "audio", "stacked": False,
                              "asset_index": i, "path": a.path})
            elif a.asset_type in ("image", "gif", "video"):
                spec = {"kind": a.asset_type, "asset_index": i, "path": a.path}
                if a.asset_type == "video":
                    spec["volume"] = a.volume
                specs.append(spec)
            # unknown/empty asset types are skipped
        return specs

    def _create_cell(self, spec: dict, assets_dir: str) -> _GridCell:
        kind = spec["kind"]
        if kind in ("image", "gif"):
            cell = self._create_image_cell(kind, os.path.join(assets_dir, spec["path"]))
        elif kind == "video":
            cell = self._create_media_cell(
                "video", os.path.join(assets_dir, spec["path"]),
                volume=spec.get("volume"))
        elif spec.get("stacked"):
            cell = self._create_stacked_audio_cell(spec, assets_dir)
        else:
            cell = self._create_media_cell("audio", os.path.join(assets_dir, spec["path"]))
        cell.asset_index = spec.get("asset_index", -1)
        return cell

    def _new_container(self) -> tuple[QFrame, QVBoxLayout]:
        container = QFrame()
        container.setObjectName("slideCell")
        container.setStyleSheet(_CELL_QSS)
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        return container, lay

    def _create_image_cell(self, kind: str, full_path: str) -> _GridCell:
        cell = _GridCell(kind)
        container, lay = self._new_container()
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background: transparent; border: none;")
        # Fill the cell but never let the pixmap drive the layout: a pixmap
        # QLabel's minimumSizeHint tracks the pixmap, which would ratchet the
        # window larger each layout pass (infinite zoom). Ignored policy makes
        # the layout use minimumSize (1px) instead of that hint.
        label.setMinimumSize(1, 1)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        lay.addWidget(label)
        cell.container = container
        cell.label = label
        if kind == "gif":
            movie = QMovie(full_path)
            if movie.isValid():
                cell.movie = movie
                movie.jumpToFrame(0)
                img = movie.currentImage()
                cell.gif_native = img.size() if not img.isNull() else None
                label.setMovie(movie)
                movie.start()
                return cell
            cell.kind = "image"  # fall back to a static first frame
        px = QPixmap(full_path)
        cell.pixmap = px if not px.isNull() else None
        return cell

    def _wire_media(self, media, cell: _GridCell):
        media.activated.connect(lambda c=cell: self._set_active_cell(c))
        media.fullscreen_opened.connect(self._on_fs_opened)
        media.fullscreen_closed.connect(self._on_fs_closed)

    def _create_media_cell(self, kind: str, full_path: str,
                           volume: float | None = None) -> _GridCell:
        cell = _GridCell(kind)
        container, lay = self._new_container()
        media = MediaWidget(auto_play=False, show_controls=self._show_controls,
                            manage_hotkeys=False, compact_controls=True)
        media.load(full_path, kind)
        if volume is not None:
            media.set_volume(int(volume * 100))
        self._wire_media(media, cell)
        lay.addWidget(media)
        cell.container = container
        cell.media = media
        return cell

    def _create_stacked_audio_cell(self, spec: dict, assets_dir: str) -> _GridCell:
        cell = _GridCell("audio")
        cell.is_stacked = True
        container, lay = self._new_container()

        stack = QStackedWidget()
        mixing = QLabel("🎵  Mixing audio clips…")
        mixing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mixing.setFont(_font(14))
        mixing.setStyleSheet(f"color: {_TEXT_MUT}; background: transparent; border: none;")
        stack.addWidget(mixing)            # index 0

        media = MediaWidget(auto_play=False, show_controls=self._show_controls,
                            manage_hotkeys=False, compact_controls=True)
        self._wire_media(media, cell)
        stack.addWidget(media)             # index 1
        stack.setCurrentIndex(0)
        lay.addWidget(stack)

        cell.container = container
        cell.media = media
        cell.stack = stack
        cell.mixing = True

        paths = [os.path.join(assets_dir, p) for p in spec["paths"]]
        cell.stack_fallback = paths[0]
        worker = _MixWorker(paths, assets_dir, spec["volumes"])
        worker.done.connect(lambda out, c=cell: self._on_stack_done(c, out))
        worker.error.connect(lambda msg, c=cell: self._on_stack_error(c, msg))
        cell.worker = worker
        worker.start()
        return cell

    def _on_stack_done(self, cell: _GridCell, out_path: str):
        cell.mixing = False
        cell.worker = None
        cell.media.load(out_path, "audio")
        if cell.stack is not None:
            cell.stack.setCurrentIndex(1)
        if cell.play_requested:
            cell.play_requested = False
            cell.media.play()

    def _on_stack_error(self, cell: _GridCell, msg: str):
        print(f"[SlideGrid] Audio mix failed, falling back: {msg}")
        cell.mixing = False
        cell.worker = None
        cell.media.load(cell.stack_fallback, "audio")
        if cell.stack is not None:
            cell.stack.setCurrentIndex(1)
        if cell.play_requested:
            cell.play_requested = False
            cell.media.play()

    # ---- active cell & hotkeys ----
    def _set_active_cell(self, cell: _GridCell | None):
        if cell is self._active_cell:
            return
        if (self._active_cell is not None
                and self._active_cell.container is not None):
            try:
                self._active_cell.container.setStyleSheet(_CELL_QSS)
            except RuntimeError:
                pass
        self._active_cell = cell
        # The accent border only matters for hotkey focus (play mode). Skip it
        # in non-interactive contexts like the editor preview.
        if (cell is not None and cell.container is not None
                and self._multi_timed and self._show_controls):
            cell.container.setStyleSheet(_CELL_QSS_ACT)

    def _toggle_active(self):
        c = self._active_cell
        if c is None:
            return
        if c.is_stacked and c.mixing:
            c.play_requested = not c.play_requested  # queue until mix done
            return
        if c.media is not None:
            c.media.toggle_play_pause()

    def _on_fs_opened(self):
        self._suspend_hotkeys = True

    def _on_fs_closed(self):
        self._suspend_hotkeys = False

    def _maybe_install_filter(self):
        if (not self._show_controls
                or self._key_filter_app is not None
                or not self.isVisible()):
            return
        if not any(c.is_timed for c in self._cells):
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._key_filter_app = app

    def _remove_filter(self):
        if self._key_filter_app is not None:
            try:
                self._key_filter_app.removeEventFilter(self)
            except RuntimeError:
                pass
            self._key_filter_app = None

    def showEvent(self, event):
        super().showEvent(event)
        self._maybe_install_filter()
        self._fit_static()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._remove_filter()

    def eventFilter(self, obj, event):
        if (not self._suspend_hotkeys
                and event.type() == QEvent.Type.KeyPress
                and self._active_cell is not None
                and self._active_cell.is_timed):
            key = event.key()
            c = self._active_cell
            if key == Qt.Key.Key_Left:
                if c.media is not None:
                    c.media.seek_relative(-1000)
                return True
            if key == Qt.Key.Key_Right:
                if c.media is not None:
                    c.media.seek_relative(1000)
                return True
            if key == Qt.Key.Key_Space:
                self._toggle_active()
                return True
            if key == Qt.Key.Key_R:
                if c.media is not None:
                    c.media.restart()
                return True
            if key == Qt.Key.Key_F:
                if c.media is not None and c.media.is_video:
                    c.media.toggle_fullscreen()
                    return True
        return super().eventFilter(obj, event)

    def media_for_asset_index(self, idx: int):
        """The MediaWidget for the cell built from assets[idx], or None."""
        for c in self._cells:
            if c.asset_index == idx and c.media is not None:
                return c.media
        return None

    # ---- playback ----
    def play(self):
        # Nothing auto-plays: only gif animation is (re)started here.
        for c in self._cells:
            if c.movie is not None:
                c.movie.start()

    def stop(self):
        for c in self._cells:
            if c.movie is not None:
                c.movie.stop()
            if c.media is not None:
                c.media.stop()
            if c.worker is not None:
                try:
                    c.worker.done.disconnect()
                    c.worker.error.disconnect()
                except (RuntimeError, TypeError):
                    pass
                c.worker.quit()
                c.worker.wait()
                c.worker = None
                c.mixing = False

    def clear(self):
        self.stop()
        self._remove_filter()
        for c in self._cells:
            if c.media is not None:
                c.media.force_close_fullscreen()
        self._cells = []
        self._active_cell = None
        self._multi_timed = False
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    # ---- sizing ----
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_static()

    def _fit_static(self):
        n = len(self._cells)
        if n == 0:
            return
        tw, th = cell_target_size(n, self.width(), self.height())
        target = QSize(max(tw, 1), max(th, 1))
        for c in self._cells:
            if c.pixmap is not None and c.label is not None:
                c.label.setPixmap(c.pixmap.scaled(
                    target, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            elif c.movie is not None:
                if c.gif_native is not None and c.gif_native.width() > 0:
                    c.movie.setScaledSize(c.gif_native.scaled(
                        target, Qt.AspectRatioMode.KeepAspectRatio))
                else:
                    c.movie.setScaledSize(target)


# ------------------------------------------------------------------ #
#  SlideRenderer — play-mode display for a Slide                      #
# ------------------------------------------------------------------ #
class SlideRenderer(QWidget):
    """
    Renders a Slide for gameplay: a 1-4 item SlideGrid (any mix of
    image / gif / video / audio) plus an optional text label.
    """

    def __init__(self, auto_play: bool = True, show_controls: bool = True,
                 parent=None):
        super().__init__(parent)
        self._auto_play = auto_play
        self._show_controls = show_controls

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # Media grid (any mix of images / gifs / videos / audio)
        self._grid = SlideGrid(show_controls=show_controls)
        self._grid.setVisible(False)
        root.addWidget(self._grid, stretch=1)

        # Text label
        self._text_label = QLabel()
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_label.setWordWrap(True)
        self._text_label.setFont(_font(20))
        self._text_label.setStyleSheet(f"color: {_TEXT_PRI}; padding: 12px;")
        self._text_label.setVisible(False)
        root.addWidget(self._text_label)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def load_slide(self, slide: Slide, assets_dir: str):
        """Display the slide content."""
        self.stop()
        self._grid.load(slide.assets, assets_dir, slide.audio_stack)
        self._grid.setVisible(bool(slide.assets))

        # Text
        if slide.text.strip():
            self._text_label.setText(slide.text)
            self._text_label.setVisible(True)
        else:
            self._text_label.setVisible(False)

    def play(self):
        self._grid.play()

    def stop(self):
        self._grid.stop()

    def media_for_asset_index(self, idx: int):
        return self._grid.media_for_asset_index(idx)

    def clear(self):
        self._grid.clear()
        self._grid.setVisible(False)
        self._text_label.setVisible(False)


# ------------------------------------------------------------------ #
#  SlideEditor — edit-mode editor for a Slide                         #
# ------------------------------------------------------------------ #
class SlideEditor(QWidget):
    """
    Edits a single Slide: text input, asset list management, preview.
    Used as a tab in CellEditorDialog.
    """

    def __init__(self, slide: Slide, assets_dir: str, parent=None):
        super().__init__(parent)
        self._slide = slide
        self._assets_dir = assets_dir
        self._pending_assets: list[SlideAsset] = list(slide.assets)
        self._build_ui()
        self._populate()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Text input
        text_label = QLabel("Text:")
        text_label.setStyleSheet(f"color: {_ACCENT_H}; font-weight: bold;")
        layout.addWidget(text_label)

        self._text_edit = _PlainTextEdit()
        self._text_edit.setPlaceholderText("Enter text for this slide…")
        self._text_edit.setFont(_font(13))
        self._text_edit.setStyleSheet(
            f"background:{_BG_MID}; color:{_TEXT_PRI};"
            f" border:1px solid {_BORDER}; border-radius:5px;"
        )
        self._text_edit.setMaximumHeight(100)
        layout.addWidget(self._text_edit)

        # Asset table
        asset_label = QLabel("Assets:")
        asset_label.setStyleSheet(f"color: {_ACCENT_H}; font-weight: bold;")
        layout.addWidget(asset_label)

        self._asset_table = QTableWidget(0, 3)
        self._asset_table.setHorizontalHeaderLabels(["Asset", "Volume", ""])
        self._asset_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._asset_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Fixed)
        self._asset_table.horizontalHeader().resizeSection(1, 140)
        self._asset_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Fixed)
        self._asset_table.horizontalHeader().resizeSection(2, 36)
        self._asset_table.verticalHeader().setVisible(False)
        self._asset_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._asset_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._asset_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._asset_table.setMaximumHeight(120)
        self._asset_table.setStyleSheet(
            f"QTableWidget {{ background:{_BG_MID}; color:{_TEXT_PRI};"
            f" border:1px solid {_BORDER}; border-radius:5px;"
            f" gridline-color:{_BORDER}; }}"
            f"QHeaderView::section {{ background:{_BG_DARK}; color:{_TEXT_MUT};"
            f" border:1px solid {_BORDER}; padding:3px; font-size:11px; }}"
            f"QTableWidget::item {{ padding:4px; }}"
            f"QTableWidget::item:selected {{ background:{_ACCENT_D}; }}"
        )
        layout.addWidget(self._asset_table)

        # Shared preview player for individual audio tracks
        self._preview_player = None
        self._preview_audio_out = None
        self._preview_playing_idx = -1
        # Video preview is driven through the preview pane's MediaWidget
        self._video_preview_idx = -1

        # Asset buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._add_btn = QPushButton("Add Asset…")
        self._add_btn.setStyleSheet(
            f"QPushButton {{ background:{_ACCENT_D}; color:{_TEXT_PRI}; border-radius:5px;"
            f" padding:5px 12px; border:1px solid {_ACCENT}; }}"
            f"QPushButton:hover {{ background:{_ACCENT}; color:#111; }}"
        )
        self._add_btn.clicked.connect(self._on_add_asset)
        btn_row.addWidget(self._add_btn)

        self._remove_btn = QPushButton("Remove Selected")
        self._remove_btn.setStyleSheet(
            f"QPushButton {{ background:#3a2828; color:{_TEXT_PRI}; border-radius:5px;"
            f" padding:5px 12px; border:1px solid #5a3838; }}"
            f"QPushButton:hover {{ background:#503535; }}"
        )
        self._remove_btn.clicked.connect(self._on_remove_asset)
        btn_row.addWidget(self._remove_btn)

        # Reorder buttons — list order drives the on-screen grid position
        _reorder_qss = (
            f"QPushButton {{ background:{_BG_MID}; color:{_TEXT_PRI}; border-radius:5px;"
            f" padding:5px 10px; border:1px solid {_BORDER}; }}"
            f"QPushButton:hover {{ background:#3a3a3a; color:{_ACCENT_H}; }}"
        )
        self._up_btn = QPushButton("▲")
        self._up_btn.setToolTip("Move selected item earlier (up / left)")
        self._up_btn.setFixedWidth(36)
        self._up_btn.setStyleSheet(_reorder_qss)
        self._up_btn.clicked.connect(lambda: self._move_asset(-1))
        btn_row.addWidget(self._up_btn)

        self._down_btn = QPushButton("▼")
        self._down_btn.setToolTip("Move selected item later (down / right)")
        self._down_btn.setFixedWidth(36)
        self._down_btn.setStyleSheet(_reorder_qss)
        self._down_btn.clicked.connect(lambda: self._move_asset(1))
        btn_row.addWidget(self._down_btn)

        btn_row.addStretch()

        # Audio stacking checkbox
        self._stack_check = QCheckBox("Stack audio clips")
        self._stack_check.setStyleSheet(f"color: {_TEXT_MUT};")
        self._stack_check.setToolTip(
            "Overlay multiple audio clips into a single mixed track"
        )
        self._stack_check.setVisible(False)
        self._stack_check.toggled.connect(self._refresh_preview)
        btn_row.addWidget(self._stack_check)

        layout.addLayout(btn_row)

        # Hint
        hint = QLabel("Tip: drag & drop or paste (Ctrl+V) media files.")
        hint.setStyleSheet(f"color: {_TEXT_MUT}; font-size: 11px;")
        layout.addWidget(hint)

        # Preview
        self._preview = SlideRenderer(auto_play=False, show_controls=False)
        self._preview.setMinimumHeight(140)
        self._preview.setStyleSheet(f"background:{_BG_DARK}; border-radius:5px;")
        layout.addWidget(self._preview, stretch=1)

    def _populate(self):
        self._text_edit.setPlainText(self._slide.text)
        self._stack_check.setChecked(self._slide.audio_stack)
        self._refresh_asset_list()
        self._refresh_preview()

    def _refresh_asset_list(self):
        self._stop_audio_preview()
        self._video_preview_idx = -1
        self._asset_table.setRowCount(0)
        has_timed = False
        for idx, a in enumerate(self._pending_assets):
            row = self._asset_table.rowCount()
            self._asset_table.insertRow(row)
            self._asset_table.setRowHeight(row, 32)
            tag = a.asset_type.upper() if a.asset_type else "?"
            # Column 0: name
            self._asset_table.setItem(row, 0,
                                      QTableWidgetItem(f"[{tag}] {a.path}"))

            if a.asset_type in ("audio", "video"):
                has_timed = True
                is_video = (a.asset_type == "video")
                # Column 1: volume slider + percentage
                vol_widget = QWidget()
                vol_layout = QHBoxLayout(vol_widget)
                vol_layout.setContentsMargins(4, 0, 4, 0)
                vol_layout.setSpacing(4)

                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(0, 100)
                slider.setValue(int(a.volume * 100))
                slider.setStyleSheet(
                    f"QSlider::groove:horizontal {{ background:{_BG_DARK};"
                    f" height:6px; border-radius:3px; }}"
                    f"QSlider::handle:horizontal {{ background:{_ACCENT};"
                    f" width:12px; margin:-3px 0; border-radius:6px; }}"
                    f"QSlider::sub-page:horizontal {{ background:{_ACCENT_D};"
                    f" border-radius:3px; }}"
                )
                slider.setToolTip(f"Volume: {int(a.volume * 100)}%")

                pct_label = QLabel(f"{int(a.volume * 100)}%")
                pct_label.setFixedWidth(32)
                pct_label.setStyleSheet(f"color:{_TEXT_MUT}; font-size:11px;")
                pct_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                       | Qt.AlignmentFlag.AlignVCenter)

                def _make_vol_handler(i, sl, pl, vid):
                    def handler(val):
                        self._pending_assets[i].volume = val / 100.0
                        sl.setToolTip(f"Volume: {val}%")
                        pl.setText(f"{val}%")
                        # Update live playback volume
                        if vid:
                            mw = self._preview.media_for_asset_index(i)
                            if mw is not None:
                                mw.set_volume(val)
                        elif (self._preview_playing_idx == i
                                and self._preview_audio_out is not None):
                            self._preview_audio_out.setVolume(val / 100.0)
                    return handler

                slider.valueChanged.connect(
                    _make_vol_handler(idx, slider, pct_label, is_video))
                vol_layout.addWidget(slider, stretch=1)
                vol_layout.addWidget(pct_label)
                self._asset_table.setCellWidget(row, 1, vol_widget)

                # Column 2: play/pause button
                play_btn = QPushButton("\u25b6")  # ▶
                play_btn.setFixedSize(24, 24)
                play_btn.setToolTip("Preview this video" if is_video
                                    else "Preview this track")
                play_btn.setStyleSheet(
                    f"QPushButton {{ background:{_BG_DARK}; color:{_ACCENT};"
                    f" border:1px solid {_BORDER}; border-radius:4px;"
                    f" font-size:13px; }}"
                    f"QPushButton:hover {{ background:{_ACCENT_D};"
                    f" color:{_TEXT_PRI}; }}"
                )

                def _make_play_handler(i, btn, vid):
                    def handler():
                        if vid:
                            self._toggle_video_preview(i)
                        else:
                            self._toggle_audio_preview(i, btn)
                    return handler

                play_btn.clicked.connect(_make_play_handler(idx, play_btn, is_video))
                # Center the button in the cell
                btn_container = QWidget()
                btn_lay = QHBoxLayout(btn_container)
                btn_lay.setContentsMargins(0, 0, 0, 0)
                btn_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                btn_lay.addWidget(play_btn)
                self._asset_table.setCellWidget(row, 2, btn_container)

        # Hide volume/play columns when no audio/video assets
        self._asset_table.setColumnHidden(1, not has_timed)
        self._asset_table.setColumnHidden(2, not has_timed)

        # Show audio stack checkbox only when 2+ audio assets
        n_audio = sum(1 for a in self._pending_assets if a.asset_type == "audio")
        self._stack_check.setVisible(n_audio >= 2)
        if n_audio < 2:
            self._stack_check.setChecked(False)

    # ---- Audio preview playback ----
    def _ensure_preview_player(self):
        if self._preview_player is None:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._preview_audio_out = QAudioOutput()
            self._preview_player = QMediaPlayer()
            self._preview_player.setAudioOutput(self._preview_audio_out)
            self._preview_player.playbackStateChanged.connect(
                self._on_preview_state_changed)

    def _toggle_audio_preview(self, idx: int, btn: QPushButton):
        from PyQt6.QtMultimedia import QMediaPlayer
        self._ensure_preview_player()

        # If already playing this track, stop it
        if (self._preview_playing_idx == idx
                and self._preview_player.playbackState()
                == QMediaPlayer.PlaybackState.PlayingState):
            self._preview_player.stop()
            return

        # Stop any current preview (audio or video — one at a time)
        self._stop_audio_preview()
        self._stop_video_preview()

        asset = self._pending_assets[idx]
        full_path = os.path.join(self._assets_dir, asset.path)
        if not os.path.isfile(full_path):
            return

        from PyQt6.QtCore import QUrl
        self._preview_audio_out.setVolume(asset.volume)
        self._preview_player.setSource(QUrl.fromLocalFile(full_path))
        self._preview_player.play()
        self._preview_playing_idx = idx
        btn.setText("\u23f8")  # ⏸
        btn.setToolTip("Stop preview")

    def _stop_audio_preview(self):
        if self._preview_player is not None:
            self._preview_player.stop()
        self._reset_all_play_buttons()
        self._preview_playing_idx = -1

    def _on_preview_state_changed(self, state):
        from PyQt6.QtMultimedia import QMediaPlayer
        if state != QMediaPlayer.PlaybackState.PlayingState:
            self._reset_all_play_buttons()
            self._preview_playing_idx = -1

    def _reset_all_play_buttons(self):
        """Reset all play buttons back to ▶."""
        for row in range(self._asset_table.rowCount()):
            w = self._asset_table.cellWidget(row, 2)
            if w:
                btn = w.findChild(QPushButton)
                if btn:
                    btn.setText("\u25b6")
                    btn.setToolTip("Preview this track")

    # ---- Video preview playback (driven via the preview pane) ----
    def _toggle_video_preview(self, idx: int):
        self._stop_audio_preview()
        mw = self._preview.media_for_asset_index(idx)
        if mw is None:
            return
        if mw.is_playing():
            mw.toggle_play_pause()       # pause -> playing_changed resets icon
            return
        # Stop any other previewing video first
        if self._video_preview_idx not in (-1, idx):
            other = self._preview.media_for_asset_index(self._video_preview_idx)
            if other is not None:
                other.stop()
        self._video_preview_idx = idx
        mw.toggle_play_pause()           # play -> playing_changed sets icon

    def _stop_video_preview(self):
        if self._video_preview_idx != -1:
            mw = self._preview.media_for_asset_index(self._video_preview_idx)
            if mw is not None:
                mw.stop()
            self._video_preview_idx = -1

    def _on_video_preview_state(self, idx: int, playing: bool):
        self._set_play_button_icon(idx, playing)
        if not playing and self._video_preview_idx == idx:
            self._video_preview_idx = -1

    def _set_play_button_icon(self, idx: int, playing: bool):
        w = self._asset_table.cellWidget(idx, 2)
        if w:
            btn = w.findChild(QPushButton)
            if btn:
                btn.setText("⏸" if playing else "▶")
                btn.setToolTip("Pause preview" if playing else "Preview this video")

    def _wire_video_previews(self):
        """Connect each preview-pane video to its asset-table play button."""
        for i, a in enumerate(self._pending_assets):
            if a.asset_type == "video":
                mw = self._preview.media_for_asset_index(i)
                if mw is not None:
                    mw.playing_changed.connect(
                        lambda playing, idx=i: self._on_video_preview_state(idx, playing))

    def _refresh_preview(self):
        preview_slide = Slide(
            text=self._text_edit.toPlainText().strip(),
            assets=list(self._pending_assets),
            audio_stack=self._stack_check.isChecked(),
        )
        self._preview.load_slide(preview_slide, self._assets_dir)
        self._wire_video_previews()

    # ---- Asset management ----
    def _on_add_asset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Media Asset", "",
            "Media Files (*.png *.jpg *.jpeg *.gif *.bmp *.webp"
            " *.mp4 *.webm *.mov *.mp3 *.wav *.ogg)"
        )
        if path:
            self._try_add_asset(path)

    def _cell_count(self, assets: list) -> int:
        """Number of grid cells the assets occupy (a stacked-audio group of
        2+ clips counts as a single cell)."""
        n_fixed = sum(1 for a in assets
                      if a.asset_type in ("image", "gif", "video"))
        n_audio = sum(1 for a in assets if a.asset_type == "audio")
        if self._stack_check.isChecked() and n_audio >= 2:
            audio_cells = 1
        else:
            audio_cells = n_audio
        return n_fixed + audio_cells

    def _try_add_asset(self, src_path: str):
        ext = os.path.splitext(src_path)[1].lower()
        atype = _ext_to_type(ext)
        if not atype:
            QMessageBox.warning(self, "Unsupported", "File type not supported.")
            return

        # Auto-enable stacking on the 2nd+ audio so the audio group stays a
        # single grid cell (matches the renderer's collapsing behaviour).
        if atype == "audio":
            n_audio = sum(1 for a in self._pending_assets
                          if a.asset_type == "audio")
            if n_audio >= 1 and not self._stack_check.isChecked():
                self._stack_check.setChecked(True)

        # Enforce the max-4-cells limit (any mix of media).
        projected = self._pending_assets + [SlideAsset(path="", asset_type=atype)]
        if self._cell_count(projected) > 4:
            QMessageBox.warning(
                self, "Limit",
                "Maximum 4 items per slide.\n"
                "(A stacked-audio group counts as one item.)"
            )
            return

        # Copy to assets dir
        rel, confirmed_type = copy_asset_to_assets_dir(src_path, self._assets_dir)
        # Videos default to full volume; audio keeps the quieter mixing default.
        default_vol = 1.0 if confirmed_type == "video" else 0.3
        self._pending_assets.append(
            SlideAsset(path=rel, asset_type=confirmed_type, volume=default_vol))
        self._refresh_asset_list()
        self._refresh_preview()

    def _on_remove_asset(self):
        row = self._asset_table.currentRow()
        if 0 <= row < len(self._pending_assets):
            self._pending_assets.pop(row)
            self._refresh_asset_list()
            self._refresh_preview()

    def _move_asset(self, delta: int):
        """Swap the selected asset with its neighbour (reordering changes the
        on-screen grid position)."""
        row = self._asset_table.currentRow()
        j = row + delta
        if (0 <= row < len(self._pending_assets)
                and 0 <= j < len(self._pending_assets)):
            self._stop_audio_preview()  # row indices are about to shift
            self._pending_assets[row], self._pending_assets[j] = (
                self._pending_assets[j], self._pending_assets[row])
            self._refresh_asset_list()
            self._asset_table.selectRow(j)
            self._refresh_preview()

    # ---- Drag-and-drop ----
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                self._try_add_asset(path)

    # ---- Clipboard paste (image data or file URLs) ----
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            if self._handle_paste():
                return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.KeyPress
                and event.matches(QKeySequence.StandardKey.Paste)):
            if self._handle_paste():
                return True
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._text_edit.installEventFilter(self)

    def _handle_paste(self) -> bool:
        """Try to paste media from clipboard. Returns True if handled."""
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                if os.path.isfile(path):
                    ext = os.path.splitext(path)[1].lower()
                    if _ext_to_type(ext):
                        self._try_add_asset(path)
                        return True
        if mime.hasImage():
            img = clipboard.image()
            if not img.isNull():
                os.makedirs(self._assets_dir, exist_ok=True)
                i = 1
                while True:
                    dest = os.path.join(self._assets_dir, f"pasted_image_{i}.png")
                    if not os.path.exists(dest):
                        break
                    i += 1
                img.save(dest, "PNG")
                self._try_add_asset(dest)
                return True
        return False  # let text paste through

    # ---- Public API ----
    def get_slide(self) -> Slide:
        """Return a Slide reflecting the current editor state."""
        return Slide(
            text=self._text_edit.toPlainText().strip(),
            assets=list(self._pending_assets),
            audio_stack=self._stack_check.isChecked(),
        )

    def stop_preview(self):
        self._preview.stop()
        self._stop_audio_preview()
