"""CONTRAT DE L'EXCITER v3 « Aural » (flux) — 2026-09-28.
  W01 blocs      résultat identique quelle que soit la taille des blocs (64, 1000, entier) : < 1e-9
  W02 latence    impulsion → sortie < 1e-7 avant 20 échantillons ; silence → < 1e-7
  W03 gain       sinus faible au centre de la zone, profil Doux, drive 0,5 (quasi linéaire) : sortie = renfort de g dB ± 1 dB (g = 3, 6, 12)
  W04 niveau     le caractère ne dépend pas du niveau d'entrée : ×0,1 → wet ×0,1 (± 0,5 dB)
  W05 régularité wet continu : crête/RMS ≤ 8 sur la musique (v2 : 19,5), fenêtres de 100 ms muettes ≤ 5 %
  W06 pureté     pureté 1 → fondamental réduit d au moins 15 dB (mesuré ≈ 20 dB : limité par l estimation du niveau et le filtrage ADAA)
  W07 robustesse 4 profils × 3 fréquences d'échantillonnage × (bruit, silence, musique), formes cloche/shelfs : fini, borné
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_exciter_v3_stream import exciter_v3_stream, D_OS
from prisme_exciter_v2_stream import PROFILS
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
RES = []
rmsdb = lambda v: 20 * np.log10(np.sqrt(np.mean(v ** 2)) + 1e-30)


def check(tid, desc, val, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:70s} {val}")


if __name__ == "__main__":
    fs, X = load(SRC)
    x = np.ascontiguousarray(X[int(30 * fs): int(36 * fs), 0])
    kw = dict(shape="bell", f0=3000.0, q=0.71, gain_db=6.0, profil="mordant_chaud")
    ref = exciter_v3_stream(x, fs, block=len(x), **kw)
    e = max(np.max(np.abs(exciter_v3_stream(x, fs, block=b, **kw) - ref)) for b in (64, 1000))
    check("W01", "indépendance à la taille des blocs (64, 1000)", f"écart {e:.1e}", e < 1e-9)
    imp = np.zeros(4000); imp[100] = 1.0
    w = exciter_v3_stream(imp, fs, **kw)
    s0 = np.max(np.abs(exciter_v3_stream(np.zeros(5000), fs, **kw)))
    check("W02", "avant l'impulsion + latence, et silence : < 1e-7", f"avant {np.max(np.abs(w[:100 + D_OS - 1])):.1e} ; silence {s0:.1e}", np.max(np.abs(w[:100 + D_OS - 1])) < 1e-7 and s0 < 1e-7)
    t = np.arange(fs * 3) / fs
    sn = 0.01 * np.sin(2 * np.pi * 3000.0 * t)
    det = []
    for g in (3.0, 6.0, 12.0):
        wv = exciter_v3_stream(sn, fs, **dict(kw, gain_db=g, profil="doux", drive=0.5))
        y = sn[: len(sn) - D_OS] + wv[D_OS:]
        det.append(rmsdb(y[fs:]) - rmsdb(sn[fs:len(sn) - D_OS]))
    check("W03", "« +g dB » ≈ renfort de g dB de la zone (sinus, quasi linéaire)", " ".join(f"{v:+.2f}" for v in det), all(abs(d - g) <= 1.0 for d, g in zip(det, (3.0, 6.0, 12.0))))
    a = exciter_v3_stream(x, fs, **kw); b = exciter_v3_stream(0.1 * x, fs, **kw)
    r = rmsdb(b[fs:]) - rmsdb(a[fs:])
    check("W04", "le wet suit le niveau (×0,1 → −20 dB), caractère indépendant du niveau", f"{r:+.2f} dB", abs(r + 20.0) <= 0.5)
    ww = int(0.1 * fs)
    rr = ref[fs:]
    nw = len(rr) // ww
    lw = 10 * np.log10((rr[: nw * ww].reshape(nw, ww) ** 2).mean(axis=1) + 1e-20)
    cr = np.max(np.abs(rr)) / np.sqrt(np.mean(rr ** 2))
    muet = 100 * np.mean(lw < np.median(lw) - 25)
    check("W05", "wet continu : crête/RMS ≤ 8, fenêtres muettes ≤ 5 %", f"crête/RMS {cr:.1f} ; muettes {muet:.0f} %", cr <= 8 and muet <= 5)
    s1 = 0.1 * np.sin(2 * np.pi * 3000.0 * t)
    def a_f0(v):
        v = v[fs:]
        P = np.abs(np.fft.rfft(v * np.hanning(len(v)))) ** 2
        f = np.fft.rfftfreq(len(v), 1 / fs)
        return 10 * np.log10(P[(f > 2950) & (f < 3050)].sum() + 1e-30)
    d = a_f0(exciter_v3_stream(s1, fs, **dict(kw, purete=0.0))) - a_f0(exciter_v3_stream(s1, fs, **dict(kw, purete=1.0)))
    check("W06", "pureté 1 : fondamental réduit (≥ 15 dB sous pureté 0 ; limite : estimation du niveau, ADAA)", f"{d:.1f} dB", d >= 15)
    ok, pire = True, 0.0
    rng = np.random.default_rng(3)
    for pr in PROFILS:
        for f_s in (44100, 48000, 96000):
            for sh, f0 in (("bell", 3000.0), ("highshelf", 9600.0), ("lowshelf", 60.0)):
                for sig in (rng.standard_normal(f_s) * 0.3, np.zeros(f_s), x[:f_s]):
                    y = exciter_v3_stream(sig, f_s, **dict(kw, profil=pr, shape=sh, f0=f0, gain_db=15.0, drive=6.0, tilt=0.8))
                    ok &= bool(np.all(np.isfinite(y))) and np.max(np.abs(y)) < 20.0
                    pire = max(pire, np.max(np.abs(y)))
    check("W07", "robustesse : 4 profils × 3 fs × 3 formes × 3 signaux, extrêmes", f"|y| max {pire:.2f}", ok)
    nf = sum(1 for o in RES if not o)
    print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
    sys.exit(1 if nf else 0)
