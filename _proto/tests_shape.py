"""CONTRAT DU SHAPE — batterie de tests (2026-09-25).

  S01 identité             gain 0 → sortie identique
  S02 causalité / blocs    y[:n] ne dépend que de x[:n] ; résultat identique quelle que soit la taille des blocs (< 1e-9)
  S03 robustesse           silence, continu, carré plein échelle, impulsions, bruit blanc, bruit −140 dB, paramètres extrêmes : fini, borné, silence → silence
  S04 précision            salves canoniques (sinus amorti) à 60 / 250 / 1000 / 4000 Hz : la CIBLE bouge de gain ± 1,5 dB, l'AUTRE de ≤ 1,0 dB (mesuré dans la bande)
  S05 niveau               réponse identique de −40 à +6 dB d'entrée : dispersion ≤ 0,3 dB
  S06 fréquence d'éch.     44,1 / 48 / 96 kHz : dispersion ≤ 0,5 dB
  S07 transparence         signal établi : mode transitoires ne change rien (≤ 0,1 dB) ; mode sustain donne le gain A (± 0,3 dB)
  S08 débordement          énergie ajoutée hors de ±1 octave de la bande ≤ −25 dB de celle de la bande (+12 dB) ; ≤ −20 dB sous 250 Hz (masqué par le clic du coup lui-même)
  S09 partition de l'unité transitoires(A) + sustain(A) = gain statique A (écart ≤ 0,3 dB sur les salves)
  S10 bipolaire            |effet du +6| / |effet du −6| ∈ [0,7 ; 1,4]
  S11 deux bandes          transitoires +6 & sustain −6 à la même fréquence : attaque +6 ± 2 dB, sustain −6 ± 2 dB
  S13 durée                le poids d'un transitoire retombe en `durée` (5–200 ms) : ≤ 12 % restant à t = durée, entre 30 et 95 % à 0,3·durée
  S14 sensibilité          à 30 % seule l'attaque vive déclenche (même si un gonflement lent est 12 dB plus fort) ; à 90 % les deux
  S12 bruit de fond        plancher de bruit −60 dB seul : la bande bouge de ≤ 0,5 dB (mesuré dans la bande)
"""
import sys, os, importlib
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter
from prisme_band import zone_filter

sys.stdout.reconfigure(encoding="utf-8")
shape_band = importlib.import_module(os.environ.get("SHAPE_MODULE", "prisme_shape")).shape_band
RES = []


def check(tid, desc, value, ok):
    RES.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {tid}  {desc:60s} {value}")


def salves(f0, fs, dur=4.0, per=0.7, tau=None, seed=1, plancher_db=None):
    n = int(fs * dur)
    tau = tau or (0.25 if f0 < 100 else 0.15 if f0 < 500 else 0.1)
    x = np.zeros(n)
    t = np.arange(int(0.65 * fs)) / fs
    for s in np.arange(0.1, dur - 0.7, per):
        i = int(s * fs)
        x[i:i + len(t)] += 0.5 * np.sin(2 * np.pi * f0 * t + 0.3) * np.exp(-t / tau)
    if plancher_db is not None:
        x += np.random.default_rng(seed).standard_normal(n) * 10 ** (plancher_db / 20)
    return x


def fenetres(f0):
    tf = float(np.clip(3.0 / f0, 0.002, 0.03))
    return (0.4 * tf, 2.0 * tf), (8 * tf, 8 * tf + 0.15)                 # attaque, sustain (secondes après le début de la salve)


def mesures(x, y, f0, fs, q=1.0, per=0.7, dur=4.0):
    bx, by = (lfilter(*zone_filter("bell", fs, f0, q), z) for z in (x, y))
    (a0, a1), (s0, s1) = fenetres(f0)
    att, sus = [], []
    for s in np.arange(0.1, dur - 0.7, per):
        i = int(s * fs)
        A = slice(i + int(a0 * fs), i + max(int(a1 * fs), int(a0 * fs) + 8)); S = slice(i + int(s0 * fs), i + int(s1 * fs))
        att.append(10 * np.log10(np.mean(by[A] ** 2) / np.mean(bx[A] ** 2)))
        sus.append(10 * np.log10(np.mean(by[S] ** 2) / np.mean(bx[S] ** 2)))
    return np.mean(att), np.mean(sus)


def run():
    fs = 48000.0
    print(f"module : {os.environ.get('SHAPE_MODULE', 'prisme_shape')}\n")
    x = salves(60.0, fs)
    check("S01", "identité à gain 0", "", np.array_equal(shape_band(x, fs, gain_db=0.0), x))
    n2 = len(x) // 2
    a = shape_band(x, fs, gain_db=6.0)[:n2]; b = shape_band(x[:n2], fs, gain_db=6.0)
    check("S02", "causalité (troncature)", f"écart {np.max(np.abs(a - b)):.1e}", np.max(np.abs(a - b)) < 1e-9)
    b1 = shape_band(x, fs, gain_db=6.0, block=777); b2 = shape_band(x, fs, gain_db=6.0, block=1 << 22)
    check("S02", "indépendance à la taille des blocs", f"écart {np.max(np.abs(b1 - b2)):.1e}", np.max(np.abs(b1 - b2)) < 1e-9)
    # S03
    t = np.arange(int(fs * 2)) / fs; rng = np.random.default_rng(5)
    imp = np.zeros(len(t)); imp[::4800] = 1.0
    cas = {"silence": np.zeros(len(t)), "continu": np.full(len(t), 0.5), "carré": np.sign(np.sin(2 * np.pi * 100 * t)), "impulsions": imp,
           "blanc": np.clip(rng.standard_normal(len(t)), -1, 1), "−140 dB": rng.standard_normal(len(t)) * 1e-7}
    ok = True; pire = 0.0
    for nom, s in cas.items():
        for p in (dict(shape="bell", f0=20.0, q=0.1), dict(shape="bell", f0=20000.0, q=20.0), dict(shape="highshelf", f0=8000.0, q=0.7), dict(shape="lowshelf", f0=200.0, q=0.7)):
            for tg in ("transitoires", "sustain"):
                for g in (-24.0, 24.0):
                    y = shape_band(s, fs, cible=tg, gain_db=g, **p)
                    fin = np.all(np.isfinite(y)); pire = max(pire, np.max(np.abs(y)) if fin else 99)
                    bon = fin and np.max(np.abs(y)) <= (2.0 if g < 0 else 1.5) * max(np.max(np.abs(s)), 1e-9) * (10 ** (24 / 20) if g > 0 else 1.0)
                    if nom == "silence": bon &= bool(np.all(y == 0))
                    if not bon and ok: pire_cas = (nom, p, tg, g, float(np.max(np.abs(y))), float(np.max(np.abs(s))))
                    ok &= bon
    check("S03", "cas extrêmes × paramètres extrêmes", f"|y| max {pire:.2f}" + ("" if ok else f" ; 1er cas fautif {pire_cas}"), ok)
    # S04 précision
    for f0 in (60.0, 250.0, 1000.0, 4000.0):
        x = salves(f0, fs)
        for tg in ("transitoires", "sustain"):
            for g in (+6.0, -6.0):
                y = shape_band(x, fs, cible=tg, f0=f0, gain_db=g)
                a, s = mesures(x, y, f0, fs)
                cible, autre = (a, s) if tg == "transitoires" else (s, a)
                check("S04", f"précision {f0:5.0f} Hz, {tg} {g:+.0f} dB", f"cible {cible:+.1f} dB, autre {autre:+.1f} dB", abs(cible - g) <= 1.5 and abs(autre) <= 1.0)
    # S05 niveau / S06 fréquence d'échantillonnage
    x = salves(250.0, fs); rs = []
    for db in (-40, -20, 0, 6):
        s_ = x * 10 ** (db / 20); rs.append(mesures(s_, shape_band(s_, fs, cible="transitoires", f0=250.0, gain_db=6.0), 250.0, fs)[0])
    check("S05", "niveau d'entrée −40…+6 dB", f"dispersion {max(rs) - min(rs):.2f} dB", max(rs) - min(rs) <= 0.3)
    rs = []
    for f_s in (44100.0, 48000.0, 96000.0):
        x_ = salves(250.0, f_s); rs.append(mesures(x_, shape_band(x_, f_s, cible="transitoires", f0=250.0, gain_db=6.0), 250.0, f_s)[0])
    check("S06", "fréquence d'échantillonnage 44,1/48/96 kHz", f"{['%+.1f' % r for r in rs]}", max(rs) - min(rs) <= 0.5)
    # S07 transparence sur signal établi
    tt = np.arange(int(fs * 3)) / fs; st = 0.5 * np.sin(2 * np.pi * 250.0 * tt)
    yT = shape_band(st, fs, cible="transitoires", f0=250.0, gain_db=6.0); yS = shape_band(st, fs, cible="sustain", f0=250.0, gain_db=6.0)
    sl = slice(int(fs), None)
    dT = 20 * np.log10(np.std(lfilter(*zone_filter("bell", fs, 250.0, 1.0), yT)[sl]) / np.std(lfilter(*zone_filter("bell", fs, 250.0, 1.0), st)[sl]))
    dS = 20 * np.log10(np.std(lfilter(*zone_filter("bell", fs, 250.0, 1.0), yS)[sl]) / np.std(lfilter(*zone_filter("bell", fs, 250.0, 1.0), st)[sl]))
    check("S07", "signal établi : transitoires (≈ 0) / sustain (≈ +6)", f"{dT:+.2f} / {dS:+.2f} dB", abs(dT) <= 0.1 and abs(dS - 6.0) <= 0.3)
    # S08 débordement spectral : un gain qui change plus vite que la bande ne peut suivre crée un clic HORS bande
    from scipy.signal import butter, sosfilt
    pire8, ok8 = -99.0, True
    for f0 in (60.0, 250.0, 1000.0, 4000.0):
        x = salves(f0, fs)
        y = shape_band(x, fs, cible="transitoires", f0=f0, gain_db=12.0)
        d = y - x
        ein = np.sum(sosfilt(butter(4, [f0 / 2, f0 * 2], btype="band", fs=fs, output="sos"), d) ** 2)
        r = 10 * np.log10(max(np.sum(d ** 2) - ein, 1e-30) / ein)
        pire8 = max(pire8, r - (0.0 if f0 >= 250 else -5.0) if False else r); ok8 &= r <= (-25.0 if f0 >= 250 else -20.0)
    check("S08", "débordement hors bande (transitoires +12 dB, 4 fréquences)", f"pire {pire8:.1f} dB (limite −25 ; −20 sous 250 Hz)", ok8)
    # S09 partition de l'unité
    ok9, pire9 = True, 0.0
    for f0 in (60.0, 1000.0):
        x = salves(f0, fs)
        y = shape_band(x, fs, cible="transitoires", f0=f0, gain_db=6.0) + shape_band(x, fs, cible="sustain", f0=f0, gain_db=6.0) - x
        bx, by = (lfilter(*zone_filter("bell", fs, f0, 1.0), z) for z in (x, y))
        r = 10 * np.log10(np.sum(by[int(0.2 * fs):] ** 2) / np.sum(bx[int(0.2 * fs):] ** 2))
        pire9 = max(pire9, abs(r - 6.0)); ok9 &= abs(r - 6.0) <= 0.3
    check("S09", "partition de l'unité (transitoires + sustain = +6 statique)", f"écart max {pire9:.2f} dB", ok9)
    # S10 bipolaire
    x = salves(250.0, fs)
    ap, _ = mesures(x, shape_band(x, fs, cible="transitoires", f0=250.0, gain_db=+6.0), 250.0, fs)
    am, _ = mesures(x, shape_band(x, fs, cible="transitoires", f0=250.0, gain_db=-6.0), 250.0, fs)
    check("S10", "bipolaire : symétrie transitoires +6 / −6", f"{ap:+.1f} / {am:+.1f} dB", 0.7 <= abs(am) / max(abs(ap), 1e-9) <= 1.4)
    # S11 deux bandes
    for f0 in (60.0, 250.0, 1000.0):
        x = salves(f0, fs)
        y = shape_band(x, fs, cible="transitoires", f0=f0, gain_db=6.0) + shape_band(x, fs, cible="sustain", f0=f0, gain_db=-6.0) - x
        a, s = mesures(x, y, f0, fs)
        check("S11", f"deux bandes à {f0:5.0f} Hz (transitoires +6 & sustain −6)", f"attaque {a:+.1f}, sustain {s:+.1f} dB", abs(a - 6.0) <= 2.0 and abs(s + 6.0) <= 2.0)
    # S12 plancher de bruit
    n = int(fs * 3); pl = np.random.default_rng(9).standard_normal(n) * 10 ** (-60 / 20)
    y = shape_band(pl, fs, cible="transitoires", f0=250.0, gain_db=6.0)
    bp = lambda z: lfilter(*zone_filter("bell", fs, 250.0, 1.0), z)[int(0.5 * fs):]
    d = 10 * np.log10(np.sum(bp(y) ** 2) / np.sum(bp(pl) ** 2))
    check("S12", "plancher de bruit seul, dans la bande (transitoires +6 dB)", f"{d:+.2f} dB", abs(d) <= 0.5)
    # S13 durée : le poids retombe en `durée` (≥ 90 % à t = durée, ≥ 50 % à t = 0,3·durée) ; la sensibilité et le niveau n'y changent rien
    for tm in (20.0, 60.0, 200.0):
        x = salves(1000.0, fs)
        y, d = shape_band(x, fs, cible="transitoires", f0=1000.0, gain_db=12.0, time_ms=tm, diag=True)
        e = (d["g"] - 1.0) / (10 ** (12 / 20) - 1.0)
        i0 = int(0.1 * fs); pk = np.max(e[i0:i0 + int(0.05 * fs)])
        e_dur = e[i0 + int(tm / 1000 * fs)] / pk; e_03 = e[i0 + int(0.3 * tm / 1000 * fs)] / pk
        check("S13", f"durée {tm:5.0f} ms : reste à t = durée / à 0,3·durée", f"{e_dur:.2f} / {e_03:.2f}", e_dur <= 0.12 and 0.3 <= e_03 <= 0.95)
    # S14 sensibilité : sur un FOND soutenu (comme dans la musique), une attaque vive (0,3 ms, +0,3) et un gonflement lent (25 ms, +0,6 : plus fort)
    n = int(fs * 2)
    fond = 0.05 * np.sin(2 * np.pi * 1000.0 * np.arange(n) / fs)
    def evt(rise, amp):
        z = np.zeros(n); i = int(0.5 * fs); m_ = int(0.4 * fs)
        env = np.minimum(np.arange(m_) / (rise * fs), 1.0) * np.exp(-np.arange(m_) / (0.15 * fs))
        z[i:i + m_] = amp * env * np.sin(2 * np.pi * 1000.0 * np.arange(m_) / fs)
        return fond + z
    res = {}
    for sens in (0.3, 0.9):
        for nom, xs in (("vive", evt(0.0003, 0.3)), ("lente", evt(0.025, 0.6))):
            _, d = shape_band(xs, fs, cible="transitoires", f0=1000.0, gain_db=12.0, sens=sens, diag=True)
            res[(sens, nom)] = np.max(((d["g"] - 1.0) / (10 ** (12 / 20) - 1.0))[int(0.45 * fs):int(1.0 * fs)])
    check("S14", "sensibilité 30 % : la vive déclenche, la lente (plus forte) non", f"vive {res[(0.3,'vive')]:.2f} ; lente {res[(0.3,'lente')]:.2f}", res[(0.3, "vive")] >= 0.8 and res[(0.3, "lente")] <= 0.2)
    check("S14", "sensibilité 90 % : les deux déclenchent", f"vive {res[(0.9,'vive')]:.2f} ; lente {res[(0.9,'lente')]:.2f}", res[(0.9, "vive")] >= 0.8 and res[(0.9, "lente")] >= 0.3)
    nf = sum(1 for o in RES if not o)
    print(f"\n{len(RES) - nf}/{len(RES)} réussis, {nf} échec(s)")
    return nf


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
