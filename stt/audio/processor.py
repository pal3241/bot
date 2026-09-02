import audioop

import numpy as np
from numpy.typing import NDArray


def pcm_stereo_48k_to_mono_16k(pcm: bytes) -> NDArray[np.float32]:
    if not pcm:
        raise ValueError("PCM untuk STT tidak boleh kosong.")
    mono: bytes = audioop.tomono(pcm, 2, 0.5, 0.5)
    converted: bytes
    converted, _ = audioop.ratecv(mono, 2, 1, 48000, 16000, None)
    samples: NDArray[np.int16] = np.frombuffer(converted, dtype=np.int16)
    return samples.astype(np.float32) / np.float32(32768.0)
