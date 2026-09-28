"""CONTRAT DES FILTRES DE BANDE (phase compensée) — 2026-09-28.
  G01 identités   LR4 : LP² + HP² = passe-tout RBJ Q √½ ; LR2 : LP² − HP² = passe-tout ordre 1   (< 1e-10 ; arrondi des biquads à basse fréquence)
  G02 exactitude  bandes linéaires (cloches ±6/−9 dB) + filtres 12 et 24 dB/oct : |sortie| = |Π AP|·|1 + Σ m_i·(H_i − 1)| → effet réel = effet affiché (< 0,01 dB)
  G03 plusieurs   3 bandes filtrées qui se chevauchent : idem (< 0,01 dB)
  G04 neutre      aucun filtre actif → sortie = sec + Σ deltas exactement
  G05 niveau      passe-tout seul (bande à gain nul, filtre actif) : module plat (< 0,01 dB)
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, freqz
from prisme_dsp import rbj_peaking
from prisme_filtres import applique, rbj, bw1, ap1, etages
sys.stdout.reconfigure(encoding="utf-8")
RES = []
fs = 48000


def check(tid, desc, val, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:70s} {val}")


w = 2 * np.pi * np.geomspace(20, 20000, 500) / fs
H = lambda ba: freqz(*ba, worN=w)[1]
e4 = max(np.max(np.abs(H(rbj(fs, fc, "lp")) ** 2 + H(rbj(fs, fc, "hp")) ** 2 - H(rbj(fs, fc, "ap")))) for fc in (40.0, 1000.0, 15000.0))
e2 = max(np.max(np.abs(H(bw1(fs, fc, False)) ** 2 - H(bw1(fs, fc, True)) ** 2 - H(ap1(fs, fc)))) for fc in (40.0, 1000.0, 15000.0))
check("G01", "identités Linkwitz-Riley / passe-tout", f"LR4 {e4:.1e} ; LR2 {e2:.1e}", e4 < 1e-10 and e2 < 1e-10)

N = 1 << 16
imp = np.zeros((N, 2)); imp[0] = 1.0


def mesure(bandes, filtres):
    """bandes : {b: (f0, gain)} linéaires ; renvoie (réponse réelle en dB, attendue en dB) sur une grille de fréquences."""
    deltas = {b: lfilter(*rbj_peaking(fs, f0, g, 0.71), imp, axis=0) - imp for b, (f0, g) in bandes.items()}
    y = applique(imp, deltas, filtres, fs)[:, 0]
    Y = np.fft.rfft(y)
    fr = np.fft.rfftfreq(N, 1 / fs)
    m = (fr > 25) & (fr < 18000)
    z = np.exp(-1j * 2 * np.pi * fr[m] / fs)
    att = np.ones(m.sum(), dtype=complex)
    for b, (f0, g) in bandes.items():
        bb, aa = rbj_peaking(fs, f0, g, 0.71)
        Hb = (bb[0] + bb[1] * z + bb[2] * z * z) / (aa[0] + aa[1] * z + aa[2] * z * z)
        mm = np.ones(m.sum())
        for sp in filtres.get(b, []):
            if sp is None:
                continue
            et, sgn, apc = etages(fs, *sp)
            Hf = sgn * np.prod([(e[0][0] + e[0][1] * z + (e[0][2] if len(e[0]) > 2 else 0) * z * z) / (e[1][0] + e[1][1] * z + (e[1][2] if len(e[1]) > 2 else 0) * z * z) for e in et], axis=0)
            Ha = (apc[0][0] + apc[0][1] * z + (apc[0][2] if len(apc[0]) > 2 else 0) * z * z) / (apc[1][0] + apc[1][1] * z + (apc[1][2] if len(apc[1]) > 2 else 0) * z * z)
            mm = mm * (Hf / Ha).real
        att = att + mm * (Hb - 1.0)
    return 20 * np.log10(np.abs(Y[m])), 20 * np.log10(np.abs(att))


pire = 0.0
for g in (6.0, -9.0):
    for sp in ([("lc", 1000.0, 12), None], [("lc", 1000.0, 24), None], [None, ("hc", 1000.0, 12)], [None, ("hc", 1000.0, 24)], [("lc", 500.0, 24), ("hc", 3000.0, 12)]):
        r, a = mesure({0: (1000.0, g)}, {0: sp})
        pire = max(pire, np.max(np.abs(r - a)))
check("G02", "effet réel = effet affiché, une bande, 12 et 24 dB/oct", f"écart max {pire:.4f} dB", pire < 0.01)
r, a = mesure({0: (800.0, 6.0), 1: (1500.0, -9.0), 2: (3000.0, 4.0)}, {0: [("lc", 600.0, 24), None], 1: [None, ("hc", 2000.0, 12)], 2: [("lc", 2000.0, 12), ("hc", 6000.0, 24)]})
check("G03", "trois bandes filtrées qui se chevauchent", f"écart max {np.max(np.abs(r - a)):.4f} dB", np.max(np.abs(r - a)) < 0.01)
rng = np.random.default_rng(1)
x = rng.standard_normal((4000, 2)); d = {0: rng.standard_normal((4000, 2)) * 0.1, 3: rng.standard_normal((4000, 2)) * 0.1}
check("G04", "aucun filtre → sortie = sec + Σ deltas exactement", "", np.array_equal(applique(x, d, {}, fs), x + d[0] + d[3]))
r, _ = mesure({0: (1000.0, 0.0)}, {0: [("lc", 1000.0, 24), ("hc", 5000.0, 12)]})
check("G05", "passe-tout seul : module plat", f"écart max {np.max(np.abs(r)):.4f} dB", np.max(np.abs(r)) < 0.01)
nf = sum(1 for o in RES if not o)
print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
sys.exit(1 if nf else 0)
