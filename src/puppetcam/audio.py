"""Microphone loudness -> mouth opening, for when the camera can't see you.

Deliberately simple: an RMS envelope follower, not phoneme recognition.
Loudness already rises and falls with syllables, which reads as talking.
Audio is analysed in memory and never stored.
"""

from __future__ import annotations

import logging
import math

import numpy as np

log = logging.getLogger(__name__)


class MicLevel:
    def __init__(
        self,
        floor_db: float = -48.0,
        range_db: float = 28.0,
        attack_s: float = 0.03,
        release_s: float = 0.12,
        samplerate: int = 16000,
        blocksize: int = 320,  # 20 ms
        device: int | str | None = None,
    ) -> None:
        import sounddevice as sd  # optional at runtime; ships with mediapipe

        self.floor_db = floor_db
        self.range_db = range_db
        block_s = blocksize / samplerate
        self._a_att = 1.0 - math.exp(-block_s / attack_s)
        self._a_rel = 1.0 - math.exp(-block_s / release_s)
        self._env = 0.0
        self._stream = sd.InputStream(
            samplerate=samplerate,
            blocksize=blocksize,
            channels=1,
            dtype="float32",
            device=device,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        rms = float(np.sqrt(np.mean(np.square(indata)) + 1e-12))
        db = 20.0 * math.log10(rms)
        level = min(max((db - self.floor_db) / self.range_db, 0.0), 1.0)
        a = self._a_att if level > self._env else self._a_rel
        self._env += a * (level - self._env)

    def mouth(self) -> float:
        return self._env

    def start(self) -> MicLevel:
        self._stream.start()
        return self

    def stop(self) -> None:
        self._stream.stop()
        self._stream.close()


def try_open_mic(**kwargs) -> MicLevel | None:
    try:
        return MicLevel(**kwargs).start()
    except Exception as exc:  # no device, no permission, no PortAudio...
        log.warning("Microphone disabled: %s", exc)
        return None
