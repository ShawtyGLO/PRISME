"""CONTRAT DU LIFT (seuil absolu) — batterie de tests (2026-09-25). Voir vault : PRISME Contrat Lift.md

  L01 identité · L02 causal/blocs/latence 0 · L03 robustesse · L04 sens et plafond · L05 au-dessus du seuil intact · L06 sous le seuil relevé
  L07 courbe statique · L08 covariance (seuil absolu) · L09 plancher de bruit · L10 dynamique · L11 modulation · L12 fréquences d'éch.
  L13 bipolaire · L14 aller-retour (info) · L15 réactivité (info)
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter
from prisme_band import zone_filter
from prisme_lift import Lift, lift_band, courbe_lift_db, seuil_dbfs

sys.stdout.reconfigure(encoding="utf-8")
RES = []
FS = 48000


def check(tid, desc, value, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:62s} {value}")


def rafales(L_db, f0=1000.0, fs=FS, n_raf=6, on=0.4, off=0.4, silence=0.5):
    """Rafales sinus de niveau L_db (dBFS = niveau de bande) séparées de vrai silence ; renvoie (x, [(début, fin)])."""
    n = int(fs * (silence + n_raf * (on + off)))
    x = np.zeros(n)
    fen = []
    for k in range(n_raf):
        i = int(fs * (silence + k * (on + off)))
        j = i + int(on * fs)
        t = np.arange(j - i) / fs
        x[i:j] = 10 ** (L_db / 20) * np.sin(2 * np.pi * f0 * t)
        fen.append((i, j))
    return x, fen


def gain_rafale(L_db, gain_db=12.0, amount=60.0, f0=1000.0, fs=FS, k=-1, **kw):
    x, fen = rafales(L_db, f0, fs)
    y, d = lift_band(x, fs, "bell", f0, 1.0, gain_db, amount, diag=True, **kw)
    i, j = fen[k]
    return 20 * np.log10(np.mean(d["g"][j - int(0.05 * fs): j]))


def main():
    rng = np.random.default_rng(3)
    # L01
    x = rng.standard_normal(20000) * 0.1
    y = Lift(FS, "bell", 1000, 1.0, 0.0, 60).process(x.copy())
    check("L01", "gain 0 → sortie identique bit à bit", f"égal : {np.array_equal(x, y)}", np.array_equal(x, y))
    # L02
    x, _ = rafales(-45.0)
    x = x + rng.standard_normal(len(x)) * 1e-4

    def flux(sig, block):
        l = Lift(FS, "bell", 1000, 1.0, 12.0, 60)
        return np.concatenate([l.process(sig[i:i + block]) for i in range(0, len(sig), block)])
    ref = flux(x, len(x))
    e = max(np.max(np.abs(flux(x, b) - ref)) for b in (64, 500, 4096))
    x2 = x.copy()
    x2[len(x) // 2:] = rng.standard_normal(len(x) - len(x) // 2)
    ecaus = np.max(np.abs(flux(x2, 4096)[:len(x) // 2] - ref[:len(x) // 2]))
    imp = np.zeros(2000)
    imp[100] = 1.0
    ok_lat = bool(np.all(flux(imp, 512)[:100] == 0))
    check("L02", "blocs identiques (<1e-9), causal (< 1e-12), latence 0", f"blocs {e:.0e}, causalité {ecaus:.0e}, avant l'impulsion : {ok_lat}", e < 1e-9 and ecaus < 1e-12 and ok_lat)
    # L03
    ok3 = True
    sigs = {"silence": np.zeros(30000), "continu": np.full(30000, 0.7), "carré": np.sign(np.sin(np.arange(30000) * 0.05)),
            "impulsions": (np.arange(30000) % 997 == 0) * 1.0, "blanc": rng.standard_normal(30000) * 0.3, "-140": rng.standard_normal(30000) * 1e-7}
    for nom, s in sigs.items():
        for shp in ("bell", "lowshelf", "highshelf"):
            for f0 in (20.0, 1000.0, 20000.0):
                for q in (0.3, 12.0):
                    for G in (-12.0, 12.0):
                        for am in (0.0, 100.0):
                            for rel in (20.0, 1000.0):
                                y = lift_band(s, FS, shp, f0, q, G, am, rel, block=7000)
                                ok3 &= bool(np.all(np.isfinite(y))) and np.max(np.abs(y)) < 50 * max(1.0, np.max(np.abs(s)))
                                if nom == "silence":
                                    ok3 &= bool(np.all(y == 0))
    check("L03", "6 signaux × formes × f0 × Q × gain × Amount × relâchement", "fini, borné, silence → silence", ok3)
    # L04
    ok4 = True
    for G in (12.0, -12.0):
        for Ldb in (-80, -60, -45, -35, -25, -10, 0):
            xx, _ = rafales(Ldb)
            xx = xx + rng.standard_normal(len(xx)) * 10 ** ((Ldb - 30) / 20)
            _, d = lift_band(xx, FS, "bell", 1000, 1.0, G, 60, diag=True)
            gdb = 20 * np.log10(d["g"])
            bon = (gdb.min() > -0.5 and gdb.max() < G + 1) if G > 0 else (gdb.max() < 0.5 and gdb.min() > G - 1)
            ok4 &= bool(bon)
    check("L04", "gain>0 : jamais < −0,5, plafond G+1 ; gain<0 : symétrique", "7 niveaux × 2 signes", ok4)
    # L05
    T = seuil_dbfs(60)
    g5 = [gain_rafale(L, amount=60) for L in (T + 1, T + 10, -10.0, 0.0)]
    check("L05", "niveau ≥ seuil : |Δ| ≤ 0,5 dB", " ".join(f"{v:+.2f}" for v in g5), max(abs(v) for v in g5) <= 0.5)
    # L06
    W = max(1.667 * 12, 6.0)
    g6 = [gain_rafale(L, amount=60) for L in (T - W - 1, T - W - 4, T - W - 8)]
    check("L06", "niveau ≤ T−W : relevé de G ± 1,5 dB (+12)", " ".join(f"{v:+.2f}" for v in g6), all(abs(v - 12) <= 1.5 for v in g6))
    # L07
    niv = np.arange(-58, -14, 5.0)
    gm = np.array([gain_rafale(L) for L in niv])
    att = np.array([courbe_lift_db(L, 12, 60) for L in niv])
    sortie = niv + gm
    check("L07", "courbe statique : conforme ±1,5 dB, sortie monotone", f"écart max {np.max(np.abs(gm - att)):.2f} dB, sortie croissante : {bool(np.all(np.diff(sortie) > 0))}",
          np.max(np.abs(gm - att)) <= 1.5 and np.all(np.diff(sortie) > 0))
    # L08
    dec = -10.0
    am2 = 60 + dec / 0.48
    ecart = max(abs(gain_rafale(L, amount=60) - gain_rafale(L + dec, amount=am2)) for L in (-45, -40, -35, -30, -25))
    a, b = gain_rafale(-52, amount=60), gain_rafale(-40, amount=60)
    check("L08", "covariance : signal −10 dB + seuil −10 dB = même gain ; seuil absolu", f"écart {ecart:.2f} dB ; −52 → {a:.1f} dB, −40 → {b:.1f} dB (courbe {courbe_lift_db(-40, 12, 60):.1f})",
          ecart <= 0.5 and abs(a - b) > 3 and abs(b - courbe_lift_db(-40, 12, 60)) <= 1.5)
    # L09
    n = FS * 30
    bruit = rng.standard_normal(n)
    bb = lfilter(*zone_filter("bell", FS, 1000, 1.0), bruit)
    niv_b = 20 * np.log10(np.pi / 2 * np.mean(np.abs(bb)))
    xb = bruit * 10 ** ((-70 - niv_b) / 20)
    _, d = lift_band(xb, FS, "bell", 1000, 1.0, 12.0, 60, diag=True)
    lift_bruit = 20 * np.log10(d["g"][-10 * FS:])
    xr, fen = rafales(-55.0, n_raf=30, silence=0.0)
    xr = np.pad(xr, (0, max(0, n - len(xr))))[:n] + xb
    _, d2 = lift_band(xr, FS, "bell", 1000, 1.0, 12.0, 60, diag=True)
    gd = [20 * np.log10(np.mean(d2["g"][j - int(0.05 * FS): j])) for (i, j) in fen[-8:] if j <= n]
    check("L09", "bruit −70 dBFS seul : relevé ≤ 1 dB ; détail +15 dB : relevé G ± 1,5", f"bruit moy {lift_bruit.mean():+.2f} max {lift_bruit.max():+.2f} dB ; détail {np.mean(gd):+.2f} dB",
          lift_bruit.max() <= 1.0 and abs(np.mean(gd) - 12) <= 1.5)
    # L10
    x = np.zeros(FS * 3)
    x[FS // 2: FS // 2 + FS] = 10 ** (-20 / 20) * np.sin(2 * np.pi * 1000 * np.arange(FS) / FS)
    l = Lift(FS, "bell", 1000, 1.0, 12.0, 60)
    l.process(x)
    Lv = l.last_L
    i0 = FS // 2
    steady = Lv[i0 + FS - 1000]
    tmont = np.argmax(Lv[i0:] >= steady - 0.9) / FS * 1000
    depass = Lv[i0:i0 + FS].max() - steady
    trel = np.argmax(Lv[i0 + FS:] <= steady - 26.0) / FS * 1000
    check("L10", "relâchement 95 % à 150 ms ±25 % ; attaque ≤ 20 ms ; dépassement ≤ 1 dB", f"relâchement {trel:.0f} ms, attaque {tmont:.1f} ms, dépassement {depass:.2f} dB",
          112.5 <= trel <= 187.5 and tmont <= 20 and depass <= 1.0)
    # L11
    xm = np.zeros(FS * 8)
    for k, L in enumerate((-62, -55, -50, -45, -40, -35, -30, -50)):
        i = k * FS
        tt = np.arange(int(0.7 * FS)) / FS
        xm[i:i + len(tt)] = 10 ** (L / 20) * np.sin(2 * np.pi * 1000 * tt)
    ym = lift_band(xm, FS, "bell", 1000, 1.0, 12.0, 60)
    dm = ym - xm
    Sp = np.abs(np.fft.rfft(dm * np.hanning(len(dm)))) ** 2
    fr = np.fft.rfftfreq(len(dm), 1 / FS)
    r = 10 * np.log10(Sp[(fr < 500) | (fr > 2000)].sum() / Sp[(fr > 500) & (fr < 2000)].sum() + 1e-30)
    tt = np.arange(FS * 12) / FS
    ripple = []
    for f0 in (60.0, 250.0):
        so = 10 ** (-42 / 20) * np.sin(2 * np.pi * f0 * tt)
        _, dp = lift_band(so, FS, "bell", f0, 1.0, 12.0, 60, diag=True)
        gd = 20 * np.log10(dp["g"][2 * FS:])
        m = np.convolve(gd, np.ones(FS // 4) / (FS // 4), mode="same")[FS // 4:-FS // 4]
        ripple.append(np.std(gd[FS // 4:-FS // 4] - m))
    prog = lfilter(*zone_filter("bell", FS, 1000, 1.0), np.random.default_rng(5).standard_normal(FS * 12))
    prog *= 10 ** ((-41 - 20 * np.log10(np.pi / 2 * np.mean(np.abs(prog)))) / 20)
    _, dp = lift_band(prog, FS, "bell", 1000, 1.0, 12.0, 60, diag=True)
    modrms = np.std(20 * np.log10(dp["g"][2 * FS:]))
    print(f"  INFO  L11b modulation du gain sur bruit stationnaire de bande à mi-courbe : {modrms:.2f} dB RMS (inhérent : pente de la courbe × fluctuation du niveau ≈ 1,2 dB)")
    check("L11", "hors ±1 oct ≤ −25 dB ; ondulation sur sinus grave (60, 250 Hz) ≤ 0,2 dB RMS", f"hors bande {r:.1f} dB ; ondulation {ripple[0]:.3f} / {ripple[1]:.3f} dB RMS", r <= -25 and max(ripple) <= 0.2)
    # L12
    gs = [gain_rafale(-42, fs=fs) for fs in (44100, 48000, 96000)]
    check("L12", "44,1 / 48 / 96 kHz : dispersion ≤ 0,5 dB", " ".join(f"{v:.2f}" for v in gs), max(gs) - min(gs) <= 0.5)
    # L13
    ga, gh = gain_rafale(-52, gain_db=-12.0), gain_rafale(-20, gain_db=-12.0)
    check("L13", "gain −12 : bas niveau −12 ± 1,5 dB, haut niveau ≤ 0,5", f"bas {ga:+.2f} dB, haut {gh:+.2f} dB", abs(ga + 12) <= 1.5 and abs(gh) <= 0.5)
    # L14 (info)
    xr, _ = rafales(-45.0)
    ya = lift_band(xr, FS, "bell", 1000, 1.0, 9.0, 60)
    yb = lift_band(ya, FS, "bell", 1000, 1.0, -9.0, 60)
    print(f"  INFO  L14  aller-retour Lift +9 puis expandeur −9 : résidu {20 * np.log10(np.sqrt(np.mean((yb - xr) ** 2)) / np.sqrt(np.mean(xr ** 2))):.1f} dB sous le signal")
    # L15 (info)
    x = np.zeros(FS * 3)
    x[FS // 2: FS] = 10 ** (-20 / 20) * np.sin(2 * np.pi * 1000 * np.arange(FS // 2) / FS)
    x[FS:] = 10 ** (-52 / 20) * np.sin(2 * np.pi * 1000 * np.arange(2 * FS) / FS)
    _, d = lift_band(x, FS, "bell", 1000, 1.0, 12.0, 60, diag=True)
    gdb = 20 * np.log10(d["g"])
    t90 = np.argmax(gdb[FS:] >= 0.9 * 12) / FS * 1000
    print(f"  INFO  L15  après un passage fort (−20 dB) puis un détail (−52 dB), le lift atteint 90 % du gain en {t90:.0f} ms (relâchement 150 ms)")
    nf = sum(1 for o in RES if not o)
    print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
    sys.exit(1 if nf else 0)


if __name__ == "__main__":
    main()
