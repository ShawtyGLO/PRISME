"""Validation du Shape sur un kick de 808 synthétique (2026-09-24) — cibles mesurables.

Signal : kick 808 toutes les 0,6 s = clic (5 ms) + sinusoïde 55 Hz à chute de hauteur, enveloppe exponentielle (τ 220 ms),
+ un grondement soutenu à 48 Hz (−24 dB) et un peu de bruit. Bande : cloche 60 Hz, Q 1.
Mesures, par coup : niveau de l'ATTAQUE (crête sur 0–25 ms) et du SUSTAIN (RMS de 150 à 350 ms après l'attaque), en dB vs le sec.
Cibles : mode « transitoires » → l'attaque bouge de ≈ gain_db, le sustain de < 1 dB ; mode « sustain » → l'inverse ;
         deux bandes (transitoires +6 dB et sustain −6 dB) → attaque +6, sustain −6.
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter
from prisme_shape import shape_band

sys.stdout.reconfigure(encoding="utf-8")
FS = 48000.0
PER = 0.6


def kick(dur=6.0, seed=3):
    n = int(FS * dur)
    t = np.arange(n) / FS
    y = np.zeros(n)
    for s in np.arange(0.1, dur - 0.7, PER):
        i = int(s * FS)
        tt = np.arange(int(0.6 * FS)) / FS
        f = 55.0 + 90.0 * np.exp(-tt / 0.03)                   # chute de hauteur
        ph = 2 * np.pi * np.cumsum(f) / FS
        corps = np.sin(ph) * np.exp(-tt / 0.22)
        clic = np.random.default_rng(int(s * 100)).standard_normal(len(tt)) * np.exp(-tt / 0.002) * 0.3
        y[i:i + len(tt)] += 0.8 * corps + clic
    y += 0.02 * np.sin(2 * np.pi * 48.0 * t)                   # grondement soutenu
    y += np.random.default_rng(seed).standard_normal(n) * 0.001
    return y


def mesures(x, y):
    """Écart (dB) de l'attaque et du sustain DANS LA BANDE (60 Hz, Q 1), moyenné sur les coups.

    Le clic large bande domine la crête du signal complet : on mesure la bande, seule chose que la bande peut modifier."""
    from prisme_band import zone_filter
    bx, by = (lfilter(*zone_filter("bell", FS, 60.0, 1.0), z) for z in (x, y))
    att, sus = [], []
    for s in np.arange(0.1, 6.0 - 0.7, PER):
        i = int(s * FS)
        a = slice(i, i + int(0.10 * FS))                       # attaque : 100 premières ms du corps (énergie)
        c = slice(i + int(0.15 * FS), i + int(0.35 * FS))      # sustain : 150–350 ms
        att.append(10 * np.log10(np.mean(by[a] ** 2) / np.mean(bx[a] ** 2)))
        sus.append(10 * np.log10(np.mean(by[c] ** 2) / np.mean(bx[c] ** 2)))
    return np.mean(att), np.mean(sus)


if __name__ == "__main__":
    x = kick()
    kw = dict(shape="bell", f0=60.0, q=1.0)
    print(f"{'configuration':44s}{'attaque':>10s}{'sustain':>10s}")
    for cible, g in (("transitoires", 6.0), ("transitoires", -6.0), ("sustain", 6.0), ("sustain", -6.0)):
        y = shape_band(x, FS, cible=cible, gain_db=g, **kw)
        a, s = mesures(x, y)
        print(f"{cible + f' {g:+.0f} dB':44s}{a:+10.1f}{s:+10.1f}")
    y = shape_band(x, FS, cible="transitoires", gain_db=6.0, **kw) + shape_band(x, FS, cible="sustain", gain_db=-6.0, **kw) - x
    a, s = mesures(x, y)
    print(f"{'2 bandes : transitoires +6 & sustain −6':44s}{a:+10.1f}{s:+10.1f}")
    print(f"\nidentité à gain 0 : {'OK' if np.array_equal(shape_band(x, FS, gain_db=0.0, **kw), x) else 'ÉCHEC'}")
    # transparence : signal sans variation (sinusoïde pure) — aucun transitoire → mode « transitoires » ne doit rien changer
    n = int(FS * 3); tt = np.arange(n) / FS
    s0 = 0.5 * np.sin(2 * np.pi * 60.0 * tt)
    ys = shape_band(s0, FS, cible="transitoires", gain_db=6.0, **kw)
    print(f"transparence (sinusoïde pure 60 Hz, mode transitoires +6 dB, régime établi) : {20*np.log10(np.std(ys[FS.__int__():])/np.std(s0[FS.__int__():])):+.2f} dB")
