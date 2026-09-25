"""CONTRAT DE L'ASSEMBLAGE EN FLUX — 2026-09-25.

  F01 équivalence     le flux (retardé de la latence) reproduit l'assemblage hors ligne `prisme_engine.process` : écart relatif < 1e-9
  F02 blocs           résultat identique pour des blocs de 64, 500, 4096, entier : < 1e-9
  F03 latence         toutes les bandes à 0 dB → sortie = entrée retardée de 20 échantillons, EXACTEMENT ; latence constante (avec ou sans Exciter)
  F04 canaux          en flux aussi : Side ne touche pas le Mid, Mid ne touche pas le Side, Left ne touche pas R, Right ne touche pas L (< 1e-12 : la sortie moins l'entrée retardée laisse un arrondi)
  F05 mono            L = R en entrée, mode Stéréo → L = R en sortie
  F06 coût            facteur temps réel de la configuration type (information)
"""
import sys, os, time
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_engine import process
from prisme_engine_stream import EngineStream, traite, LATENCE
from tests_engine import config
from render import load
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
RES = []


def check(tid, desc, val, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:66s} {val}")


if __name__ == "__main__":
    fs, x = load(SRC)
    x = x[int(30 * fs): int(35 * fs)]
    n, D = len(x), LATENCE
    b = config()
    t0 = time.time(); flux = traite(x, fs, b); dt = time.time() - t0
    hors = process(x, fs, b)
    e = np.max(np.abs(flux[D:] - hors[:n - D])) / np.max(np.abs(hors))
    check("F01", "équivalence avec l'assemblage hors ligne (config type, 5 bandes)", f"écart relatif max {e:.1e}", e < 1e-9)
    ecarts = {bl: np.max(np.abs(traite(x, fs, b, block=bl) - flux)) for bl in (64, 500, 4096)}
    check("F02", "indépendance à la taille des blocs (64, 500, 4096)", " ".join(f"{k}:{v:.0e}" for k, v in ecarts.items()), max(ecarts.values()) < 1e-9)
    zero = [dict(s, gain_db=0.0) for s in b]
    y0 = traite(x, fs, zero)
    sans_exc = [dict(s) for s in b if s["type"] != "exciter"]
    ok3 = np.array_equal(y0[D:], x[:n - D]) and np.all(y0[:D] == 0) and EngineStream(fs, b).latence == EngineStream(fs, sans_exc).latence == D
    check("F03", "gains à 0 dB : sortie = entrée retardée de 20 échantillons, exactement", f"latence {D} échantillons ({D / fs * 1000:.2f} ms), constante", ok3)
    ok4, det = True, []
    for canal in ("side", "mid", "left", "right"):
        for typ in ("tame", "exciter"):
            s = dict(type=typ, shape="bell", f0=3000.0, q=0.7, gain_db=-9.0 if typ == "tame" else 6.0, width=1.0, canal=canal)
            d = traite(x, fs, [s]) - np.concatenate([np.zeros((D, 2)), x[:n - D]])
            M, S = (d[:, 0] + d[:, 1]) / 2, (d[:, 0] - d[:, 1]) / 2
            bon = {"side": np.max(np.abs(M)) < 1e-12, "mid": np.max(np.abs(S)) < 1e-12, "left": np.max(np.abs(d[:, 1])) < 1e-12, "right": np.max(np.abs(d[:, 0])) < 1e-12}[canal]
            ok4 &= bool(bon); det.append(f"{canal}/{typ}:{'ok' if bon else 'NON'}")
    check("F04", "canaux en flux : chaque mode ne touche que sa cible", " ".join(det), ok4)
    mono = np.stack([x[:, 0], x[:, 0]], axis=1)
    ym = traite(mono, fs, [dict(s, canal="stereo") for s in b])
    check("F05", "mono : L = R en entrée → L = R en sortie (mode Stéréo)", f"écart {np.max(np.abs(ym[:, 0] - ym[:, 1])):.1e}", np.max(np.abs(ym[:, 0] - ym[:, 1])) < 1e-9)
    bl = b + [dict(type="lift", shape="bell", f0=2000.0, q=0.7, gain_db=9.0, canal="stereo", amount=70.0)]
    fl = traite(x, fs, bl); hl = process(x, fs, bl)
    e7 = np.max(np.abs(fl[D:] - hl[:n - D])) / np.max(np.abs(hl))
    check("F07", "avec une bande Lift : équivalence flux / hors ligne, blocs, mono", f"écart {e7:.1e}", e7 < 1e-9 and np.max(np.abs(traite(x, fs, bl, block=500) - fl)) < 1e-9)
    print(f"  INFO  F06  coût : {dt:.1f} s pour {n / fs:.0f} s de stéréo = {dt / (n / fs):.2f}× le temps réel (numpy, blocs de 8192)")
    nf = sum(1 for o in RES if not o)
    print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
    sys.exit(1 if nf else 0)
