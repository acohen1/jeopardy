"""
media_widget.py — Reusable widget that renders any supported asset type.

Supported types:
  "image"  — static image (PNG/JPG/BMP/WEBP)
  "gif"    — animated GIF via QMovie
  "video"  — MP4/WEBM via QMediaPlayer + QVideoWidget  (controls shown)
  "audio"  — MP3/WAV via QMediaPlayer (controls shown, music note icon)
  ""       — no asset, widget is empty/hidden

Pass show_controls=True to enable the full transport bar (seek, volume,
play/pause/stop/rewind, fullscreen) for video and audio.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QUrl, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QPixmap, QMovie, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QStackedWidget, QSlider, QPushButton,
)

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    _MEDIA_AVAILABLE = True
except ImportError:
    _MEDIA_AVAILABLE = False

# ---- theme colours ----
_CTRL_BG = "#2f2f2f"
_TEXT     = "#e5ddd5"
_ACCENT   = "#7daf8d"

_SLIDER_H = """
    QSlider::groove:horizontal {
        background: #404040; height: 5px; border-radius: 2px;
    }
    QSlider::sub-page:horizontal {
        background: #7daf8d; border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #91c4a1; width: 14px; height: 14px;
        margin: -5px 0; border-radius: 7px;
    }
"""
_VOL_SLIDER = """
    QSlider::groove:horizontal {
        background: #404040; height: 4px; border-radius: 2px;
    }
    QSlider::sub-page:horizontal {
        background: #7daf8d; border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #91c4a1; width: 12px; height: 12px;
        margin: -4px 0; border-radius: 6px;
    }
"""
_BTN_STYLE = (
    "QPushButton { background: #404040; color: #e5ddd5; border-radius: 5px;"
    " font-size: 16px; padding: 4px 10px; border: 1px solid #555; }"
    "QPushButton:hover { background: #505050; color: #91c4a1; }"
    "QPushButton:pressed { background: #303030; }"
)


def _fmt_ms(ms: int) -> str:
    s = ms // 1000
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"



# ------------------------------------------------------------------ #
#  Clickable QVideoWidget subclass                                    #
# ------------------------------------------------------------------ #
if _MEDIA_AVAILABLE:
    class _ClickableVideo(QVideoWidget):
        """QVideoWidget that emits clicked() on left-button press."""
        clicked = pyqtSignal()

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.clicked.emit()
            super().mousePressEvent(event)
else:
    _ClickableVideo = None  # type: ignore[assignment,misc]


# ------------------------------------------------------------------ #
#  Reusable transport controls bar                                    #
# ------------------------------------------------------------------ #
class _ControlsBar(QWidget):
    """
    Self-contained transport bar: seek slider + buttons + volume + time.
    Attach to a QMediaPlayer via attach(player, audio_out).
    Detach via detach() before the player is given to another widget.
    """

    def __init__(self, parent=None, poll_interval: int = 300, compact: bool = False):
        super().__init__(parent)
        self._player: "QMediaPlayer | None" = None
        self._audio_out: "QAudioOutput | None" = None
        self._dragging = False
        self._compact = compact

        self.setStyleSheet(f"background: {_CTRL_BG}; border-radius: 6px;")

        # ---- create all controls up-front (so attributes/handlers always
        #      exist, regardless of which layout variant is used) ----
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setStyleSheet(_SLIDER_H)
        self.seek_slider.sliderPressed.connect(self._on_pressed)
        self.seek_slider.sliderReleased.connect(self._on_released)
        self.seek_slider.sliderMoved.connect(self._on_moved)

        self.rewind_btn = QPushButton("⏮")
        self.rewind_btn.setToolTip("Rewind to start")
        self.rewind_btn.setStyleSheet(_BTN_STYLE)
        self.rewind_btn.clicked.connect(self._on_rewind)

        self.play_btn = QPushButton("▶")
        self.play_btn.setToolTip("Play / Pause  (or click video)")
        self.play_btn.setStyleSheet(_BTN_STYLE)
        self.play_btn.clicked.connect(self.toggle_play_pause)

        self.stop_btn = QPushButton("■")
        self.stop_btn.setToolTip("Stop")
        self.stop_btn.setStyleSheet(_BTN_STYLE)
        self.stop_btn.clicked.connect(self._on_stop)

        self.vol_icon = QLabel("🔊")
        self.vol_icon.setStyleSheet(f"color: {_TEXT}; font-size: 14px; background: transparent;")

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setToolTip("Volume")
        self.vol_slider.setStyleSheet(_VOL_SLIDER)
        self.vol_slider.valueChanged.connect(self._on_volume)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet(f"color: {_TEXT}; font-size: 13px; background: transparent;")

        self.fs_btn = QPushButton("⛶")
        self.fs_btn.setToolTip("Toggle fullscreen  [F]")
        self.fs_btn.setStyleSheet(_BTN_STYLE)

        if compact:
            self._build_compact_layout()
        else:
            self._build_full_layout()

        # Position poll timer
        self._timer = QTimer(self)
        self._timer.setInterval(poll_interval)
        self._timer.timeout.connect(self._poll)

        # Prevent buttons/sliders from stealing keyboard focus —
        # key events must flow to the parent window's event filter
        for w in self.findChildren((QPushButton, QSlider)):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _build_full_layout(self):
        """Two-row transport bar (seek on top, buttons below)."""
        self.rewind_btn.setFixedWidth(42)
        self.play_btn.setFixedWidth(42)
        self.stop_btn.setFixedWidth(42)
        self.vol_slider.setFixedWidth(90)
        self.fs_btn.setFixedWidth(42)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)
        root.addWidget(self.seek_slider)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addWidget(self.rewind_btn)
        btn_row.addWidget(self.play_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.vol_icon)
        btn_row.addWidget(self.vol_slider)
        btn_row.addStretch()
        btn_row.addWidget(self.time_label)
        btn_row.addSpacing(6)
        btn_row.addWidget(self.fs_btn)
        root.addLayout(btn_row)

    def _build_compact_layout(self):
        """Single-row mini transport bar for small grid cells."""
        # Unused-in-compact controls stay created (handlers reference them)
        # but are hidden and left out of the layout.
        self.rewind_btn.setVisible(False)
        self.stop_btn.setVisible(False)
        self.vol_icon.setVisible(False)

        self.play_btn.setFixedWidth(34)
        self.fs_btn.setFixedWidth(30)
        self.vol_slider.setFixedWidth(54)
        self.time_label.setStyleSheet(
            f"color: {_TEXT}; font-size: 11px; background: transparent;")

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(5)
        row.addWidget(self.play_btn)
        row.addWidget(self.seek_slider, stretch=1)
        row.addWidget(self.time_label)
        row.addWidget(self.vol_slider)
        row.addWidget(self.fs_btn)

    # ---- Attach / detach ----
    def attach(self, player: "QMediaPlayer", audio_out: "QAudioOutput",
               vol: int = 100):
        self._player = player
        self._audio_out = audio_out
        self.vol_slider.setValue(vol)
        player.durationChanged.connect(self._on_duration)
        player.playbackStateChanged.connect(self._on_state)
        # Sync initial state — durationChanged won't fire if duration already known
        if _MEDIA_AVAILABLE:
            dur = player.duration()
            if dur > 0:
                self._on_duration(dur)
            playing = (player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
            self.play_btn.setText("⏸" if playing else "▶")
            if playing:
                self._timer.start()

    def detach(self):
        if self._player and _MEDIA_AVAILABLE:
            try:
                self._player.durationChanged.disconnect(self._on_duration)
                self._player.playbackStateChanged.disconnect(self._on_state)
            except RuntimeError:
                pass
        self._timer.stop()
        self._player = None
        self._audio_out = None

    def current_volume(self) -> int:
        return self.vol_slider.value()

    def reset_display(self):
        self.seek_slider.setValue(0)
        self.time_label.setText("0:00 / 0:00")
        self.play_btn.setText("▶")

    def seek_by(self, ms: int):
        """Seek forward (positive) or backward (negative) by ms milliseconds."""
        if not self._player:
            return
        dur = self._player.duration()
        new_pos = max(0, min(dur, self._player.position() + ms))
        self._player.setPosition(new_pos)
        # Update UI immediately (poll timer may be stopped when paused)
        self.seek_slider.setValue(new_pos)
        self.time_label.setText(f"{_fmt_ms(new_pos)} / {_fmt_ms(dur)}")

    # ---- Slots ----
    def toggle_play_pause(self):
        if not self._player or not _MEDIA_AVAILABLE:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_stop(self):
        if self._player:
            self._player.stop()
        self.reset_display()

    def _on_rewind(self):
        if self._player:
            self._player.setPosition(0)
            self._player.play()

    def _on_volume(self, val: int):
        if self._audio_out:
            self._audio_out.setVolume(val / 100.0)

    def _on_pressed(self):
        self._dragging = True

    def _on_released(self):
        self._dragging = False
        if self._player:
            self._player.setPosition(self.seek_slider.value())

    def _on_moved(self, value: int):
        if self._player and self._dragging:
            dur = self._player.duration() or 1
            self.time_label.setText(f"{_fmt_ms(value)} / {_fmt_ms(dur)}")

    def _poll(self):
        if not self._player or self._dragging:
            return
        pos = self._player.position()
        dur = self._player.duration()
        self.seek_slider.setValue(pos)
        self.time_label.setText(f"{_fmt_ms(pos)} / {_fmt_ms(dur)}")

    def _on_duration(self, dur: int):
        self.seek_slider.setRange(0, dur)
        self.time_label.setText(f"0:00 / {_fmt_ms(dur)}")

    def _on_state(self, state):
        if not _MEDIA_AVAILABLE:
            return
        playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        self.play_btn.setText("⏸" if playing else "▶")
        if playing:
            self._timer.start()
        else:
            self._timer.stop()


# ------------------------------------------------------------------ #
#  Fullscreen video window                                            #
# ------------------------------------------------------------------ #
class _FullscreenWindow(QWidget):
    """
    Custom fullscreen window that owns a new QVideoWidget and a copy of
    the transport controls, sharing the same QMediaPlayer / QAudioOutput.
    On close it restores the player's video output to the embedded widget.
    """

    def __init__(self, player: "QMediaPlayer", audio_out: "QAudioOutput",
                 embedded_video: "QVideoWidget", restore_cb, current_vol: int,
                 parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self._player = player
        self._audio_out = audio_out
        self._embedded_video = embedded_video
        self._restore_cb = restore_cb

        self.setWindowTitle("Video — Fullscreen")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint
        )
        self.setStyleSheet("background: black;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Controls bar (built first so click-to-pause can reference it)
        self._controls = _ControlsBar(self)
        self._controls.fs_btn.setText("✕")
        self._controls.fs_btn.setToolTip("Exit fullscreen  [Esc / F]")
        self._controls.fs_btn.clicked.connect(self.close)

        # New video widget (player will output here while fullscreen)
        if _MEDIA_AVAILABLE and _ClickableVideo is not None:
            self._vw = _ClickableVideo()
            self._vw.clicked.connect(self._controls.toggle_play_pause)
        else:
            self._vw = QVideoWidget()  # type: ignore[assignment]
        self._vw.setStyleSheet("background: black;")
        root.addWidget(self._vw, stretch=1)
        root.addWidget(self._controls)

        # Switch player output to our new video widget
        player.setVideoOutput(self._vw)
        self._controls.attach(player, audio_out, vol=current_vol)

        # Keyboard shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, activated=self.close)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self,
                  activated=self._controls.toggle_play_pause)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self,
                  activated=lambda: self._controls.seek_by(-1000))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self,
                  activated=lambda: self._controls.seek_by(1000))
        QShortcut(QKeySequence(Qt.Key.Key_R), self,
                  activated=self._controls._on_rewind)

        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        vol = self._controls.current_volume()
        self._controls.detach()
        # Restore video output to embedded widget
        self._player.setVideoOutput(self._embedded_video)
        self._restore_cb(vol)
        super().closeEvent(event)


# ------------------------------------------------------------------ #
#  MediaWidget                                                        #
# ------------------------------------------------------------------ #
class MediaWidget(QWidget):
    """
    Drop this widget anywhere you want to display a board asset.
    Call load(path, asset_type) to switch content.
    Call stop() to stop playback.
    Call play() to (re)start playback.

    Signals:
      activated          — user interacted with this widget (click / control)
      fullscreen_opened  — embedded video entered fullscreen
      fullscreen_closed  — fullscreen window closed
    """

    activated = pyqtSignal()
    fullscreen_opened = pyqtSignal()
    fullscreen_closed = pyqtSignal()
    playing_changed = pyqtSignal(bool)   # True when playing, False when paused/stopped

    def __init__(self, parent=None, auto_play: bool = True, show_controls: bool = False,
                 manage_hotkeys: bool = True, compact_controls: bool = False):
        super().__init__(parent)
        self._auto_play = auto_play
        self._show_controls = show_controls
        self._manage_hotkeys = manage_hotkeys
        self._compact_controls = compact_controls
        self._asset_type = ""
        self._movie: QMovie | None = None
        self._player: "QMediaPlayer | None" = None
        self._audio_out: "QAudioOutput | None" = None
        self._fs_window: "_FullscreenWindow | None" = None
        self._key_filter_win = None  # window we've installed as event filter on

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Stacked display area ----
        self._stack = QStackedWidget(self)
        root.addWidget(self._stack, stretch=1)

        # page 0 — blank
        self._blank = QLabel()
        self._blank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._blank)

        # page 1 — static image
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setScaledContents(False)
        self._stack.addWidget(self._image_label)

        # page 2 — animated GIF
        self._gif_label = QLabel()
        self._gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._gif_label)

        # page 3 — video (clickable subclass)
        if _MEDIA_AVAILABLE and _ClickableVideo is not None:
            self._video_widget = _ClickableVideo()
            self._video_widget.setToolTip("Click to play / pause")
            self._stack.addWidget(self._video_widget)
        else:
            _nv = QLabel("Video playback not available")
            _nv.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _nv.setStyleSheet("color: #9a9080;")
            self._stack.addWidget(_nv)

        # page 4 — audio (music note placeholder)
        self._audio_label = QLabel("♪")
        self._audio_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        af = QFont()
        af.setPointSize(72)
        self._audio_label.setFont(af)
        self._audio_label.setStyleSheet("color: #7daf8d;")
        self._stack.addWidget(self._audio_label)

        self._stack.setCurrentIndex(0)

        # ---- Transport controls bar ----
        self._controls = _ControlsBar(self, compact=self._compact_controls)
        self._controls.fs_btn.clicked.connect(self._on_fullscreen)
        root.addWidget(self._controls)
        self._controls.setVisible(False)

        # Wire click-to-pause on embedded video widget — only in interactive
        # (controls-shown) contexts like play mode. In the editor preview
        # (show_controls=False) clicking the video does nothing; playback is
        # driven from the asset table instead.
        if (_MEDIA_AVAILABLE and self._show_controls
                and isinstance(getattr(self, "_video_widget", None), _ClickableVideo)):
            self._video_widget.clicked.connect(self._controls.toggle_play_pause)
            self._video_widget.clicked.connect(self._mark_activated)

        # Emit `activated` whenever the user touches the transport controls,
        # so an owning grid can mark this cell as the focused one.
        self._controls.play_btn.clicked.connect(self._mark_activated)
        self._controls.rewind_btn.clicked.connect(self._mark_activated)
        self._controls.stop_btn.clicked.connect(self._mark_activated)
        self._controls.fs_btn.clicked.connect(self._mark_activated)
        self._controls.seek_slider.sliderPressed.connect(self._mark_activated)
        self._controls.vol_slider.sliderPressed.connect(self._mark_activated)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _mark_activated(self, *args):
        self.activated.emit()

    # ------------------------------------------------------------------ #
    #  Arrow-key seek (embedded mode) — event filter on parent window      #
    # ------------------------------------------------------------------ #
    def showEvent(self, event):
        super().showEvent(event)
        if (self._manage_hotkeys and self._show_controls
                and self._key_filter_win is None):
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
                self._key_filter_win = app

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._key_filter_win is not None:
            try:
                self._key_filter_win.removeEventFilter(self)
            except RuntimeError:
                pass
            self._key_filter_win = None

    def eventFilter(self, obj, event):
        # Keyboard shortcuts (from QApplication-level filter)
        if (event.type() == QEvent.Type.KeyPress
                and self._asset_type in ("video", "audio")
                and self._player is not None):
            key = event.key()
            if key == Qt.Key.Key_Left:
                self._controls.seek_by(-1000)
                return True
            elif key == Qt.Key.Key_Right:
                self._controls.seek_by(1000)
                return True
            elif key == Qt.Key.Key_Space:
                self._controls.toggle_play_pause()
                return True
            elif key == Qt.Key.Key_F:
                self._on_fullscreen()
                return True
            elif key == Qt.Key.Key_R:
                self._controls._on_rewind()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ #
    #  Public API                                                           #
    # ------------------------------------------------------------------ #
    def load(self, path: str, asset_type: str):
        self.stop()
        self._asset_type = asset_type

        if not path or not asset_type or not os.path.isfile(path):
            self._stack.setCurrentIndex(0)
            self._controls.setVisible(False)
            return

        if asset_type == "image":
            self._load_image(path)
        elif asset_type == "gif":
            self._load_gif(path)
        elif asset_type == "video":
            self._load_video(path)
        elif asset_type == "audio":
            self._load_audio(path)
        else:
            self._stack.setCurrentIndex(0)

        is_timed = asset_type in ("video", "audio")
        self._controls.setVisible(self._show_controls and is_timed)
        # Fullscreen only makes sense for video
        self._controls.fs_btn.setVisible(asset_type == "video")

    def play(self):
        if self._asset_type == "gif" and self._movie:
            self._movie.start()
        elif self._asset_type in ("video", "audio") and self._player:
            self._player.play()

    def stop(self):
        if self._movie:
            self._movie.stop()
            self._movie = None
        if self._player:
            self._player.stop()
        self._controls.reset_display()

    def clear(self):
        self.stop()
        self._asset_type = ""
        self._stack.setCurrentIndex(0)
        self._stack.setVisible(True)
        self._controls.setVisible(False)

    def set_controls_only(self, controls_only: bool):
        """Hide the visual area (music note / video) and show only controls."""
        self._stack.setVisible(not controls_only)

    # ------------------------------------------------------------------ #
    #  Thin control surface (used by an owning SlideGrid)                 #
    # ------------------------------------------------------------------ #
    @property
    def is_video(self) -> bool:
        return self._asset_type == "video"

    def is_timed(self) -> bool:
        return self._asset_type in ("video", "audio")

    def is_playing(self) -> bool:
        return bool(_MEDIA_AVAILABLE and self._player is not None
                    and self._player.playbackState()
                    == QMediaPlayer.PlaybackState.PlayingState)

    def set_volume(self, pct: int):
        """Set playback volume (0-100); also updates the transport slider."""
        self._controls.vol_slider.setValue(int(pct))

    def seek_relative(self, ms: int):
        self._controls.seek_by(ms)

    def toggle_play_pause(self):
        self._controls.toggle_play_pause()

    def restart(self):
        self._controls._on_rewind()

    def toggle_fullscreen(self):
        self._on_fullscreen()

    def force_close_fullscreen(self):
        if self._fs_window is not None:
            self._fs_window.close()

    # ------------------------------------------------------------------ #
    #  Resize — rescale static image to fit                              #
    # ------------------------------------------------------------------ #
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._asset_type == "image" and hasattr(self, "_raw_pixmap"):
            self._fit_image()

    # ------------------------------------------------------------------ #
    #  Internal loaders                                                  #
    # ------------------------------------------------------------------ #
    def _load_image(self, path: str):
        px = QPixmap(path)
        if px.isNull():
            self._stack.setCurrentIndex(0)
            return
        self._raw_pixmap = px
        self._fit_image()
        self._stack.setCurrentIndex(1)

    def _fit_image(self):
        if not hasattr(self, "_raw_pixmap"):
            return
        size = self._stack.size()
        scaled = self._raw_pixmap.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    def _load_gif(self, path: str):
        movie = QMovie(path)
        if not movie.isValid():
            self._stack.setCurrentIndex(0)
            return
        self._movie = movie
        self._gif_label.setMovie(movie)
        self._stack.setCurrentIndex(2)
        if self._auto_play:
            movie.start()

    def _load_video(self, path: str):
        if not _MEDIA_AVAILABLE:
            self._stack.setCurrentIndex(0)
            return
        self._ensure_player()
        self._player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
        self._stack.setCurrentIndex(3)
        if self._auto_play:
            self._player.play()

    def _load_audio(self, path: str):
        if not _MEDIA_AVAILABLE:
            self._stack.setCurrentIndex(4)
            return
        self._ensure_player()
        self._player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
        self._stack.setCurrentIndex(4)
        if self._auto_play:
            self._player.play()

    def _ensure_player(self):
        if self._player is not None:
            return
        if not _MEDIA_AVAILABLE:
            return
        self._audio_out = QAudioOutput()
        self._audio_out.setVolume(self._controls.current_volume() / 100.0)
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_out)
        self._player.playbackStateChanged.connect(self._emit_playing_changed)
        if hasattr(self, "_video_widget"):
            self._player.setVideoOutput(self._video_widget)
        self._controls.attach(self._player, self._audio_out)

    def _emit_playing_changed(self, state):
        if _MEDIA_AVAILABLE:
            self.playing_changed.emit(
                state == QMediaPlayer.PlaybackState.PlayingState)

    # ------------------------------------------------------------------ #
    #  Fullscreen                                                        #
    # ------------------------------------------------------------------ #
    def _on_fullscreen(self):
        if not self._player or not _MEDIA_AVAILABLE:
            return
        if self._fs_window is not None:
            self._fs_window.close()
            return
        embedded = getattr(self, "_video_widget", None)
        if embedded is None:
            return
        # Detach controls from player — fullscreen window will attach them
        self._controls.detach()
        vol = self._controls.current_volume()
        self._controls.fs_btn.setText("✕")
        self._controls.fs_btn.setToolTip("Exit fullscreen")

        self._fs_window = _FullscreenWindow(
            player=self._player,
            audio_out=self._audio_out,
            embedded_video=embedded,
            restore_cb=self._on_fullscreen_closed,
            current_vol=vol,
            parent=self.window(),
        )
        self.fullscreen_opened.emit()

    def _on_fullscreen_closed(self, restored_vol: int):
        """Called by _FullscreenWindow.closeEvent — player output already restored."""
        self._fs_window = None
        self._controls.fs_btn.setText("⛶")
        self._controls.fs_btn.setToolTip("Toggle fullscreen  [F]")
        # Re-attach controls to player
        if self._player and self._audio_out:
            self._controls.attach(self._player, self._audio_out, vol=restored_vol)
        self.fullscreen_closed.emit()
