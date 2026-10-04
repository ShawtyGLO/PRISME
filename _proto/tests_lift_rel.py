"""CONTRAT DU LIFT À SEUIL RELATIF — batterie de tests (2026-10-04). Voir vault : PRISME Contrat Lift.md (section révisée).

  R01 identité · R02 causal/blocs/latence 0 · R03 robustesse · R04 sens et plafond · R05 signal stationnaire → pas de relevé (à tout niveau)
  R06 covariance au niveau (signal décalé de k dB → même relevé) · R07 passage faible relevé puis le « normal » se déplace · R08 Amount monotone
  R09 plancher de bruit · R10 dynamique (retour du fort : coupure rapide ; enclenchement) · R11 modulation · R12 fréquences d'éch. · R13 bipolaire · R14/R15 informations
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter
from prisme_band import zone_filter
from prisme_lift_rel import LiftRel, lift_rel_band, courbe_lift_rel_db, seuil_rel_db

sys.stdout.reconfigure(encoding="utf-8")
RES = []
FS = 48000


def check(tid, desc, value, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:66s} {value}")


def sequence(plan, f0=1000.0, fs=FS, lit_db=-90.0, seed=1):
    """plan = [(niveau dBFS de bande, durée s), …] : sinus de f0 à ces niveaux, sur un lit de bruit très bas (le « souffle »). Renvoie (x, bornes de chaque segment en échantillons)."""
    rng = np.random.default_rng(seed)
    segs, bornes, i = [], [], 0
    for L, d in plan:
        n = int(d * fs)
        t = (i + np.arange(n)) / fs
        segs.append(10 ** (L / 20) * np.sin(2 * np.pi * f0 * t))
        bornes.append((i, i + n))
        i += n
    x = np.concatenate(segs)
    return x + rng.standard_normal(len(x)) * 10 ** (lit_db / 20), bornes


def gains(x, fs=FS, f0=1000.0, G=12.0, amount=60.0, **kw):
    _, d = lift_rel_band(x, fs, "bell", f0, 1.0, G, amount, diag=True, **kw)
    return 20 * np.log10(d["g"])


def main():
    rng = np.random.default_rng(3)
    # R01
    x = rng.standard_normal(20000) * 0.1
    y = LiftRel(FS, "bell", 1000, 1.0, 0.0, 60).process(x.copy())
    check("R01", "gain 0 → sortie identique bit à bit", f"égal : {np.array_equal(x, y)}", np.array_equal(x, y))
    # R02
    x, _ = sequence([(-8, 3), (-38, 3)])

    def flux(sig, block):
        l = LiftRel(FS, "bell", 1000, 1.0, 12.0, 60)
        return np.concatenate([l.process(sig[i:i + block]) for i in range(0, len(sig), block)])
    ref = flux(x, len(x))
    e = max(np.max(np.abs(flux(x, b) - ref)) for b in (64, 500, 4096))
    x2 = x.copy()
    x2[len(x) // 2:] = rng.standard_normal(len(x) - len(x) // 2)
    ecaus = np.max(np.abs(flux(x2, 4096)[:len(x) // 2] - ref[:len(x) // 2]))
    imp = np.zeros(2000)
    imp[100] = 1.0
    ok_lat = bool(np.all(flux(imp, 512)[:100] == 0))
    check("R02", "blocs identiques (<1e-9), causal (< 1e-12), latence 0", f"blocs {e:.0e}, causalité {ecaus:.0e}, avant l'impulsion : {ok_lat}", e < 1e-9 and ecaus < 1e-12 and ok_lat)
    # R03
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
                                y = lift_rel_band(s, FS, shp, f0, q, G, am, rel, block=7000)
                                ok3 &= bool(np.all(np.isfinite(y))) and np.max(np.abs(y)) < 50 * max(1.0, np.max(np.abs(s)))
                                if nom == "silence":
                                    ok3 &= bool(np.all(y == 0))
    check("R03", "6 signaux × formes × f0 × Q × gain × Amount × relâchement", "fini, borné, silence → silence", ok3)
    # R04
    ok4 = True
    for G in (12.0, -12.0):
        for plan in ([(-8, 3), (-38, 3), (-8, 2)], [(-20, 3), (-50, 3)], [(-60, 6)], [(0, 2), (-30, 2), (-5, 2)]):
            xx, _ = sequence(plan)
            g = gains(xx, G=G)
            bon = (g.min() > -0.5 and g.max() < G + 1) if G > 0 else (g.max() < 0.5 and g.min() > G - 1)
            ok4 &= bool(bon)
    check("R04", "gain>0 : jamais < −0,5, plafond G+1 ; gain<0 : symétrique", "4 programmes × 2 signes", ok4)
    # R05 : signal stationnaire, à tout niveau → pas de relevé (le « normal » est lui-même)
    r5 = []
    for L in (-58.0, -45.0, -30.0, -15.0, -3.0):
        xx, b = sequence([(L, 12)])
        g = gains(xx)
        r5.append(np.abs(g[-3 * FS:]).max())
    check("R05", "signal stationnaire (−58 … −3 dBFS) : |relevé| ≤ 0,5 dB après 9 s", " ".join(f"{v:.2f}" for v in r5), max(r5) <= 0.5)
    # R06 : covariance au niveau (tout le programme décalé de k dB → même relevé), au-dessus du plancher de souffle
    pics = []
    for dec in (0.0, -5.0, -10.0):
        xx, b = sequence([(-8 + dec, 6), (-38 + dec, 3)])
        g = gains(xx)
        i0 = b[1][0]
        pics.append(g[i0 + int(0.2 * FS): i0 + int(0.6 * FS)].max())
    check("R06", "programme décalé de −5 / −10 dB : même relevé ±0,5 dB (covariance au niveau)", " ".join(f"{v:+.2f}" for v in pics), max(pics) - min(pics) <= 0.5)
    # R07 : chute de 30 dB → relevé quasi plein, puis le « normal » se déplace (le relevé s'éteint en quelques secondes)
    xx, b = sequence([(-8, 8), (-38, 8), (-8, 2)])
    g = gains(xx)
    i0 = b[1][0]
    pic = g[i0 + int(0.2 * FS): i0 + int(0.8 * FS)].max()
    fin = g[i0 + int(7 * FS): b[1][1]].mean()
    mi = g[i0 + int(3 * FS)]
    check("R07", "chute de 30 dB : relevé ≥ 0,85·G en < 1 s, puis décroît (le normal se déplace)", f"pic {pic:+.1f} dB ; à 3 s {mi:+.1f} dB ; à 7–8 s {fin:+.1f} dB",
          pic >= 0.85 * 12 and mi < pic - 3 and fin <= 3.0)
    # R08 : Amount monotone
    xx, b = sequence([(-8, 6), (-23, 2)])
    pv = []
    for am in (0.0, 30.0, 60.0, 100.0):
        g = gains(xx, amount=am)
        pv.append(g[b[1][0] + int(0.25 * FS): b[1][0] + int(0.7 * FS)].max())
    check("R08", "même chute de 15 dB : relevé croissant avec Amount (0 → 100 %)", " ".join(f"{v:+.2f}" for v in pv), all(np.diff(pv) >= -0.1) and pv[-1] > pv[0] + 3)
    # R09 : souffle
    n = FS * 30
    bruit = rng.standard_normal(n)
    bb = lfilter(*zone_filter("bell", FS, 1000, 1.0), bruit)
    niv_b = 20 * np.log10(np.pi / 2 * np.mean(np.abs(bb)))
    xb = bruit * 10 ** ((-70 - niv_b) / 20)
    _, d = lift_rel_band(xb, FS, "bell", 1000, 1.0, 12.0, 60, diag=True)
    lift_bruit = 20 * np.log10(d["g"][-10 * FS:])
    # souffle seul après un passage fort : le « très faible par rapport à l'habituel » n'est pas du détail
    def avec_lit(plan):
        xx, b = sequence(plan, lit_db=-120.0)
        m = len(xx)
        lit = np.convolve(rng.standard_normal(m + 64), np.ones(1), "same")[:m]
        lit = lfilter(*zone_filter("bell", FS, 1000, 1.0), lit)
        lit *= 10 ** ((-70 - 20 * np.log10(np.pi / 2 * np.mean(np.abs(lit)))) / 20)
        return xx + lit, b
    xs, b = avec_lit([(-10, 10), (-300, 5)])
    g_s = gains(xs)
    souffle_apres = g_s[b[1][0] + int(2.5 * FS): b[1][1]].max()          # la queue du fort (0–2 s) est légitimement relevée ; le souffle qui reste ne l'est pas
    xd, b = avec_lit([(-10, 10), (-45, 1.5)])
    g_d = gains(xd)
    detail = g_d[b[1][0] + int(0.3 * FS): b[1][1]].max()
    check("R09", "bruit −70 dBFS seul ou après du fort : relevé ≤ 1,5 dB ; détail −45 dB : relevé > 6 dB", f"bruit seul max {lift_bruit.max():+.2f} dB ; bruit après fort {souffle_apres:+.2f} dB ; détail {detail:+.2f} dB",
          lift_bruit.max() <= 1.0 and souffle_apres <= 1.5 and detail > 6.0)
    # R10 : le retour du fort coupe le relevé vite ; enclenchement après la chute
    xx, b = sequence([(-8, 6), (-38, 1.2), (-8, 2)])
    g = gains(xx)
    i_chute, i_ret = b[1][0], b[2][0]
    plein = g[i_ret - 1000]
    coupe = np.argmax(g[i_ret:] <= 0.1 * plein) / FS * 1000
    t90 = np.argmax(g[i_chute:] >= 0.9 * 12) / FS * 1000
    check("R10", "retour du fort : relevé coupé (≤ 10 %) en ≤ 40 ms ; enclenchement 90 % ≤ 300 ms", f"coupure {coupe:.0f} ms ; enclenchement {t90:.0f} ms (plein {plein:+.1f} dB)", coupe <= 40 and t90 <= 300)
    # R11 : modulation
    xm, _ = sequence([(-8, 1.5), (-38, 1.5)] * 3)
    ym = lift_rel_band(xm, FS, "bell", 1000, 1.0, 12.0, 60)
    dm = ym - xm
    Sp = np.abs(np.fft.rfft(dm * np.hanning(len(dm)))) ** 2
    fr = np.fft.rfftfreq(len(dm), 1 / FS)
    r = 10 * np.log10(Sp[(fr < 500) | (fr > 2000)].sum() / Sp[(fr > 500) & (fr < 2000)].sum() + 1e-30)
    tt = np.arange(FS * 14) / FS
    ripple = []
    for f0 in (60.0, 250.0):
        so = 10 ** (-42 / 20) * np.sin(2 * np.pi * f0 * tt) + rng.standard_normal(len(tt)) * 10 ** (-90 / 20)
        g = gains(so, f0=f0)
        gd = g[5 * FS:]
        ripple.append(np.std(gd))
    check("R11", "hors ±1 oct ≤ −25 dB ; ondulation sur sinus grave stationnaire ≤ 0,2 dB RMS", f"hors bande {r:.1f} dB ; ondulation {ripple[0]:.3f} / {ripple[1]:.3f} dB RMS", r <= -25 and max(ripple) <= 0.2)
    # R12
    gs = []
    for fs in (44100, 48000, 96000):
        xx, b = sequence([(-8, 6), (-38, 2)], fs=fs)
        g = gains(xx, fs=fs)
        gs.append(g[b[1][0] + int(0.2 * fs): b[1][0] + int(0.6 * fs)].max())
    check("R12", "44,1 / 48 / 96 kHz : dispersion ≤ 0,5 dB", " ".join(f"{v:.2f}" for v in gs), max(gs) - min(gs) <= 0.5)
    # R13
    xx, b = sequence([(-8, 6), (-38, 2)])
    g = gains(xx, G=-12.0)
    bas = g[b[1][0] + int(0.25 * FS): b[1][0] + int(0.7 * FS)].min()
    haut = np.abs(g[b[0][1] - 2 * FS: b[0][1]]).max()
    check("R13", "gain −12 : le passage faible baisse de ~12 dB (±1,5), le niveau habituel ≤ 0,5", f"bas {bas:+.2f} dB, habituel {haut:+.2f} dB", abs(bas + 12) <= 1.5 and haut <= 0.5)
    # R14 (info)
    xr, _ = sequence([(-8, 4), (-38, 1.5)] * 2)
    ya = lift_rel_band(xr, FS, "bell", 1000, 1.0, 9.0, 60)
    yb = lift_rel_band(ya, FS, "bell", 1000, 1.0, -9.0, 60)
    print(f"  INFO  R14  aller-retour Lift +9 puis expandeur −9 : résidu {20 * np.log10(np.sqrt(np.mean((yb - xr) ** 2)) / np.sqrt(np.mean(xr ** 2))):.1f} dB sous le signal")
    # R15 (info) : enclenchement rapide + maintien lent (relâchement adaptatif) contre un relâchement unique
    xx, b = sequence([(-8, 6), (-38, 2), (-8, 2), (-38, 2)])
    g = gains(xx)
    ond = np.std(g[b[1][0] + int(0.4 * FS): b[1][1]])
    print(f"  INFO  R15  relevé sur un passage faible de 2 s : moyenne {g[b[1][0] + int(0.4 * FS): b[1][1]].mean():+.1f} dB, écart-type {ond:.2f} dB ; Th relatif à Amount 60 % = {seuil_rel_db(60):.1f} dB")
    nf = sum(1 for o in RES if not o)
    print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
    sys.exit(1 if nf else 0)


if __name__ == "__main__":
    main()
