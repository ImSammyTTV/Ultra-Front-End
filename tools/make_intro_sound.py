"""Compose the startup sound from scratch (no samples): writes app/assets/intro.wav.

Spacey and soft. Everything is built from sine tones, so there are no buzzy edges. A deep drone and distant air rise out
of silence, a reversed swell pulls towards the moment the arc finishes at 2.2 seconds, then a soft low impact and a wide
slow chord bloom in a very long, dark reverb, with a few glass tones drifting between the speakers. numpy only.
"""
import os
import wave

import numpy as np

SR = 44100
LEN = 6.4
HIT = 2.2  # seconds: when the arc finishes
t = np.arange(int(SR * LEN)) / SR
rng = np.random.default_rng(11)
# D with a raised fourth: open and weightless, neither happy nor sad
D2, A2, D3, A3, D4, E4, FS4, GS4, A4, CS5, E5, FS5, A5 = 73.42, 110.0, 146.83, 220.0, 293.66, 329.63, 369.99, 415.3, 440.0, 554.37, 659.26, 739.99, 880.0


def soft(freq, env, cents=0.0, rate=.13, phase=0.0):
    """One slowly drifting tone with only a touch of warmth above it."""
    drift = 2 ** ((cents + 4 * np.sin(2 * np.pi * rate * t + phase)) / 1200)
    p = 2 * np.pi * np.cumsum(freq * drift) / SR + phase
    return env * (np.sin(p) + .16 * np.sin(2 * p + .5) + .05 * np.sin(3 * p))


def wide(freq, env, level):
    """A note spread across the speakers by several slightly detuned copies."""
    l, r = np.zeros_like(t), np.zeros_like(t)
    for i, (cents, pan) in enumerate(((-7, .1), (-3, .75), (2, .25), (6, .9))):
        v = soft(freq, env, cents, rate=.09 + i * .03, phase=i * 1.3)
        l, r = l + v * (1 - pan), r + v * pan
    return level * l, level * r


def glass(freq, start, level):
    """A soft struck glass tone: a slow fade-in, a clean sine and one faint high partial."""
    x = np.clip(t - start, 0, None)
    on = (t >= start) * (1 - np.exp(-x / .025))
    return level * on * (np.exp(-x / 1.1) * np.sin(2 * np.pi * freq * x) + .12 * np.exp(-x / .3) * np.sin(2 * np.pi * freq * 2.01 * x))


def lowpass(x, hz):
    a = 1 - np.exp(-2 * np.pi * hz / SR)
    b = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(np.fft.rfft(x) / np.sqrt(1 + (b / hz) ** 4), len(x)) if a else x


def hall(x, seconds, seed, dark=2400):
    """A very long synthetic space: decaying noise, darkened, applied by FFT."""
    n = int(SR * seconds)
    ir = np.random.default_rng(seed).standard_normal(n) * np.exp(-np.arange(n) / SR / (seconds / 6))
    ir *= 1 - np.exp(-np.arange(n) / SR / .03)  # a soft onset, so it feels far away
    ir = lowpass(ir, dark)
    size = len(x) + n
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)]
    return wet / (np.abs(wet).max() + 1e-9)


# Rising out of silence: a deep drone and distant air
rise = np.clip(t / HIT, 0, 1) ** 1.6
fade = np.exp(-np.clip(t - HIT, 0, None) / 1.7)
left, right = np.zeros_like(t), np.zeros_like(t)
for f, level in ((D2, .34), (A2, .2), (D3, .12)):
    a, b = wide(f, rise * fade, level)
    left, right = left + a, right + b
air = [lowpass(rng.standard_normal(len(t)), 700) for _ in range(2)]
air = [x / np.abs(x).max() * .16 * (.25 + rise) * fade for x in air]
left, right = left + air[0], right + air[1]

# The bloom at the arc: a wide slow chord that opens over half a second
x = np.clip(t - HIT, 0, None)
bloom = (t >= HIT) * (1 - np.exp(-x / .28)) * np.exp(-x / 1.9)
for f, level in ((D3, .16), (A3, .15), (E4, .11), (FS4, .13), (GS4, .05), (A4, .1), (CS5, .06), (E5, .05), (A5, .025)):
    a, b = wide(f, bloom, level)
    left, right = left + a, right + b

# A soft low impact: felt more than heard
pitch = 34 + 28 * np.exp(-x / .09)
boom = (t >= HIT) * (1 - np.exp(-x / .006)) * np.exp(-x / .75) * np.sin(2 * np.pi * np.cumsum(pitch) / SR)
left, right = left + .5 * boom, right + .5 * boom

# Glass tones drifting between the speakers
glass_l = glass(FS5, HIT + .16, .1) + glass(CS5, HIT + 1.05, .07)
glass_r = glass(E5, HIT + .55, .09) + glass(A5, HIT + 1.5, .05)

# Everything washes through the long space, and the space carries most of it
wet_l = hall(left + glass_l + glass_r * .3, 5.5, 1)
wet_r = hall(right + glass_r + glass_l * .3, 5.5, 2)

# A reversed swell: a chord's reverb played backwards, ending exactly on the arc
hit = np.zeros_like(t)
for f, level in ((D4, 1), (FS4, .7), (A4, .7), (E5, .4)):
    hit += glass(f, .05, level)
tail = hall(hit, 4.0, 3, dark=3200)
length = int(SR * HIT)
reverse = tail[:length][::-1] * np.linspace(0, 1, length) ** 1.5
swell = np.zeros_like(t)
swell[:length] = reverse / np.abs(reverse).max()

dry = 1 / max(np.abs(left).max(), np.abs(right).max())
out_l = left * dry * .55 + glass_l * .9 + wet_l * .7 + swell * .4
out_r = right * dry * .55 + glass_r * .9 + wet_r * .7 + np.roll(swell, 90) * .4
end = np.clip((LEN - t) / 1.6, 0, 1) ** 1.6  # always reaches silence
stereo = np.stack([out_l * end, out_r * end], axis=1)
stereo = np.tanh(stereo / np.abs(stereo).max() * 1.1)
stereo *= 10 ** (-5 / 20) / np.abs(stereo).max()

path = os.path.join(os.path.dirname(__file__), "..", "app", "assets", "intro.wav")
with wave.open(path, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((stereo * 32767).astype("<i2").tobytes())
rms = lambda a, b: 20 * np.log10(np.sqrt(np.mean(stereo[int(a * SR):int(b * SR)] ** 2)) + 1e-9)
print("written", os.path.getsize(path) // 1024, "KB; level dB 0.5-2s", round(rms(.5, 2), 1), "| 2.2-4s", round(rms(2.2, 4), 1), "| 4-5.5s", round(rms(4, 5.5), 1), "| last 0.2s", round(rms(LEN - .2, LEN), 1))
