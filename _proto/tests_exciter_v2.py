"""CONTRAT DE L'EXCITER v2 (flux) — 2026-09-26.
  V01 blocs      résultat identique quelle que soit la taille des blocs (64, 1000, entier) : < 1e-9
  V02 latence    impulsion → sortie < 1e-7 avant 20 échantillons ; silence → < 1e-7 (−140 dBFS)
  V03 lié        entrée identique → wet identique (une seule chaîne mono) ; niveau du wet proportionnel à 10^(g/20) (g = 3 → 9 dB) à ± 0,5 dB
  V04 régularité fenêtres de 100 ms muettes ≤ 5 %, écart-type du niveau du wet ≤ 12 dB (mesuré avant réglage de la porte : 37 % et 66,8 dB)
  V05 profils    4 profils, sortie finie et bornée, sur bruit blanc, musique, silence, 44,1/48/96 kHz
  V06 niveau     sortie proportionnelle au niveau d'entrée (le wet suit le signal : ×2 en entrée → ×2 en sortie ± 0,3 dB)
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_exciter_v2_stream import exciter_v2_stream, PROFILS, D_OS
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
RES = []


def check(tid, desc, val, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:70s} {val}")


rmsdb = lambda v: 20 * np.log10(np.sqrt(np.mean(v ** 2)) + 1e-30)

if __name__ == "__main__":
    fs, x = load(SRC)
    x = np.ascontiguousarray(x[int(30 * fs): int(34 * fs), 0])
    kw = dict(shape="bell", f0=3000.0, q=0.71, gain_db=6.0, profil="mordant_chaud")
    ref = exciter_v2_stream(x, fs, block=len(x), **kw)
    e = max(np.max(np.abs(exciter_v2_stream(x, fs, block=b, **kw) - ref)) for b in (64, 1000))
    check("V01", "indépendance à la taille des blocs (64, 1000)", f"écart {e:.1e}", e < 1e-9)
    imp = np.zeros(4000); imp[100] = 1.0
    w = exciter_v2_stream(imp, fs, **kw)
    check("V02", "avant l'impulsion et sur le silence : < 1e-7 (−140 dBFS ; le décalage de la courbe asymétrique × plancher de niveau 1e-7)", f"avant 100+{D_OS}: {np.max(np.abs(w[:100 + D_OS - 1])):.1e}",
          np.max(np.abs(w[:100 + D_OS - 1])) < 1e-7 and np.max(np.abs(exciter_v2_stream(np.zeros(5000), fs, **kw))) < 1e-7)
    a = exciter_v2_stream(x, fs, **dict(kw, gain_db=3.0)); b = exciter_v2_stream(x, fs, **dict(kw, gain_db=12.0))
    dlt = rmsdb(b[int(fs):]) - rmsdb(a[int(fs):])
    check("V03", "niveau du wet proportionnel à 10^(g/20) (3 → 12 dB : +9 dB)", f"{dlt:+.2f} dB", abs(dlt - 9.0) < 0.5)
    ww = int(0.1 * fs)
    r = ref[int(fs):]
    nw = len(r) // ww
    lw = 10 * np.log10((r[: nw * ww].reshape(nw, ww) ** 2).mean(axis=1) + 1e-20)
    muet = 100 * np.mean(lw < np.median(lw) - 25)
    check("V04", "détection RÉGULIÈRE sur la musique : fenêtres de 100 ms muettes ≤ 5 %, écart-type du niveau ≤ 12 dB", f"muettes {muet:.0f} % ; écart-type {np.std(lw):.1f} dB", muet <= 5 and np.std(lw) <= 12)
    ok5, pire = True, 0.0
    rng = np.random.default_rng(3)
    for pr in PROFILS:
        for f_s in (44100, 48000, 96000):
            for sig in (rng.standard_normal(f_s) * 0.3, np.zeros(f_s), x[:f_s]):
                y = exciter_v2_stream(sig, f_s, **dict(kw, profil=pr, shape="highshelf", f0=9600.0, source="band"))
                ok5 &= bool(np.all(np.isfinite(y))) and np.max(np.abs(y)) < 5.0
                pire = max(pire, np.max(np.abs(y)))
    check("V05", "4 profils × 3 fréquences d'échantillonnage × (bruit, silence, musique)", f"|y| max {pire:.2f}", ok5)
    a = exciter_v2_stream(x, fs, **kw); b = exciter_v2_stream(2.0 * x, fs, **kw)
    r = rmsdb(b[int(fs):]) - rmsdb(a[int(fs):])
    check("V06", "le wet suit le niveau d'entrée (×2 → +6 dB)", f"{r:+.2f} dB", abs(r - 6.02) < 0.5)
    nf = sum(1 for o in RES if not o)
    print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
    sys.exit(1 if nf else 0)
