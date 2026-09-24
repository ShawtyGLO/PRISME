"""Banc d'étape 1 : effet localisé ? source Auto / Bande / Large, 5 modes, adaptatif ou non.

Signal de test synthétique « voix sombre » : dent de scie 180 Hz passe-bas ~5 kHz + souffle léger,
crête 0,3 sur 0–2,5 s puis 0,03 sur 2,5–5 s (−20 dB) pour voir la dépendance au niveau.
Zone d'air = une octave centrée sur f0 (f0/√2 .. f0·√2).
"""
import os, sys
import numpy as np
from scipy.signal import lfilter, welch, sawtooth
from scipy.io import wavfile
from prisme_band import excite_band
from prisme_dsp import MODES

sys.stdout.reconfigure(encoding="utf-8")
FS = 44100.0
DRIVE = 1.5      # niveau cible à l'entrée de la courbe (adaptatif)


def voice(fs=FS, dur=5.0, seed=1):
    n = int(fs * dur)
    t = np.arange(n) / fs
    f = 180 * (1 + 0.03 * np.sin(2 * np.pi * 4.5 * t))
    ph = 2 * np.pi * np.cumsum(f) / fs
    x = sawtooth(ph)
    for _ in range(2):                       # LP 5 kHz, 2 passes
        from prisme_band import rbj_lowpass
        x = lfilter(*rbj_lowpass(fs, 5000.0), x)
    rng = np.random.default_rng(seed)
    x = x / np.max(np.abs(x)) * 0.3 + rng.normal(0, 0.003, n)
    x[int(2.5 * fs):] *= 0.1
    return x


def zone_db(a, b, fs, lo, hi):
    f, Pa = welch(a, fs, nperseg=4096)
    _, Pb = welch(b, fs, nperseg=4096)
    m = (f >= lo) & (f <= hi)
    return 10 * np.log10(Pb[m].sum() / Pa[m].sum())


def zone_stats(x, out, fs, lo, hi):
    """(gain net, niveau ajouté, corrélation) dans la zone — l'interférence est séparée du niveau."""
    from scipy.signal import butter, sosfiltfilt
    sos = butter(4, [lo, hi], btype="band", fs=fs, output="sos")
    xb = sosfiltfilt(sos, x)
    db = sosfiltfilt(sos, out - x)
    px, pd = np.sum(xb ** 2) + 1e-30, np.sum(db ** 2) + 1e-30
    return (10 * np.log10(np.sum((xb + db) ** 2) / px), 10 * np.log10(pd / px),
            float(np.sum(xb * db) / np.sqrt(px * pd)))


def localisation(x, out, fs, lo, hi):
    d = out - x
    f, Pd = welch(d, fs, nperseg=4096)
    m = (f >= lo) & (f <= hi)
    return 100 * Pd[m].sum() / Pd.sum()


def run(f0=12000.0, q=2.0, gain_db=6.0):
    x = voice()
    lo, hi = f0 / np.sqrt(2), f0 * np.sqrt(2)
    print(f"Bande cloche {f0:.0f} Hz, Q {q}, +{gain_db} dB, zone {lo:.0f}–{hi:.0f} Hz, drive adaptatif {DRIVE}, De-Emphasis (projection), ADAA×2")
    print(f"{'mode':8s}{'source':8s}{'naturel':>9s}{'normalisé':>11s}{'% dans zone':>13s}{'0,1–3 kHz':>11s}   (gain zone en dB, réf. entrée)")
    for mode in MODES:
        for src in ("auto", "band", "large"):
            kw = dict(f0=f0, q=q, gain_db=gain_db, mode=mode, source=src, drive=DRIVE, oversample=2)
            o1 = excite_band(x, FS, **kw)
            o2 = excite_band(x, FS, norm="zone", **kw)
            print(f"{mode:8s}{src:8s}{zone_db(x, o1, FS, lo, hi):9.1f}{zone_db(x, o2, FS, lo, hi):11.1f}"
                  f"{localisation(x, o2, FS, lo, hi):12.0f}%{zone_db(x, o2, FS, 100, 3000):11.2f}")


def run_level(f0=12000.0):
    x = voice()
    lo, hi = f0 / np.sqrt(2), f0 * np.sqrt(2)
    n1 = int(2.5 * FS)
    print("\nDépendance au niveau (Iron, source auto) : gain de la zone d'air, segment fort puis segment −20 dB")
    for adaptive in (False, True):
        out = excite_band(x, FS, f0=f0, mode="iron", source="auto", drive=DRIVE, adaptive=adaptive, oversample=2, norm="zone")
        print(f"  adaptatif={adaptive!s:5s}  fort {zone_db(x[:n1], out[:n1], FS, lo, hi):6.1f} dB   faible {zone_db(x[n1:], out[n1:], FS, lo, hi):6.1f} dB")


def renders(f0=12000.0):
    os.makedirs("renders", exist_ok=True)
    x = voice()
    wavfile.write("renders/00_dry.wav", int(FS), x.astype(np.float32))
    for mode in ("iron", "rect"):
        for src in ("auto", "band", "large"):
            out = excite_band(x, FS, f0=f0, mode=mode, source=src, gain_db=6.0, drive=DRIVE, oversample=2, norm="zone")
            wavfile.write(f"renders/{mode}_{src}.wav", int(FS), out.astype(np.float32))
    print("\nRendus écrits dans _proto/renders/ (signal synthétique — à refaire sur une vraie voix)")


if __name__ == "__main__":
    run()
    run_level()
    renders()
