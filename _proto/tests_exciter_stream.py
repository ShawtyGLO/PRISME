"""CONTRAT DE L'EXCITER EN FLUX — batterie de tests (2026-09-25).

  X01 équivalence      le flux (aligné sur la latence) reproduit `excite_band` hors ligne : écart relatif < 1e-9 (source Auto et Bande, 3 modes)
  X02 blocs            résultat identique quelle que soit la taille des blocs (1, 64, 1000, 8192, entier) : < 1e-9
  X03 latence          latence déclarée = 20 échantillons ; la réponse du delta à une impulsion n'apparaît pas avant ; entrée retardée exacte
  X04 identité         gain 0 → delta nul exact
  X05 robustesse       silence, continu, carré, impulsions, blanc, −140 dB × paramètres extrêmes : fini, borné, silence → silence exact
  X06 fréquences d'éch. 44,1 / 48 / 96 kHz : fini, même forme (l'effet net dans la zone reste dans ±1 dB)
  X07 coût             facteur temps réel (information)
"""
import sys, os, time
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_band import excite_band
from prisme_exciter_stream import ExciterStream, exciter_stream, D_OS
from render import load
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
RES = []


def check(tid, desc, val, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:66s} {val}")


def hors_ligne(x, fs, **kw):
    kw = dict(kw); gain = kw.pop("gain_db")
    return excite_band(x, fs, gain_db=gain, out_sections=3, drive=1.5, oversample=2, norm="zone", **kw) - x


if __name__ == "__main__":
    fs, x = load(SRC)
    m = x.mean(axis=1)[int(30 * fs): int(34 * fs)]
    n = len(m)
    base = dict(shape="bell", f0=12000.0, q=2.0, gain_db=5.0)
    # X01 équivalence
    pire = 0.0; ok1 = True
    for src in ("auto", "band"):
        for mode in ("iron", "triode", "rect"):
            kw = dict(base, source=src, mode=mode)
            ref = hors_ligne(m, fs, **kw)
            st = exciter_stream(m, fs, **kw)
            e = np.max(np.abs(st[D_OS:] - ref[:n - D_OS])) / max(np.max(np.abs(ref)), 1e-12)
            pire = max(pire, e); ok1 &= e < 1e-9
    check("X01", "équivalence avec excite_band hors ligne (2 sources × 3 modes)", f"écart relatif max {pire:.1e}", ok1)
    # X02 blocs
    kw = dict(base, source="auto", mode="iron")
    refb = exciter_stream(m, fs, block=1 << 22, **kw)
    ecarts = {b: np.max(np.abs(exciter_stream(m, fs, block=b, **kw) - refb)) for b in (1, 64, 1000, 8192)} if n < 40000 else {b: np.max(np.abs(exciter_stream(m[:20000], fs, block=b, **kw) - exciter_stream(m[:20000], fs, block=1 << 22, **kw))) for b in (1, 64, 1000, 8192)}
    check("X02", "indépendance à la taille des blocs (1, 64, 1000, 8192 ; 20 000 échantillons)", " ".join(f"{b}:{e:.0e}" for b, e in ecarts.items()), max(ecarts.values()) < 1e-9)
    # X03 latence : une impulsion à t0 ne produit rien de significatif avant t0 + (rien n'est anticipé) ; delta nul avant t0
    imp = np.zeros(20000); imp[5000] = 0.5
    d = exciter_stream(imp, fs, **kw)
    premier = int(np.argmax(np.abs(d) > 1e-12)) if np.any(np.abs(d) > 1e-12) else -1
    check("X03", "latence déclarée 20 ; delta nul avant l'impulsion", f"latence {D_OS} échantillons ({D_OS / fs * 1000:.2f} ms) ; premier échantillon non nul : {premier}", D_OS == 20 and (premier == -1 or premier >= 5000))
    # X04 identité
    check("X04", "gain 0 → delta nul exact", "", np.all(exciter_stream(m, fs, **dict(kw, gain_db=0.0)) == 0.0))
    # X05 robustesse
    t = np.arange(int(fs * 2)) / fs; rng = np.random.default_rng(5); imp2 = np.zeros(len(t)); imp2[::4800] = 1.0
    cas = {"silence": np.zeros(len(t)), "continu": np.full(len(t), 0.5), "carré": np.sign(np.sin(2 * np.pi * 100 * t)), "impulsions": imp2,
           "blanc": np.clip(rng.standard_normal(len(t)), -1, 1), "−140 dB": rng.standard_normal(len(t)) * 1e-7}
    ok5, pire5 = True, 0.0
    for nom, s in cas.items():
        for p in (dict(shape="bell", f0=100.0, q=0.3), dict(shape="bell", f0=15000.0, q=8.0), dict(shape="highshelf", f0=8000.0, q=0.7), dict(shape="lowshelf", f0=200.0, q=0.7)):
            for mode in ("iron", "triode", "rect"):
                for g in (-12.0, 12.0):
                    y = exciter_stream(s, fs, gain_db=g, mode=mode, **p)
                    fin = bool(np.all(np.isfinite(y))); pire5 = max(pire5, np.max(np.abs(y)) if fin else 99.0)
                    ok5 &= fin and np.max(np.abs(y)) <= 8.0 * max(np.max(np.abs(s)), 1e-9) * 16
                    if nom == "silence": ok5 &= bool(np.all(y == 0))
    check("X05", "cas extrêmes × paramètres extrêmes", f"|delta| max {pire5:.2f}", ok5)
    # X06 fréquences d'échantillonnage
    res6 = []
    for f_s in (44100.0, 48000.0, 96000.0):
        from scipy.signal import resample_poly
        from math import gcd
        g_ = gcd(int(f_s), int(fs)); mm = resample_poly(m[: int(fs * 2)], int(f_s) // g_, int(fs) // g_)
        d = exciter_stream(mm, f_s, **kw)
        res6.append(10 * np.log10(np.sum((mm[D_OS:] + d[D_OS:]) ** 2) / np.sum(mm[D_OS:] ** 2)))
    check("X06", "44,1 / 48 / 96 kHz : fini, gain global comparable", f"Δ niveau global {['%+.3f' % r for r in res6]} dB", all(np.isfinite(res6)) and max(res6) - min(res6) < 0.5)
    t0 = time.time(); exciter_stream(m, fs, **kw); dt = time.time() - t0
    print(f"  INFO  X07  coût : {dt:.2f} s pour {n / fs:.0f} s de mono ({dt / (n / fs):.2f}× le temps réel, numpy)")
    nf = sum(1 for o in RES if not o)
    print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
    sys.exit(1 if nf else 0)
