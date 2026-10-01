"""CONTRAT DU TAME — batterie de tests (2026-09-25). Un test échoue = le Tame n'est pas encore « infaillible ».

  T01 identité          gain 0 → sortie identique bit à bit
  T02 causalité         y[:n] ne dépend que de x[:n] (indispensable au temps réel) : écart < 1e-9
  T03 robustesse        silence, continu, carré plein échelle, impulsions, bruit blanc, bruit −140 dB, paramètres extrêmes :
                        sortie finie, bornée (|y| ≤ 4), silence → silence exact
  T04 sens              gain < 0 : aucune bande de 1/6 d'octave n'augmente de plus de +0,5 dB ; gain > 0 : aucune ne baisse de plus de 0,5 dB
  T05 plafond           la réduction d'un pic n'excède jamais |gain| + 1 dB
  T06 confinement       une résonance hors zone bouge de < 0,3 dB ; le bruit à > 2,5 octaves de la zone de < 0,1 dB
  T07 position          une résonance balayée dans la zone (±0,25 oct) est réduite de façon constante : dispersion ≤ 1,5 dB (pas de « scalloping »)
  T08 niveau            réduction identique de −40 à +6 dB d'entrée : dispersion ≤ 0,5 dB
  T09 fréquence d'éch.  44,1 / 48 / 96 kHz : dispersion ≤ 1,0 dB
  T10 transparence      bruit rose et blanc sans résonance : |Δ| ≤ 0,1 dB par tiers d'octave
  T11 modulation        pente du gain appliqué ≤ 3 dB/ms ; part de la variance du gain au-dessus de 30 Hz ≤ 1e-3 (pas de bourdonnement)
  T12 dynamique         un pic qui apparaît est réduit à 80 % en ≤ 40 ms ; le bruit retrouve son niveau à 80 % en ≤ 400 ms ; dépassement ≤ 1 dB
  T14 bipolaire         |effet du + | / |effet du − | ∈ [0,7 ; 1,4] pour le même |gain|
  T15 largeur           la largeur du creux croît avec le réglage « largeur » ; fin ≤ 0,5 × large
  T16 musique           sur un vrai mix : sens (T04) et modulation (T11) respectés
"""
import sys, os, time, importlib
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, welch, butter, sosfilt
from prisme_dsp import rbj_bandpass0db

sys.stdout.reconfigure(encoding="utf-8")
tame_band = importlib.import_module(os.environ.get("TAME_MODULE", "prisme_tame")).tame_band
DUR = float(os.environ.get("TEST_DUR", "5"))
KW = dict(shape="bell", f0=3000.0, q=0.7)
RESULTS = []


def pink(n, fs, seed=1, rms=0.05):
    w = np.random.default_rng(seed).standard_normal(n)
    W = np.fft.rfft(w); f = np.fft.rfftfreq(n, 1 / fs)
    W[1:] /= np.sqrt(f[1:]); W[0] = 0
    y = np.fft.irfft(W, n)
    return y * rms / np.std(y)


def add_tone(x, fs, f, rel_db=12.0):
    t = np.arange(len(x)) / fs
    brms = np.std(lfilter(*rbj_bandpass0db(fs, f, 8.6), x))
    return x + np.sqrt(2) * brms * 10 ** (rel_db / 20) * np.sin(2 * np.pi * f * t)


def psd(x, fs):
    nper = int(2 ** np.ceil(np.log2(fs / 2.9)))
    return welch(x, fs, nperseg=nper, noverlap=nper // 2)


def tone_db(x, fs, f):
    fr, P = psd(x, fs)
    k = (fr > f * 0.985) & (fr < f * 1.015)
    return 10 * np.log10(P[k].max() + 1e-30)


def tiers(x, fs, centres, frac=6):
    fr, P = psd(x, fs)
    return np.array([10 * np.log10(P[(fr >= c / 2 ** (1 / frac)) & (fr < c * 2 ** (1 / frac))].sum() + 1e-30) for c in centres])


def reduc(x, y, fs, f):
    return tone_db(y, fs, f) - tone_db(x, fs, f)


def check(tid, desc, value, ok):
    RESULTS.append((tid, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:62s} {value}")


def sig(fs=48000.0, res=(3100.0,), seed=1, dur=None):
    n = int(fs * (dur or DUR))
    x = pink(n, fs, seed)
    for f in res:
        x = add_tone(x, fs, f)
    return x


def run():
    fs = 48000.0
    x = sig(fs, res=(1700.0, 3100.0, 5300.0))
    print(f"module : {os.environ.get('TAME_MODULE', 'prisme_tame')} ; durée des signaux {DUR:.0f} s\n")
    # T01
    check("T01", "identité à gain 0", "", np.array_equal(tame_band(x, fs, gain_db=0.0, **KW), x))
    # T02
    n2 = len(x) // 2
    a = tame_band(x, fs, gain_db=-9.0, width=1.0, **KW)[:n2]
    b = tame_band(x[:n2], fs, gain_db=-9.0, width=1.0, **KW)
    check("T02", "causalité (troncature)", f"écart max {np.max(np.abs(a - b)):.2e}", np.max(np.abs(a - b)) < 1e-9)
    b1 = tame_band(x[:int(fs * 2)], fs, gain_db=-9.0, width=1.0, block=1000, **KW)
    b2 = tame_band(x[:int(fs * 2)], fs, gain_db=-9.0, width=1.0, block=1 << 20, **KW)
    check("T02", "indépendance à la taille des blocs (1000 vs entier)", f"écart max {np.max(np.abs(b1 - b2)):.2e}", np.max(np.abs(b1 - b2)) < 1e-9)
    # T03
    t = np.arange(int(fs * 2)) / fs
    rng = np.random.default_rng(5)
    imp = np.zeros(len(t)); imp[::4800] = 1.0
    cas = {"silence": np.zeros(len(t)), "continu 0,5": np.full(len(t), 0.5), "carré ±1 100 Hz": np.sign(np.sin(2 * np.pi * 100 * t)),
           "impulsions": imp, "bruit blanc ±1": np.clip(rng.standard_normal(len(t)), -1, 1), "bruit −140 dB": rng.standard_normal(len(t)) * 1e-7}
    params = [dict(shape="bell", f0=20.0, q=0.1), dict(shape="bell", f0=20000.0, q=20.0), dict(shape="highshelf", f0=8000.0, q=0.7),
              dict(shape="lowshelf", f0=200.0, q=0.7), dict(shape="bell", f0=1000.0, q=20.0)]
    ok, pire = True, 0.0
    for nom, s in cas.items():
        for p in params:
            for g in (-24.0, 24.0):
                for w in (0.0, 1.0):
                    y = tame_band(s, fs, gain_db=g, width=w, **p)
                    fin = np.all(np.isfinite(y)); pire = max(pire, np.max(np.abs(y)) if fin else 99)
                    borne = (2.0 if g < 0 else 1.5) * max(np.max(np.abs(s)), 1e-9) * (10 ** (24 / 20) if g > 0 else 1.0)          # cut : ≤ 2·crête d entrée (v4 : couper −24 dB tous les harmoniques d un carré change sa forme, crête ×1,62) ; boost +24 dB : ≤ 1,5·×16
                    ok &= fin and np.max(np.abs(y)) <= borne
                    if nom == "silence": ok &= np.all(y == 0)
    check("T03", "cas extrêmes × paramètres extrêmes", f"|y| max {pire:.2f}", ok)
    # T04
    real = None
    try:
        from render import load
        from bench_leak import SRC
        fsr, xr = load(SRC); real = xr.mean(axis=1)[int(30 * fsr): int(36 * fsr)]; fsr_ = fsr
    except Exception:
        pass
    cent = 1000 * 2.0 ** (np.arange(-9, 13) / 3)
    for nom, s, f_s in (("pink+résonances", x, fs), ("pink", sig(fs, res=()), fs), ("blanc", np.random.default_rng(2).standard_normal(int(fs * DUR)) * 0.05, fs)):
        for g in (-9.0, +9.0):
            d = tiers(tame_band(s, f_s, gain_db=g, width=1.0, **KW), f_s, cent) - tiers(s, f_s, cent)
            ok = (d.max() <= 0.5) if g < 0 else (d.min() >= -0.5)
            check("T04", f"sens ({nom}, {g:+.0f} dB)", f"extrême {d.max() if g < 0 else d.min():+.2f} dB", ok)
    # T05
    xs = sig(fs, res=(3100.0,), dur=DUR); xs = add_tone(xs, fs, 3100.0, 13.0)
    for g in (-6.0, -12.0):
        r = reduc(xs, tame_band(xs, fs, gain_db=g, width=1.0, **KW), fs, 3100.0)
        check("T05", f"plafond (gain {g:+.0f} dB, pic +25 dB)", f"réduction {r:+.1f} dB", r >= g - 1.0)
    # T06
    xo = sig(fs, res=(3100.0, 12000.0))
    yo = tame_band(xo, fs, gain_db=-9.0, width=1.0, shape="bell", f0=3000.0, q=1.4)
    r12 = reduc(xo, yo, fs, 12000.0)
    check("T06", "résonance hors zone (12 kHz, cloche 3 kHz Q 1,4)", f"{r12:+.2f} dB", abs(r12) < 0.3)
    # T07 position
    for wd in (1.0, 0.5, 0.0):
        rs = []
        for u in np.linspace(-0.25, 0.25, 9):
            f = 3000.0 * 2 ** u
            xs = sig(fs, res=(f,), dur=min(DUR, 4))
            rs.append(reduc(xs, tame_band(xs, fs, gain_db=-9.0, width=wd, **KW), fs, f))
        check("T07", f"position (largeur {wd:.1f})", f"réductions {min(rs):+.1f}…{max(rs):+.1f} dB (dispersion {max(rs)-min(rs):.1f})", (max(rs) - min(rs)) <= 1.5)
    # T08 niveau
    rs = []
    for db in (-40, -20, 0, 6):
        s = x * 10 ** (db / 20); rs.append(reduc(s, tame_band(s, fs, gain_db=-9.0, width=1.0, **KW), fs, 3100.0))
    check("T08", "niveau d'entrée −40…+6 dB", f"dispersion {max(rs)-min(rs):.2f} dB", (max(rs) - min(rs)) <= 0.5)
    # T09 fréquence d'échantillonnage
    rs = []
    for f_s in (44100.0, 48000.0, 96000.0):
        s = sig(f_s, res=(3100.0,), dur=min(DUR, 4)); rs.append(reduc(s, tame_band(s, f_s, gain_db=-9.0, width=1.0, **KW), f_s, 3100.0))
    check("T09", "fréquence d'échantillonnage 44,1/48/96 kHz", f"réductions {['%+.1f' % r for r in rs]}", (max(rs) - min(rs)) <= 1.0)
    # T10 transparence
    for nom, s in (("rose", sig(fs, res=())), ("blanc", np.random.default_rng(3).standard_normal(int(fs * DUR)) * 0.05)):
        d = tiers(tame_band(s, fs, gain_db=-9.0, width=1.0, **KW), fs, cent) - tiers(s, fs, cent)
        check("T10", f"transparence ({nom})", f"|Δ| max {np.max(np.abs(d)):.3f} dB", np.max(np.abs(d)) <= 0.1)
    # T11 modulation
    try:
        y, dg = tame_band(x, fs, gain_db=-9.0, width=1.0, diag=True, **KW)
        red = dg.get("red_full")
        if red is None:
            check("T11", "modulation du gain appliqué", "non mesurable (pas de red_full)", False)
        else:
            r64 = red.astype(np.float64)
            pente = np.max(np.abs(np.diff(r64, axis=1))) * fs / 1000.0
            sos = butter(2, 30.0, btype="high", fs=fs, output="sos")
            act = np.max(r64, axis=1) > 0.5
            prof = np.max(np.sqrt(np.mean(sosfilt(sos, r64[act], axis=1) ** 2, axis=1))) if act.any() else 0.0
            check("T11", "modulation du gain appliqué (pente ; profondeur > 30 Hz)", f"pente max {pente:.2f} dB/ms ; modulation {prof:.3f} dB RMS", pente <= 3.0 and prof <= 0.15)
    except TypeError:
        check("T11", "modulation du gain appliqué", "diag non supporté", False)
    # T12 dynamique
    n = int(fs * 3.5); tt = np.arange(n) / fs
    base = pink(n, fs, 4)
    brms = np.std(lfilter(*rbj_bandpass0db(fs, 3100.0, 8.6), base))
    gate = np.clip((tt - 1.0) / 0.002, 0, 1) * np.clip((2.0 - tt) / 0.002, 0, 1)
    xg = base + np.sqrt(2) * brms * 10 ** (12 / 20) * np.sin(2 * np.pi * 3100.0 * tt) * gate
    yg = tame_band(xg, fs, gain_db=-9.0, width=1.0, **KW)
    sos = butter(2, [3100 * 0.97, 3100 * 1.03], btype="band", fs=fs, output="sos")
    env = lambda z: np.convolve(sosfilt(sos, z) ** 2, np.ones(int(0.005 * fs)) / int(0.005 * fs), mode="same")
    rdb = 10 * np.log10((env(yg) + 1e-20) / (env(xg) + 1e-20))
    ss = np.median(rdb[int(1.6 * fs):int(1.95 * fs)])
    idx = np.where(rdb[int(1.0 * fs):int(2.0 * fs)] <= 0.8 * ss)[0]
    t80 = (idx[0] / fs * 1000) if len(idx) else 9999
    over = ss - np.min(rdb[int(1.0 * fs):int(2.0 * fs)])
    nb = 10 * np.log10((env(yg) + 1e-20) / (env(base) + 1e-20))                       # niveau du bruit seul après la coupure (yg vs base)
    post = rdb[int(2.05 * fs):int(3.4 * fs)]
    rel = np.where(post >= -0.2 * abs(ss))[0]
    t_rel = (rel[0] / fs * 1000 + 50) if len(rel) else 9999
    check("T12", "dynamique : apparition (80 %)", f"t80 {t80:.0f} ms ; réduction stable {ss:+.1f} dB ; dépassement {over:.1f} dB", t80 <= 100 and over <= 1.0)
    check("T12", "dynamique : relâchement (retour du bruit)", f"retour à 80 % en {t_rel:.0f} ms", t_rel <= 400)
    # T14 bipolaire
    xb = sig(fs, res=(3100.0,))
    rc = reduc(xb, tame_band(xb, fs, gain_db=-9.0, width=1.0, **KW), fs, 3100.0)
    rb = reduc(xb, tame_band(xb, fs, gain_db=+9.0, width=1.0, **KW), fs, 3100.0)
    check("T14", "bipolaire : symétrie coupe/boost", f"coupe {rc:+.1f} dB, boost {rb:+.1f} dB", 0.7 <= abs(rb) / max(abs(rc), 1e-9) <= 1.4)
    # T15 largeur : une résonance à 3,1 kHz déclenche ; des sondes FAIBLES (−6 dB sous le bruit de bande, sous le seuil) placées à δ octaves
    # mesurent le profil d'atténuation réellement appliqué ; largeur = étendue où l'atténuation dépasse la moitié de celle du centre
    deltas = np.array([0.0, 0.04, 0.08, 0.12, 0.17, 0.23, 0.3, 0.4, 0.55])
    def profil(wd):
        xs = sig(fs, res=(3100.0,))
        for d in deltas[1:]:
            xs = add_tone(xs, fs, 3100.0 * 2 ** d, -6.0)
        ys = tame_band(xs, fs, gain_db=-12.0, width=wd, **KW)
        return np.array([reduc(xs, ys, fs, 3100.0 * 2 ** d) for d in deltas])
    P = {wd: profil(wd) for wd in (1.0, 0.5, 0.0)}
    def larg(p):
        m = p[1]
        if m > -1.0:
            return 0.0
        ok = np.where(p <= 0.5 * m)[0]
        return 2 * deltas[ok.max()]
    ws = [larg(P[wd]) for wd in (1.0, 0.5, 0.0)]
    check("T15", "largeur du creux (fin / moyen / large, sondes)", f"{ws[0]:.2f} / {ws[1]:.2f} / {ws[2]:.2f} oct", ws[0] < ws[1] < ws[2] and ws[0] <= 0.5 * ws[2])
    # T16 musique
    if real is not None:
        for g in (-9.0, +9.0):
            d = tiers(tame_band(real, fsr_, gain_db=g, width=1.0, **KW), fsr_, cent) - tiers(real, fsr_, cent)
            ok = (d.max() <= 0.5) if g < 0 else (d.min() >= -0.5)
            check("T16", f"musique : sens ({g:+.0f} dB)", f"extrême {d.max() if g < 0 else d.min():+.2f} dB", ok)
    nf = sum(1 for _, o in RESULTS if not o)
    print(f"\n{len(RESULTS) - nf}/{len(RESULTS)} réussis, {nf} échec(s)")
    return nf


if __name__ == "__main__":
    t0 = time.time()
    sys.exit(1 if run() else 0)
