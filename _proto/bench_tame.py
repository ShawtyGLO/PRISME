"""Validation du Tame (moteur temporel) — cibles mesurables, sans écoute (2026-09-24).

Signal de test : bruit rose (−26 dBFS RMS) + 3 sinusoïdes soutenues (1,7 / 3,1 / 5,3 kHz) + une résonance qui sonne (2,4 kHz, Q 40,
excitée toutes les 0,5 s), chacune ≈ +10 dB au-dessus de la puissance du bruit dans une bande de 1/6 d'octave.
Zone : cloche 3 kHz, Q 0,7 (≈ 1,4–6,4 kHz), profondeur −9 dB.

Cibles :  T1 supprimer chaque résonance sans toucher aux voisines ;  T2 transparence sur bruit sans résonance ;
          T3 indépendance au niveau ;  T4 bipolaire (réhausser) ;  T5 identité à gain 0 ;  T6 largeur (fin = étroit, large = étalé).
"""
import sys, os, time
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, welch
from prisme_dsp import rbj_bandpass0db
from prisme_tame import tame_band

sys.stdout.reconfigure(encoding="utf-8")
FS = 48000.0
RES = [1700.0, 3100.0, 5300.0]
RING = 2400.0


def bruit_rose(n, seed=1, rms=0.05):
    w = np.random.default_rng(seed).standard_normal(n)
    W = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1 / FS)
    W[1:] /= np.sqrt(f[1:])
    W[0] = 0
    y = np.fft.irfft(W, n)
    return y * rms / np.std(y)


def signal(dur=8.0, avec_res=True, seed=1):
    n = int(FS * dur)
    t = np.arange(n) / FS
    b = bruit_rose(n, seed)
    if not avec_res:
        return b
    y = b.copy()
    for f in RES:
        brms = np.std(lfilter(*rbj_bandpass0db(FS, f, 8.6), b))              # bande de 1/6 d'octave
        y += np.sqrt(2) * brms * 10 ** (10 / 20) * np.sin(2 * np.pi * f * t)
    imp = np.zeros(n)
    imp[:: int(0.5 * FS)] = 1.0
    ring = lfilter(*rbj_bandpass0db(FS, RING, 40.0), imp)
    brms = np.std(lfilter(*rbj_bandpass0db(FS, RING, 8.6), b))
    y += ring * (brms * 10 ** (10 / 20) / (np.std(ring) + 1e-12)) * 2.5
    return y


def psd(x):
    return welch(x, FS, nperseg=16384, noverlap=8192)


def pic_db(x, f, larg=30.0):
    fr, P = psd(x)
    k = (fr > f - larg) & (fr < f + larg)
    return 10 * np.log10(P[k].max())


def bandes_tiers(x, centres):
    fr, P = psd(x)
    out = []
    for c in centres:
        k = (fr >= c / 2 ** (1 / 6)) & (fr < c * 2 ** (1 / 6))
        out.append(10 * np.log10(P[k].sum()))
    return np.array(out)


CENTRES = 1000 * 2.0 ** (np.arange(-6, 11) / 3)                    # ≈ 250 Hz … 10 kHz par tiers d'octave
def hors_resonances(c):
    return all(abs(np.log2(c / f)) > 0.2 for f in RES + [RING])


def rapport(x, y, zone=(1400.0, 6400.0)):
    d = bandes_tiers(y, CENTRES) - bandes_tiers(x, CENTRES)
    ok = np.array([hors_resonances(c) for c in CENTRES])
    dans = np.array([zone[0] <= c <= zone[1] for c in CENTRES])
    return (np.mean(np.abs(d[ok & dans])), np.max(np.abs(d[ok & dans])), np.mean(np.abs(d[ok & ~dans])))


def largeur_creux(x, y, f, seuil=1.5):
    """Largeur (octaves) de la zone autour de f où le niveau du bruit baisse de plus de `seuil` dB (hors la raie elle-même)."""
    fr, Px = psd(x)
    _, Py = psd(y)
    g = 10 * np.log10(Py / Px)
    hors = np.abs(fr - f) > 20
    g_lisse = g.copy()
    lis = np.convolve(np.where(hors, g, np.nan), np.ones(9) / 9, mode="same")
    k = np.argmin(np.abs(fr - f))
    lo = k
    while lo > 0 and (np.isnan(lis[lo]) or lis[lo] < -seuil):
        lo -= 1
    hi = k
    while hi < len(fr) - 1 and (np.isnan(lis[hi]) or lis[hi] < -seuil):
        hi += 1
    return np.log2(fr[hi] / fr[lo])


if __name__ == "__main__":
    x = signal()
    kw = dict(shape="bell", f0=3000.0, q=0.7)
    print("T1/T6 — supprimer les résonances (−9 dB), selon la largeur de traitement\n")
    print(f"{'largeur':>9s}{'1,7k':>8s}{'2,4k':>8s}{'3,1k':>8s}{'5,3k':>8s}{'  collatéral zone (moy/max)':>30s}{'hors zone':>11s}{'creux 3,1k':>12s}{'temps':>8s}")
    for wd in (0.0, 0.5, 1.0):
        t0 = time.time()
        y = tame_band(x, FS, gain_db=-9.0, width=wd, **kw)
        dt = time.time() - t0
        red = [pic_db(y, f) - pic_db(x, f) for f in (1700.0, 2400.0, 3100.0, 5300.0)]
        mo, mx, hz = rapport(x, y)
        print(f"{wd:9.1f}" + "".join(f"{r:+8.1f}" for r in red) + f"{mo:20.2f}/{mx:5.2f} dB{hz:9.2f} dB{largeur_creux(x, y, 3100.0):9.2f} oct{dt:7.1f}s")
    print("\nT2 — transparence : bruit rose SANS résonance (écart moyen par tiers d'octave, dB)")
    xn = signal(avec_res=False)
    for wd in (0.0, 0.5, 1.0):
        yn = tame_band(xn, FS, gain_db=-9.0, width=wd, **kw)
        d = bandes_tiers(yn, CENTRES) - bandes_tiers(xn, CENTRES)
        print(f"   largeur {wd:.1f} : |Δ| moyen {np.mean(np.abs(d)):.2f} dB, max {np.max(np.abs(d)):.2f} dB")
    print("\nT3 — indépendance au niveau (largeur 0,5) : réduction à 3,1 kHz selon le niveau d'entrée")
    for db in (-12, 0, 6):
        xs = x * 10 ** (db / 20)
        ys = tame_band(xs, FS, gain_db=-9.0, width=0.5, **kw)
        print(f"   entrée {db:+3d} dB : {pic_db(ys, 3100.0) - pic_db(xs, 3100.0):+.1f} dB")
    print("\nT4 — bipolaire : +9 dB réhausse les résonances (largeur 0,5)")
    yb = tame_band(x, FS, gain_db=+9.0, width=0.5, **kw)
    print("   " + "  ".join(f"{f/1000:.1f}k {pic_db(yb, f) - pic_db(x, f):+.1f}" for f in (1700.0, 2400.0, 3100.0, 5300.0)) + " dB ; collatéral zone (moy/max) %.2f/%.2f dB" % rapport(x, yb)[:2])
    print("\nT6b — bosse LARGE (bruit filtré 2 kHz, ~0,7 octave, +8 dB) : le mode large doit agir, le mode fin non")
    n = len(x)
    xb = signal(avec_res=False)
    bosse = lfilter(*rbj_bandpass0db(FS, 2000.0, 2.0), bruit_rose(n, seed=7))
    brms = np.std(lfilter(*rbj_bandpass0db(FS, 2000.0, 2.0), xb))
    xb = xb + bosse * (brms * 10 ** (8 / 20) / np.std(bosse)) * 0.9
    k2 = int(np.argmin(np.abs(CENTRES - 2000.0)))
    aut = [i for i in range(len(CENTRES)) if abs(np.log2(CENTRES[i] / 2000.0)) > 0.4 and 1400 <= CENTRES[i] <= 6400]
    for wd in (0.0, 0.5, 1.0):
        yb2 = tame_band(xb, FS, gain_db=-9.0, width=wd, **kw)
        d = bandes_tiers(yb2, CENTRES) - bandes_tiers(xb, CENTRES)
        print(f"   largeur {wd:.1f} : à 2 kHz {d[k2]:+.1f} dB ; autres tiers d'octave de la zone (|Δ| moy) {np.mean(np.abs(d[aut])):.2f} dB")
    print("\nT5 — identité à gain 0 :", "OK" if np.array_equal(tame_band(x, FS, gain_db=0.0, **kw), x) else "ÉCHEC")
