"""Banc 2026-10-01 : l'analyse partagée est-elle rentable avec Lift + Shape en plus du Tame ? (qualité + CPU, Python)"""
import time
import numpy as np
from scipy.signal import lfilter, butter
import prisme_tame as t4
import prisme_lift as l4
import prisme_shape as s4
import prisme_tame5 as t5
import prisme_lift5_shape5 as ls5

fs = 48000
rng = np.random.default_rng(3)
DUR = 10.0
n = int(DUR * fs)
t = np.arange(n) / fs


def env_decay(ts, tau, length):
    e = np.zeros(n)
    i = int(ts * fs)
    k = np.arange(min(int(length * fs), n - i))
    e[i:i + len(k)] = np.exp(-k / (tau * fs))
    return e


# --- signal de test : nappe tonale (changements de notes hors temps de batterie) + batterie
pad = np.zeros(n)
notes = [(110, 165, 220), (98, 147, 196), (123.5, 185, 247), (87.3, 131, 175)]
bounds = [0.0, 2.37, 4.87, 7.37, DUR]
drums_t = {"kick": [], "snare": [], "hat": []}
for k in range(4):
    a, b = int(bounds[k] * fs), int(bounds[k + 1] * fs)
    seg = np.zeros(b - a)
    tt = np.arange(b - a) / fs
    for f in notes[k]:
        for h in range(1, 9):
            seg += np.sin(2 * np.pi * f * h * tt) / h ** 1.2
    att = np.minimum(tt / 0.02, 1.0)                             # attaque de note de 20 ms
    pad[a:b] = 0.05 * seg * att
drum = np.zeros(n)
for beat in np.arange(0.5, DUR - 0.5, 0.5):
    i = int(beat * fs)
    L = int(0.3 * fs)
    tk = np.arange(L) / fs
    f_inst = 50 + 100 * np.exp(-tk / 0.03)
    kick = np.sin(2 * np.pi * np.cumsum(f_inst) / fs) * np.exp(-tk / 0.12) + 0.6 * rng.standard_normal(L) * np.exp(-tk / 0.003)
    drum[i:i + L] += 0.5 * kick
    drums_t["kick"].append(beat)
    if int(round(beat / 0.5)) % 2 == 0:
        sn = rng.standard_normal(L) * np.exp(-tk / 0.07) + 0.5 * np.sin(2 * np.pi * 200 * tk) * np.exp(-tk / 0.05)
        drums_t["snare"].append(beat + 0.25)
        k0 = int((beat + 0.25) * fs)
        drum[k0:k0 + L] += 0.3 * sn
    j = int((beat + 0.125) * fs)
    if j + int(0.1 * fs) < n:
        hat = lfilter(*butter(2, 7000 / (fs / 2), "high"), rng.standard_normal(int(0.1 * fs))) * np.exp(-np.arange(int(0.1 * fs)) / (0.02 * fs))
        drum[j:j + len(hat)] += 0.15 * hat
        drums_t["hat"].append(beat + 0.125)
x = (pad + drum).astype(np.float64)
x /= np.abs(x).max() / 0.7
note_t = [2.37, 4.87, 7.37]


def run_blocks(f, x, block=8192):
    out = []
    for i in range(0, len(x), block):
        out.append(f(x[i:i + block]))
    return np.concatenate(out)


def poids(g, A):
    return (g - 1.0) / (A - 1.0)


def stat(w, times, win=(0.0, 0.04)):
    return np.array([w[int((tm + win[0]) * fs):int((tm + win[1]) * fs)].max() for tm in times])


# =============== QUALITÉ SHAPE : transitoires en bell 5 kHz (charleston/caisse claire) et bell 200 Hz (pied, corps de caisse claire, notes graves)
print("== QUALITÉ SHAPE (cible transitoires, +9 dB ; poids max dans les 40 ms après un événement)")
for nom, f0, evts in (("5 kHz", 5000.0, ("hat", "snare")), ("200 Hz", 200.0, ("kick", "snare"))):
    A = 10 ** (9.0 / 20)
    s = s4.Shape(fs, "transitoires", "bell", f0, 0.7, 9.0)
    ys, g4 = [], []
    for i in range(0, n, 8192):
        y, g = s.process(x[i:i + 8192], keep=True)
        g4.append(g)
    w4 = poids(np.concatenate(g4), A)
    ana = t5.AnalysePartagee(fs)
    s5 = ls5.Shape5(fs, ana.f, "transitoires", "bell", f0, 0.7, 9.0)
    g5 = []
    for i in range(0, n, 8192):
        xb = x[i:i + 8192]
        out = ana.process(xb)
        y, g = s5.process(xb, out, ana, keep=True)
        g5.append(g)
    w5 = poids(np.concatenate(g5), A)
    print(" bell %s :" % nom)
    for lab, w in (("v4", w4), ("v5", w5)):
        txt = " ".join("%s %.2f" % (e, np.mean(stat(w, drums_t[e]))) for e in evts)
        print("   %s  percussions : %s | début de NOTE (faux) : %.2f | poids moyen hors événements : %.3f" % (lab, txt, np.mean(stat(w, note_t, (0.0, 0.1))), w[(t > 1.0)].mean()))

# =============== QUALITÉ LIFT : ambiance faible sous une partie forte -> relevé ; mesure : gain sur un passage faible vs fort
print("== QUALITÉ LIFT (bell 1 kHz, +9 dB, Amount 50)")
sig = lfilter(*butter(2, [600 / (fs / 2), 1700 / (fs / 2)], "band"), rng.standard_normal(n))
amp = np.where((t % 4.0) < 2.0, 0.2, 0.01)                         # fort 2 s / faible 2 s (-26 dB)
amp = lfilter([1 - np.exp(-1 / (0.02 * fs))], [1, -np.exp(-1 / (0.02 * fs))], amp)
xl = 0.5 * sig / sig.std() * amp
for lab, build in (("v4 (seuil absolu)", "v4"), ("v5 (seuil relatif)", "v5")):
    if build == "v4":
        l = l4.Lift(fs, "bell", 1000.0, 1.0, 9.0, 50.0)
        gs = np.concatenate([l.process(xl[i:i + 8192], keep=True)[1] for i in range(0, n, 8192)])
    else:
        ana = t5.AnalysePartagee(fs)
        l = ls5.Lift5(fs, ana.f, "bell", 1000.0, 1.0, 9.0, 50.0)
        gs = []
        for i in range(0, n, 8192):
            xb = xl[i:i + 8192]
            gs.append(l.process(xb, ana.process(xb), ana, keep=True)[1])
        gs = np.concatenate(gs)
    gdb = 20 * np.log10(gs)
    fort = gdb[(t > 8.5) & (t < 9.8)].mean()
    faible = gdb[(t > 6.2) & (t < 7.8)].mean()
    print("   %s : gain moyen sur passage fort %.1f dB, sur passage faible %.1f dB" % (lab, fort, faible))
# même passage faible 20 dB plus bas (très bas niveau absolu) : le seuil relatif doit relever pareil, l'absolu moins
xl2 = xl * 0.1
for lab, build in (("v4 (absolu)", "v4"), ("v5 (relatif)", "v5")):
    if build == "v4":
        l = l4.Lift(fs, "bell", 1000.0, 1.0, 9.0, 50.0)
        gs = np.concatenate([l.process(xl2[i:i + 8192], keep=True)[1] for i in range(0, n, 8192)])
    else:
        ana = t5.AnalysePartagee(fs)
        l = ls5.Lift5(fs, ana.f, "bell", 1000.0, 1.0, 9.0, 50.0)
        gs = []
        for i in range(0, n, 8192):
            xb = xl2[i:i + 8192]
            gs.append(l.process(xb, ana.process(xb), ana, keep=True)[1])
        gs = np.concatenate(gs)
    gdb = 20 * np.log10(gs)
    print("   morceau entier 20 dB plus bas, %s : gain passage fort %.1f, passage faible %.1f dB" % (lab, gdb[(t > 8.5) & (t < 9.8)].mean(), gdb[(t > 6.2) & (t < 7.8)].mean()))

# =============== CPU : 5 bandes = 2 Tame + 1 Lift + 2 Shape
print("== CPU (Python, 10 s, mono) : 2 Tame + 1 Lift + 2 Shape")
tame_cfg = [dict(f0=300.0, q=0.7, gain_db=-9.0, width=0.5), dict(f0=3500.0, q=0.7, gain_db=-9.0, width=0.5)]
x = x[:n]
tt0 = time.time()
for c in tame_cfg:
    t4.tame_band(x, fs, "bell", c["f0"], c["q"], c["gain_db"], c["width"])
tT4 = time.time() - tt0
tt0 = time.time(); l4.lift_band(x, fs, "bell", 1000.0, 1.0, 9.0, 50.0); tL4 = time.time() - tt0
tt0 = time.time(); s4.shape_band(x, fs, "transitoires", "bell", 200.0, 0.7, 9.0); s4.shape_band(x, fs, "transitoires", "bell", 5000.0, 0.7, 9.0); tS4 = time.time() - tt0
print("   v4 : Tame×2 %.2f + Lift %.2f + Shape×2 %.2f = %.2f s" % (tT4, tL4, tS4, tT4 + tL4 + tS4))

ana = t5.AnalysePartagee(fs)
tames = [t5.TameP(fs, ana.f, "bell", c["f0"], c["q"], c["gain_db"], c["width"], 4.5) for c in tame_cfg]
lift = ls5.Lift5(fs, ana.f, "bell", 1000.0, 1.0, 9.0, 50.0)
shps = [ls5.Shape5(fs, ana.f, "transitoires", "bell", f, 0.7, 9.0) for f in (200.0, 5000.0)]
tA = tTP = tLi = tSh = 0.0
for i in range(0, n, 8192):
    xb = x[i:i + 8192]
    a0 = time.time(); out = ana.process(xb); tA += time.time() - a0
    a0 = time.time()
    for tp in tames:
        tp.process(xb, out)
    tTP += time.time() - a0
    a0 = time.time(); lift.process(xb, out, ana); tLi += time.time() - a0
    a0 = time.time()
    for sp in shps:
        sp.process(xb, out, ana)
    tSh += time.time() - a0
print("   v5 : analyse %.2f + Tame×2 %.2f + Lift %.2f + Shape×2 %.2f = %.2f s" % (tA, tTP, tLi, tSh, tA + tTP + tLi + tSh))
