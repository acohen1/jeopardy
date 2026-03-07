"""
media_widget.py — Reusable widget that renders any supported asset type.

Supported types:
  "image"  — static image (PNG/JPG/BMP/WEBP)
  "gif"    — animated GIF via QMovie
  "video"  — MP4/WEBM via QMediaPlayer + QVideoWidget
  "audio"  — MP3/WAV via QMediaPlayer (audio-only, shows waveform icon)
  ""       — no asset, widget is empty/hidden
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QUrl, QSize
from PyQt6.QtGui import QPixmap, QMovie, QFont
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QSizePolicy, QStackedWidget,
)

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    _MEDIA_AVAILABLE = True
except ImportError:
    _MEDIA_AVAILABLE = False


class MediaWidget(QWidget):
    """
    Drop this widget anywhere you want to display a board asset.
    Call load(path, asset_type) to switch content.
    Call stop() to stop playback (video/audio).
    Call play() to (re)start playback.
    """

    def __init__(self, parent=None, auto_play: bool = True):
        super().__init__(parent)
        self._auto_play = auto_play
        self._asset_type = ""
        self._movie: QMovie | None = None
        self._player: "QMediaPlayer | None" = None
        self._audio_out: "QAudioOutput | None" = None

        self._stack = QStackedWidget(self)

        # --- Blank page ---
        self._blank = QLabel()
        self._blank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._blank)           # index 0

        # --- Image page ---
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setScaledContents(False)
        self._stack.addWidget(self._image_label)     # index 1

        # --- GIF page ---
        self._gif_label = QLabel()
        self._gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._gif_label)       # index 2

        # --- Video page ---
        if _MEDIA_AVAILABLE:
            self._video_widget = QVideoWidget()
            self._stack.addWidget(self._video_widget)  # index 3
        else:
            _placeholder = QLabel("Video not available")
            _placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stack.addWidget(_placeholder)

        # --- Audio page ---
        self._audio_label = QLabel("♪")
        self._audio_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(72)
        self._audio_label.setFont(font)
        self._audio_label.setStyleSheet("color: #FFD700;")
        self._stack.addWidget(self._audio_label)     # index 4

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------ #
    #  Public API                                                           #
    # ------------------------------------------------------------------ #
    def load(self, path: str, asset_type: str):
        self.stop()
        self._asset_type = asset_type

        if not path or not asset_type or not os.path.isfile(path):
            self._stack.setCurrentIndex(0)
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

    def clear(self):
        self.stop()
        self._asset_type = ""
        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------ #
    #  Resize — rescale static image to fit                                #
    # ------------------------------------------------------------------ #
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._asset_type == "image" and hasattr(self, "_raw_pixmap"):
            self._fit_image()

    # ------------------------------------------------------------------ #
    #  Internal loaders                                                     #
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
        if self._player is None and _MEDIA_AVAILABLE:
            self._audio_out = QAudioOutput()
            self._audio_out.setVolume(1.0)
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._audio_out)
            # Only attach video widget for video
            if hasattr(self, "_video_widget"):
                self._player.setVideoOutput(self._video_widget)
