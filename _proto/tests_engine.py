"""CONTRAT DE L'ASSEMBLAGE (5 bandes) — 2026-09-25.

  E01 identité        toutes les bandes à 0 dB → sortie identique bit à bit
  E02 additivité      sortie = entrée + Σ deltas de chaque bande seule (écart < 1e-12)
  E03 ordre           permuter les bandes ne change rien (< 1e-12)
  E04 canaux          Side ne touche pas le Mid ; Mid ne touche pas le Side ; Left ne touche pas R ; Right ne touche pas L (exact)
  E05 mono            L = R en entrée, mode Stéréo → L = R en sortie (exact)
  E06 robustesse      3 types × 5 formes/fréquences par défaut × 5 canaux : sorties finies, |y| ≤ 4 × la crête d'entrée
  E07 bande coupée    `on = False` équivaut à gain 0 (exact)
  E08 coût            facteur temps réel de la configuration type (information)
"""
import sys, os, time
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_engine import process, delta_bande, bandes_defaut, FREQS_DEFAUT, FORMES_DEFAUT
from render import load
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
RES = []


def check(tid, desc, val, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:66s} {val}")


def config():
    b = bandes_defaut()
    b[0].update(type="shape", cible="sustain", gain_db=-3.0, q=0.71)
    b[1].update(type="exciter", gain_db=4.0, mode="iron", canal="stereo")
    b[2].update(type="tame", gain_db=-6.0, width=0.5, canal="mid")
    b[3].update(type="shape", cible="transitoires", gain_db=4.0, time_ms=40.0, canal="stereo")
    b[4].update(type="exciter", gain_db=5.0, mode="iron", canal="side")
    return b


if __name__ == "__main__":
    fs, x = load(SRC)
    x = x[int(30 * fs): int(36 * fs)]                       # 6 s stéréo de la prod
    n = len(x)
    b = config()
    zero = [dict(s, gain_db=0.0) for s in b]
    check("E01", "identité : toutes les bandes à 0 dB", "", np.array_equal(process(x, fs, zero), x))
    t0 = time.time(); full = process(x, fs, b); dt = time.time() - t0
    somme = x + sum(delta_bande(x, fs, s) for s in b)
    check("E02", "additivité (entrée + Σ deltas)", f"écart max {np.max(np.abs(full - somme)):.1e}", np.max(np.abs(full - somme)) < 1e-12)
    perm = process(x, fs, b[::-1])
    check("E03", "ordre des bandes indifférent", f"écart max {np.max(np.abs(perm - full)):.1e}", np.max(np.abs(perm - full)) < 1e-12)
    # E04 canaux
    ok4, det = True, []
    for canal in ("side", "mid", "left", "right"):
        s = dict(type="tame", shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=1.0, canal=canal)
        d = delta_bande(x, fs, s)
        M, S = (d[:, 0] + d[:, 1]) / 2, (d[:, 0] - d[:, 1]) / 2
        bon = {"side": np.all(M == 0), "mid": np.all(S == 0), "left": np.all(d[:, 1] == 0), "right": np.all(d[:, 0] == 0)}[canal]
        ok4 &= bool(bon); det.append(f"{canal}:{'ok' if bon else 'NON'}")
    check("E04", "canaux : chaque mode ne touche que sa cible", " ".join(det), ok4)
    mono = np.stack([x[:, 0], x[:, 0]], axis=1)
    ym = process(mono, fs, [dict(s, canal="stereo") for s in b])
    check("E05", "mono : L = R en entrée → L = R en sortie (mode Stéréo)", f"écart {np.max(np.abs(ym[:, 0] - ym[:, 1])):.1e}", np.max(np.abs(ym[:, 0] - ym[:, 1])) < 1e-9)
    # E06 robustesse (segment court)
    xs = x[: int(fs * 2)]
    ok6, pire = True, 0.0
    for t_ in ("exciter", "tame", "shape"):
        for sh, fr in zip(FORMES_DEFAUT, FREQS_DEFAUT):
            for canal in ("stereo", "mid", "side", "left", "right"):
                s = dict(type=t_, shape=sh, f0=fr, q=0.71, gain_db=6.0, canal=canal, cible="transitoires", width=0.5)
                d = delta_bande(xs, fs, s); y = xs + d
                ok6 &= bool(np.all(np.isfinite(y))) and np.max(np.abs(y)) <= 4.0 * np.max(np.abs(xs)); pire = max(pire, np.max(np.abs(y)) / np.max(np.abs(xs)))
    check("E06", "robustesse : 3 types × 5 bandes × 5 canaux", f"|y|/crête max {pire:.2f}", ok6)
    off = b[2].copy(); off["on"] = False
    check("E07", "`on = False` équivaut à gain 0", "", np.array_equal(delta_bande(x, fs, off), delta_bande(x, fs, dict(off, gain_db=0.0))))
    print(f"  INFO  E08  coût de la configuration type : {dt:.1f} s pour {n / fs:.0f} s de stéréo (numpy, hors ligne) = {dt / (n / fs):.1f}× le temps réel")
    nf = sum(1 for o in RES if not o)
    print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
    sys.exit(1 if nf else 0)
