"""
slide_widgets.py — Reusable widgets for slide editing and rendering.

CollageWidget   — displays 1-4 images in auto-arranged layouts
SlideRenderer   — plays back a Slide (collage / video / audio + text)
SlideEditor     — edits a Slide (text + asset list + preview)
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QEvent, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont, QDragEnterEvent, QDropEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QTextEdit, QCheckBox,
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
#  SlideRenderer — play-mode display for a Slide                      #
# ------------------------------------------------------------------ #
class SlideRenderer(QWidget):
    """
    Renders a Slide for gameplay: collage for images, MediaWidget for
    video/audio, optional text label at the bottom.
    """

    def __init__(self, auto_play: bool = True, show_controls: bool = True,
                 parent=None):
        super().__init__(parent)
        self._auto_play = auto_play
        self._show_controls = show_controls
        self._active_mode = ""  # "image", "video", "audio", ""
        self._mix_worker = None
        self._pending_audio_image = False  # whether to show collage after mix
        self._pending_img_paths: list[str] = []
        self._pending_fallback: str = ""
        self._play_requested = False  # play() called while mix was in progress

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # Collage (for images)
        self._collage = CollageWidget()
        self._collage.setVisible(False)
        root.addWidget(self._collage, stretch=1)

        # MediaWidget (for video / audio)
        self._media = MediaWidget(auto_play=False, show_controls=show_controls)
        self._media.setVisible(False)
        root.addWidget(self._media, stretch=1)

        # Mixing overlay label (shown while background mix is running)
        self._mixing_label = QLabel("🎵  Mixing audio clips…")
        self._mixing_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mixing_label.setFont(_font(16))
        self._mixing_label.setStyleSheet(
            f"color: {_TEXT_MUT}; background: transparent; padding: 20px;"
        )
        self._mixing_label.setVisible(False)
        root.addWidget(self._mixing_label, stretch=1)

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
        self._collage.clear()
        self._collage.setVisible(False)
        self._media.clear()
        self._media.setVisible(False)
        self._active_mode = ""

        media_type = slide.dominant_media_type()

        if media_type == "image":
            paths = [os.path.join(assets_dir, a.path) for a in slide.image_assets()]
            if paths:
                self._collage.load(paths)
                self._collage.setVisible(True)
                self._active_mode = "image"

        elif media_type == "video":
            va = slide.video_asset()
            if va:
                full = os.path.join(assets_dir, va.path)
                self._media.load(full, "video")
                self._media.setVisible(True)
                self._active_mode = "video"

        elif media_type in ("audio", "audio_image"):
            audio_list = slide.audio_assets()
            if audio_list:
                if slide.audio_stack and len(audio_list) > 1 and audio_utils.is_available():
                    audio_paths = [os.path.join(assets_dir, a.path) for a in audio_list]
                    volumes = [a.volume for a in audio_list]
                    self._pending_fallback = audio_paths[0]
                    self._pending_audio_image = (media_type == "audio_image")
                    self._pending_img_paths = (
                        [os.path.join(assets_dir, a.path) for a in slide.image_assets()]
                        if self._pending_audio_image else []
                    )
                    self._mixing_label.setVisible(True)
                    self._mix_worker = _MixWorker(audio_paths, assets_dir, volumes)
                    self._mix_worker.done.connect(self._on_mix_done)
                    self._mix_worker.error.connect(self._on_mix_error)
                    self._mix_worker.start()
                    self._active_mode = "audio"
                else:
                    full = os.path.join(assets_dir, audio_list[0].path)
                    self._media.load(full, "audio")
                    self._media.setVisible(True)
                    if media_type == "audio_image":
                        img_paths = [os.path.join(assets_dir, a.path)
                                     for a in slide.image_assets()]
                        self._collage.load(img_paths)
                        self._collage.setVisible(True)
                        self._media.set_controls_only(True)
                    self._active_mode = "audio"

        # Text
        if slide.text.strip():
            self._text_label.setText(slide.text)
            self._text_label.setVisible(True)
        else:
            self._text_label.setVisible(False)

    def _on_mix_done(self, path: str):
        self._mixing_label.setVisible(False)
        self._media.load(path, "audio")
        self._media.setVisible(True)
        if self._pending_audio_image and self._pending_img_paths:
            self._collage.load(self._pending_img_paths)
            self._collage.setVisible(True)
            self._media.set_controls_only(True)
        if self._auto_play or self._play_requested:
            self._media.play()
        self._play_requested = False

    def _on_mix_error(self, msg: str):
        print(f"[SlideRenderer] Audio mix failed, falling back: {msg}")
        self._mixing_label.setVisible(False)
        self._media.load(self._pending_fallback, "audio")
        self._media.setVisible(True)
        if self._auto_play or self._play_requested:
            self._media.play()
        self._play_requested = False

    def play(self):
        if self._mixing_label.isVisible():
            self._play_requested = True
            return
        if self._active_mode in ("video", "audio"):
            self._media.play()

    def stop(self):
        if self._mix_worker and self._mix_worker.isRunning():
            self._mix_worker.done.disconnect()
            self._mix_worker.error.disconnect()
            self._mix_worker.quit()
            self._mix_worker.wait()
            self._mix_worker = None
        self._mixing_label.setVisible(False)
        self._play_requested = False
        self._media.stop()

    def clear(self):
        self.stop()
        self._collage.clear()
        self._collage.setVisible(False)
        self._media.clear()
        self._media.setVisible(False)
        self._text_label.setVisible(False)
        self._active_mode = ""


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

        btn_row.addStretch()

        # Audio stacking checkbox
        self._stack_check = QCheckBox("Stack audio clips")
        self._stack_check.setStyleSheet(f"color: {_TEXT_MUT};")
        self._stack_check.setToolTip(
            "Overlay multiple audio clips into a single mixed track"
        )
        self._stack_check.setVisible(False)
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
        self._asset_table.setRowCount(0)
        has_any_audio = False
        for idx, a in enumerate(self._pending_assets):
            row = self._asset_table.rowCount()
            self._asset_table.insertRow(row)
            self._asset_table.setRowHeight(row, 32)
            tag = a.asset_type.upper() if a.asset_type else "?"
            # Column 0: name
            self._asset_table.setItem(row, 0,
                                      QTableWidgetItem(f"[{tag}] {a.path}"))

            if a.asset_type == "audio":
                has_any_audio = True
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

                def _make_vol_handler(i, sl, pl):
                    def handler(val):
                        self._pending_assets[i].volume = val / 100.0
                        sl.setToolTip(f"Volume: {val}%")
                        pl.setText(f"{val}%")
                        # Update live playback volume if this track is playing
                        if (self._preview_playing_idx == i
                                and self._preview_audio_out is not None):
                            self._preview_audio_out.setVolume(val / 100.0)
                    return handler

                slider.valueChanged.connect(
                    _make_vol_handler(idx, slider, pct_label))
                vol_layout.addWidget(slider, stretch=1)
                vol_layout.addWidget(pct_label)
                self._asset_table.setCellWidget(row, 1, vol_widget)

                # Column 2: play/pause button
                play_btn = QPushButton("\u25b6")  # ▶
                play_btn.setFixedSize(24, 24)
                play_btn.setToolTip("Preview this track")
                play_btn.setStyleSheet(
                    f"QPushButton {{ background:{_BG_DARK}; color:{_ACCENT};"
                    f" border:1px solid {_BORDER}; border-radius:4px;"
                    f" font-size:13px; }}"
                    f"QPushButton:hover {{ background:{_ACCENT_D};"
                    f" color:{_TEXT_PRI}; }}"
                )

                def _make_play_handler(i, btn):
                    def handler():
                        self._toggle_audio_preview(i, btn)
                    return handler

                play_btn.clicked.connect(_make_play_handler(idx, play_btn))
                # Center the button in the cell
                btn_container = QWidget()
                btn_lay = QHBoxLayout(btn_container)
                btn_lay.setContentsMargins(0, 0, 0, 0)
                btn_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                btn_lay.addWidget(play_btn)
                self._asset_table.setCellWidget(row, 2, btn_container)

        # Hide volume/play columns when no audio assets
        self._asset_table.setColumnHidden(1, not has_any_audio)
        self._asset_table.setColumnHidden(2, not has_any_audio)

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

        # Stop any current preview
        self._stop_audio_preview()

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

    def _refresh_preview(self):
        preview_slide = Slide(
            text=self._text_edit.toPlainText().strip(),
            assets=list(self._pending_assets),
            audio_stack=self._stack_check.isChecked(),
        )
        self._preview.load_slide(preview_slide, self._assets_dir)

    # ---- Asset management ----
    def _on_add_asset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Media Asset", "",
            "Media Files (*.png *.jpg *.jpeg *.gif *.bmp *.webp"
            " *.mp4 *.webm *.mov *.mp3 *.wav *.ogg)"
        )
        if path:
            self._try_add_asset(path)

    def _try_add_asset(self, src_path: str):
        ext = os.path.splitext(src_path)[1].lower()
        atype = _ext_to_type(ext)
        if not atype:
            QMessageBox.warning(self, "Unsupported", "File type not supported.")
            return

        # Validation rules
        has_video = any(a.asset_type == "video" for a in self._pending_assets)
        has_images = any(a.asset_type in ("image", "gif") for a in self._pending_assets)
        has_audio = any(a.asset_type == "audio" for a in self._pending_assets)
        n_images = sum(1 for a in self._pending_assets
                       if a.asset_type in ("image", "gif"))

        if atype == "video":
            if self._pending_assets:
                QMessageBox.warning(
                    self, "Video",
                    "Video must be the only asset on a slide.\n"
                    "Remove other assets first."
                )
                return
        elif atype in ("image", "gif"):
            if has_video:
                QMessageBox.warning(self, "Conflict",
                                    "Cannot add images when a video is attached.")
                return
            if n_images >= 4:
                QMessageBox.warning(self, "Limit", "Maximum 4 images per slide.")
                return
        elif atype == "audio":
            if has_video:
                QMessageBox.warning(self, "Conflict",
                                    "Cannot add audio when a video is attached.")
                return
            if has_audio and not self._stack_check.isChecked():
                # Auto-enable stacking when adding a second audio
                self._stack_check.setChecked(True)

        # Copy to assets dir
        rel, confirmed_type = copy_asset_to_assets_dir(src_path, self._assets_dir)
        self._pending_assets.append(SlideAsset(path=rel, asset_type=confirmed_type))
        self._refresh_asset_list()
        self._refresh_preview()

    def _on_remove_asset(self):
        row = self._asset_table.currentRow()
        if 0 <= row < len(self._pending_assets):
            self._pending_assets.pop(row)
            self._refresh_asset_list()
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
