"""Microphone capture with real-time audio-level callback.

The level callback drives the dancing-character indicator: every frame, the
current RMS amplitude (0.0-1.0) is sent to whoever subscribed.
"""
from __future__ import annotations

import io
import threading
import wave
from collections.abc import Callable
from typing import Optional

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: Optional[int] = None,
        on_level: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device if device is not None and device >= 0 else None
        self.on_level = on_level

        self._stream: Optional[sd.InputStream] = None
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording = False
        self._current_level: float = 0.0   # polled by main thread via QTimer
        self._agc_floor: float | None = None   # adaptive noise-floor (int16 RMS)
        self._agc_peak: float | None = None    # adaptive signal-peak (int16 RMS)

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            # Drop frame on overflow rather than crashing; user will only notice a tiny gap.
            pass
        with self._lock:
            self._frames.append(indata.copy())
        try:
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            if indata.dtype != np.int16:
                rms *= 32768.0             # bring float PCM (~±1.0) onto the int16 scale

            # Auto-gain so the dancing character reacts well on ANY microphone,
            # quiet or loud. A fixed mapping can't satisfy both "dances on
            # speech" and "still on silence" across mics (a very quiet mic's
            # speech RMS can be ~90 — 1/5 of normal). Instead we learn this
            # mic's own noise floor and signal peak and report where the live
            # level sits between them.
            SPAN_MIN = 60.0
            if self._agc_floor is None:    # first frame → calibrate to this mic
                self._agc_floor = rms
                self._agc_peak = rms + SPAN_MIN
            # Floor: follow downward fast, upward slowly (speech can't raise it).
            if rms < self._agc_floor:
                self._agc_floor += (rms - self._agc_floor) * 0.10
            else:
                self._agc_floor += (rms - self._agc_floor) * 0.02
            # Peak: follow upward fast, downward slowly.
            if rms > self._agc_peak:
                self._agc_peak += (rms - self._agc_peak) * 0.30
            else:
                self._agc_peak += (rms - self._agc_peak) * 0.02
            span = max(self._agc_peak - self._agc_floor, SPAN_MIN)
            gate = self._agc_floor + 0.15 * span     # below this = treated as silence
            denom = self._agc_peak - gate
            if denom <= 0:
                level = 0.0
            else:
                level = min(1.0, max(0.0, rms - gate) / denom) ** 0.6
            # Store for main-thread polling — avoids cross-thread Signal.emit()
            # from PortAudio's native C thread which can silently drop Qt events.
            self._current_level = level
            if self.on_level is not None:
                self.on_level(level)
        except Exception:
            pass

    def start(self) -> None:
        if self._recording:
            return
        self._frames = []
        self._agc_floor = None       # recalibrate auto-gain for this session
        self._agc_peak = None
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()
        self._recording = True

    def stop(self) -> bytes:
        """Stop recording and return a WAV-encoded byte stream (16kHz mono PCM16)."""
        if not self._recording:
            return b""
        self._recording = False
        assert self._stream is not None
        self._stream.stop()
        self._stream.close()
        self._stream = None

        with self._lock:
            frames = self._frames
            self._frames = []
        if not frames:
            return b""

        audio = np.concatenate(frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()


def list_input_devices() -> list[dict]:
    """Return [{index, name, channels, default}, ...] for input-capable devices."""
    default_in = sd.default.device[0] if sd.default.device else -1
    result = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            result.append({
                "index": i,
                "name": dev["name"],
                "channels": dev["max_input_channels"],
                "default": i == default_in,
            })
    return result
