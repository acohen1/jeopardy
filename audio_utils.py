"""
audio_utils.py — Audio mixing utility for stacked audio clips.

Uses pydub to overlay multiple audio files into a single output.
Requires pydub (pip install pydub). For non-WAV formats, ffmpeg must
be on the system PATH.
"""
from __future__ import annotations

import hashlib
import os

_PYDUB_AVAILABLE = False
try:
    from pydub import AudioSegment
    _PYDUB_AVAILABLE = True
except ImportError:
    pass


def _configure_ffmpeg():
    """Point pydub at the bundled ffmpeg.exe when running as a PyInstaller app,
    or fall back to finding it on the system PATH in dev mode."""
    if not _PYDUB_AVAILABLE:
        return
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(base, "ffmpeg.exe")
    if os.path.isfile(candidate):
        AudioSegment.converter = candidate
        AudioSegment.ffmpeg = candidate


_configure_ffmpeg()


def is_available() -> bool:
    """Check whether pydub is installed and audio stacking can work."""
    return _PYDUB_AVAILABLE


def mix_audio_overlay(paths: list[str], output_dir: str,
                      volumes: list[float] | None = None) -> str:
    """
    Overlay (mix) multiple audio files into a single WAV.

    *volumes* is an optional list of per-track gain multipliers (0.0–1.0).
    Uses a deterministic filename based on the source paths and volumes so
    repeated calls with the same inputs return the cached result.

    Returns the absolute path to the mixed output file.
    """
    if not _PYDUB_AVAILABLE:
        raise RuntimeError("pydub is not installed — cannot mix audio")
    if not paths:
        raise ValueError("No audio paths provided")
    if len(paths) == 1 and (volumes is None or volumes[0] == 1.0):  # noqa: skip mix only if full volume
        return paths[0]  # nothing to mix

    # Normalise volumes list
    if volumes is None:
        volumes = [1.0] * len(paths)
    else:
        # Pad / trim to match paths length
        volumes = list(volumes) + [1.0] * (len(paths) - len(volumes))
        volumes = volumes[:len(paths)]

    # Deterministic output name (includes volumes so cache busts on change)
    vol_str = ",".join(f"{v:.2f}" for v in volumes)
    key = "|".join(sorted(os.path.basename(p) for p in paths)) + "||" + vol_str
    digest = hashlib.md5(key.encode()).hexdigest()[:12]
    out_path = os.path.join(output_dir, f"_mix_{digest}.wav")

    # Return cached if it already exists
    if os.path.isfile(out_path):
        return out_path

    os.makedirs(output_dir, exist_ok=True)

    def _apply_volume(seg: AudioSegment, vol: float) -> AudioSegment:
        if vol <= 0:
            return AudioSegment.silent(duration=len(seg))
        if vol != 1.0:
            import math
            db_change = 20 * math.log10(vol)
            return seg + db_change
        return seg

    base = _apply_volume(AudioSegment.from_file(paths[0]), volumes[0])
    for p, v in zip(paths[1:], volumes[1:]):
        layer = _apply_volume(AudioSegment.from_file(p), v)
        base = base.overlay(layer)
    base.export(out_path, format="wav")
    return out_path
