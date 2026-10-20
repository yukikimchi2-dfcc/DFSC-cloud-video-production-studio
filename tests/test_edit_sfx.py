"""Synthesised (royalty-free) sound effects and music bed used by the reel edits."""
import numpy as np
import pytest

from studio.edit import sfx


@pytest.mark.parametrize("name", sorted(sfx.EFFECTS))
def test_effects_are_short_stereo_and_not_clipping(name):
    x = sfx.EFFECTS[name]()
    assert x.ndim == 2 and x.shape[1] == 2 and x.dtype == np.float32
    assert 0.05 < len(x) / sfx.SR <= 1.0
    peak = np.abs(x).max()
    assert 0.1 < peak <= 1.0


def test_music_bed_length_fade_and_headroom():
    x = sfx.music_bed(6.0)
    assert len(x) == int(6.0 * sfx.SR) and x.shape[1] == 2
    assert np.abs(x).max() <= 10 ** (-1 / 20) + 1e-3                    # -1 dBFS ceiling
    assert np.abs(x[-200:]).max() < 0.01                                  # fades out
    assert np.abs(x[int(3 * sfx.SR):int(4 * sfx.SR)]).mean() > 0.01       # body is audible


def test_write_wav_roundtrip(tmp_path):
    from scipy.io import wavfile
    p = sfx.write_wav(tmp_path / "pop.wav", sfx.pop())
    sr, data = wavfile.read(p)
    assert sr == sfx.SR and data.shape[1] == 2 and data.dtype == np.int16
