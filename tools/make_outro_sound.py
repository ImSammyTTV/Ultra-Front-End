"""Compose the closing sound from scratch (no samples): writes app/assets/outro.wav.

The intro in reverse, in its own words: it opens on the chord the intro blooms into, with two glass tones, then the
chord settles down an octave into the deep drone and fades into the same long dark space, reaching silence by 3 seconds.
The same sine tones, detuned spread and synthetic hall as tools/make_intro_sound.py. numpy only.
"""
import os
import wave

import numpy as np

SR = 44100
LEN = 3.2
t = np.arange(int(SR * LEN)) / SR
# the intro's notes: D with a raised fourth
D2, A2, D3, A3, D4, E4, FS4, A4, CS5, E5, FS5, A5 = 73.42, 110.0, 146.83, 220.0, 293.66, 329.63, 369.99, 440.0, 554.37, 659.26, 739.99, 880.0


def soft(freq, env, cents=0.0, rate=.13, phase=0.0, glide=None):
    """One slowly drifting tone with a touch of warmth; glide lowers it gradually (cents over time)."""
    bend = cents + 4 * np.sin(2 * np.pi * rate * t + phase) + (glide if glide is not None else 0)
    p = 2 * np.pi * np.cumsum(freq * 2 ** (bend / 1200)) / SR + phase
    return env * (np.sin(p) + .16 * np.sin(2 * p + .5) + .05 * np.sin(3 * p))


def wide(freq, env, level, glide=None):
    """A note spread across the speakers by several slightly detuned copies."""
    l, r = np.zeros_like(t), np.zeros_like(t)
    for i, (cents, pan) in enumerate(((-7, .1), (-3, .75), (2, .25), (6, .9))):
        v = soft(freq, env, cents, rate=.09 + i * .03, phase=i * 1.3, glide=glide)
        l, r = l + v * (1 - pan), r + v * pan
    return level * l, level * r


def glass(freq, start, level):
    x = np.clip(t - start, 0, None)
    on = (t >= start) * (1 - np.exp(-x / .025))
    return level * on * (np.exp(-x / .9) * np.sin(2 * np.pi * freq * x) + .12 * np.exp(-x / .3) * np.sin(2 * np.pi * freq * 2.01 * x))


def lowpass(x, hz):
    b = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(np.fft.rfft(x) / np.sqrt(1 + (b / hz) ** 4), len(x))


def hall(x, seconds, seed, dark=2400):
    n = int(SR * seconds)
    ir = np.random.default_rng(seed).standard_normal(n) * np.exp(-np.arange(n) / SR / (seconds / 6))
    ir *= 1 - np.exp(-np.arange(n) / SR / .03)
    ir = lowpass(ir, dark)
    size = len(x) + n
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    return wet / (np.abs(wet).max() + 1e-9)


left, right = np.zeros_like(t), np.zeros_like(t)
# The chord, already open, fading as it sinks a little (a quarter tone over two seconds: settling, not falling)
chord = (1 - np.exp(-t / .04)) * np.exp(-t / .9)
sink = -50 * np.clip(t / 2.0, 0, 1) ** 1.5
for f, level in ((D3, .14), (A3, .14), (E4, .1), (FS4, .12), (A4, .09), (CS5, .05), (E5, .04)):
    a, b = wide(f, chord, level, glide=sink)
    left, right = left + a, right + b
# ...into the deep drone it came from, which swells briefly and goes
drone = np.clip(t / .5, 0, 1) ** 1.5 * np.exp(-np.clip(t - .5, 0, None) / .8)
for f, level in ((D2, .32), (A2, .16), (D3, .08)):
    a, b = wide(f, drone, level)
    left, right = left + a, right + b
# Two glass tones, high then lower, across the speakers
glass_l = glass(A5, .02, .08) + glass(D4 * 2, .5, .05)
glass_r = glass(FS5, .2, .07)

wet_l = hall(left + glass_l + glass_r * .3, 3.0, 1)
wet_r = hall(right + glass_r + glass_l * .3, 3.0, 2)
dry = 1 / max(np.abs(left).max(), np.abs(right).max())
out_l = left * dry * .55 + glass_l * .9 + wet_l * .6
out_r = right * dry * .55 + glass_r * .9 + wet_r * .6
end = np.clip((LEN - t) / 1.4, 0, 1) ** 1.8  # always reaches silence
start = np.clip(t / .01, 0, 1)  # no click at the start
stereo = np.stack([out_l * end * start, out_r * end * start], axis=1)
stereo = np.tanh(stereo / np.abs(stereo).max() * 1.1)
stereo *= 10 ** (-7 / 20) / np.abs(stereo).max()  # a little quieter than the intro

path = os.path.join(os.path.dirname(__file__), "..", "app", "assets", "outro.wav")
with wave.open(path, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((stereo * 32767).astype("<i2").tobytes())
rms = lambda a, b: 20 * np.log10(np.sqrt(np.mean(stereo[int(a * SR):int(b * SR)] ** 2)) + 1e-9)
print("written", os.path.getsize(path) // 1024, "KB; level dB 0-0.5s", round(rms(0, .5), 1), "| 0.5-1.5s", round(rms(.5, 1.5), 1),
      "| 1.5-2.5s", round(rms(1.5, 2.5), 1), "| last 0.2s", round(rms(LEN - .2, LEN), 1))
