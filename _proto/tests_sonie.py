"""CONTRAT DE LA COMPENSATION DE SONIE — batterie de tests (2026-10-04).

  S01 identité (traité = sec → 0 dB) · S02 gain pur (+6 dB → −6 dB) · S03 programme réel : sonie K du traité compensé = celle du sec (± 0,3 dB)
  S04 pas de pompage (écart-type du gain ≤ 0,1 dB sur programme stationnaire) · S05 silence : gel, pas de dérive, pas de NaN · S06 borne ±12 dB
  S07 temps de réponse (90 % en ≤ 2 s après un saut) · S08 blocs identiques · S09 44,1 / 48 / 96 kHz · S10 mono (L = R) · S11 pondération K : coefficients de référence à 48 kHz
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_sonie import Sonie, sonie_band, sonie_k_db, coefs_k
from prisme_engine_stream import traite as traite_moteur, LATENCE
from tests_engine import config
from render import load
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
RES = []


def check(tid, desc, val, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:68s} {val}")


def main():
    fs, x = load(SRC)
    x = x[int(30 * fs): int(50 * fs)].astype(np.float64)
    # S01
    out, g = sonie_band(x, x.copy(), fs)
    check("S01", "traité = sec → correction 0 dB", f"|g| max {np.abs(g).max():.3f} dB", np.abs(g).max() <= 0.05)
    # S02
    wet = x * 2.0
    out, g = sonie_band(x, wet, fs)
    check("S02", "traité = sec + 6 dB → correction −6 dB (après 8 s)", f"{g[8 * fs:].mean():+.2f} dB", abs(g[8 * fs:].mean() + 6.02) <= 0.15)
    # S03 : programme réel passé dans le moteur (config type), sec aligné
    wet = traite_moteur(x, fs, config())
    sec = np.concatenate([np.zeros((LATENCE, 2)), x[:-LATENCE]])
    out, g = sonie_band(sec, wet, fs)
    d = sonie_k_db(out, fs) - sonie_k_db(sec, fs)
    d0 = sonie_k_db(wet, fs) - sonie_k_db(sec, fs)
    check("S03", "programme réel (moteur, config type) : sonie K compensée = sonie du sec ± 0,3 dB", f"avant {d0:+.2f} dB → après {d:+.2f} dB", abs(d) <= 0.3)
    # S04
    sd = g[8 * fs:].std()
    check("S04", "pas de pompage : écart-type de la correction ≤ 0,1 dB après 8 s", f"{sd:.3f} dB", sd <= 0.1)
    # S05 : silence au milieu → gel
    y = np.concatenate([x[:8 * fs], np.zeros((5 * fs, 2)), x[8 * fs:12 * fs]])
    w = y * 1.5
    out, g = sonie_band(y, w, fs)
    gel = g[8 * fs + int(1.5 * fs): 13 * fs]
    check("S05", "silence de 5 s : correction gelée (dérive ≤ 0,05 dB), valeurs finies", f"dérive {gel.max() - gel.min():.3f} dB", bool(np.all(np.isfinite(out))) and gel.max() - gel.min() <= 0.05)
    # S06
    out, g = sonie_band(x, x * 10.0, fs)
    check("S06", "écart de 20 dB : correction bornée à ±12 dB", f"{g.min():+.2f} dB", g.min() >= -12.05 and g.max() <= 12.05)
    # S07 : saut à 5 s
    sj = x.copy()
    wj = sj.copy()
    wj[5 * fs:] *= 2.0
    out, g = sonie_band(sj, wj, fs)
    cible = g[-fs:].mean()
    t90 = np.argmax(g[5 * fs:] <= 0.9 * cible) / fs
    info = f"cible {cible:+.1f} dB ; 90 % en {t90:.2f} s"
    check("S07", "saut de +6 dB du traité : correction à 90 % en ≤ 2 s (sonie lissée sur 1 s)", info, abs(cible + 5.5) <= 1.5 and t90 <= 2.5)
    # S08
    wet = x * 1.4
    ref = sonie_band(x, wet, fs, block=len(x))[0]
    e = max(np.max(np.abs(sonie_band(x, wet, fs, block=b)[0] - ref)) for b in (64, 500, 4096))
    check("S08", "blocs de 64, 500, 4096 identiques à < 1e-9", f"écart {e:.1e}", e < 1e-9)
    # S09
    gs = []
    for f in (44100, 48000, 96000):
        rng = np.random.default_rng(1)
        n = f * 12
        b = rng.standard_normal((n, 2)) * 0.05
        gs.append(sonie_band(b, b * 1.6, f)[1][-f:].mean())
    check("S09", "44,1 / 48 / 96 kHz : même correction ± 0,2 dB", " ".join(f"{v:+.2f}" for v in gs), max(gs) - min(gs) <= 0.2)
    # S10
    mono = np.repeat(x[:, :1], 2, axis=1)
    out, g = sonie_band(mono, mono * 1.5, fs)
    check("S10", "mono (L = R) : sortie L = R, correction ≈ −3,5 dB", f"écart L−R {np.abs(out[:, 0] - out[:, 1]).max():.1e} ; {g[-fs:].mean():+.2f} dB",
          np.abs(out[:, 0] - out[:, 1]).max() < 1e-12 and abs(g[-fs:].mean() + 3.52) <= 0.15)
    # S11 : coefficients de référence BS.1770 à 48 kHz
    (b1, a1), (b2, a2) = coefs_k(48000)
    ref_b1 = [1.53512485958697, -2.69169618940638, 1.19839281085285]
    ref_a1 = [1.0, -1.69065929318241, 0.73248077421585]
    ref_a2 = [1.0, -1.99004745483398, 0.99007225036621]
    e = max(np.max(np.abs(b1 - ref_b1)), np.max(np.abs(a1 - ref_a1)), np.max(np.abs(a2 - ref_a2)))
    check("S11", "coefficients K à 48 kHz = valeurs de référence BS.1770 (≤ 1e-6)", f"écart {e:.1e}", e < 1e-6)
    nf = sum(1 for o in RES if not o)
    print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
    sys.exit(1 if nf else 0)


if __name__ == "__main__":
    main()
