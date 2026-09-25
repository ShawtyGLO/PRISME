"""Exporte les vecteurs de référence du prototype pour les tests C++ (PRISME/tests/refs/).

Fichiers : <nom>.in.f64 / <nom>.out.f64 (float64 brut, mono) + manifest.txt (une ligne par test).
  lift  <nom> <fs> <forme> <f0> <q> <gain_db> <amount> <release_ms>
  shape <nom> <fs> <forme> <f0> <q> <gain_db> <cible> <time_ms(0=défaut)> <sens>
  zone  <nom> <fs> <forme> <f0> <q> <b0> <b1> <b2> <a1> <a2>
Lancer :  python _proto/export_refs.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(HERE, "_libs"))
sys.path.insert(0, HERE)
import numpy as np
from render import load
from bench_leak import SRC
from prisme_band import zone_filter
from prisme_lift import lift_band
from prisme_shape import shape_band

OUT = os.path.join(HERE, "..", "PRISME", "tests", "refs")
os.makedirs(OUT, exist_ok=True)
man = []


def dump(nom, x, y):
    np.asarray(x, dtype="<f8").tofile(os.path.join(OUT, nom + ".in.f64"))
    np.asarray(y, dtype="<f8").tofile(os.path.join(OUT, nom + ".out.f64"))


def synth(fs, dur=6.0, seed=7):
    """Rafales de sinus de niveaux variés séparées de silence, sur un lit de bruit très bas, puis un passage de bruit rose fort."""
    rng = np.random.default_rng(seed)
    n = int(fs * dur)
    x = np.zeros(n)
    t = np.arange(int(0.3 * fs)) / fs
    for k, (f, L) in enumerate([(1000, -60), (250, -45), (3000, -35), (8000, -50), (60, -25), (1000, -12), (5000, -55)]):
        i = int((0.2 + k * 0.6) * fs)
        x[i:i + len(t)] += 10 ** (L / 20) * np.sin(2 * np.pi * f * t)
    x += rng.standard_normal(n) * 10 ** (-80 / 20)
    x[int(4.6 * fs):] += rng.standard_normal(n - int(4.6 * fs)) * 10 ** (-38 / 20)
    return x


fs0, mus = load(SRC)
mus = np.ascontiguousarray(mus[int(30 * fs0): int(33 * fs0), 0])
CFG = [("bell", 1000.0, 1.0, 12.0, 60.0, 150.0), ("highshelf", 8000.0, 0.7, 6.0, 60.0, 150.0), ("lowshelf", 100.0, 0.7, -9.0, 40.0, 300.0),
       ("bell", 250.0, 0.7, 6.0, 80.0, 50.0), ("bell", 3000.0, 2.0, -6.0, 100.0, 150.0), ("highshelf", 12000.0, 0.7, 9.0, 30.0, 1000.0)]
for fs, nom_sig, sig in ((int(fs0), "mus", mus), (44100, "syn44", synth(44100)), (96000, "syn96", synth(96000)), (48000, "syn48", synth(48000))):
    for i, (sh, f0, q, g, am, rel) in enumerate(CFG):
        nom = f"lift_{nom_sig}_{i}"
        y = lift_band(sig, fs, sh, f0, q, g, am, rel, block=8192)
        dump(nom, sig, y)
        man.append(f"lift {nom} {fs} {sh} {f0} {q} {g} {am} {rel}")
SCFG = [("transitoires", "bell", 60.0, 1.0, 6.0, 0.0, 0.85), ("sustain", "bell", 250.0, 1.0, -6.0, 80.0, 0.5), ("transitoires", "highshelf", 8000.0, 0.7, 6.0, 30.0, 0.9),
        ("sustain", "lowshelf", 120.0, 0.7, 6.0, 200.0, 0.3), ("transitoires", "bell", 3000.0, 2.0, -6.0, 5.0, 1.0)]
for fs, nom_sig, sig in ((int(fs0), "mus", mus), (44100, "syn44", synth(44100)), (96000, "syn96", synth(96000))):
    for i, (cb, sh, f0, q, g, tm, sens) in enumerate(SCFG):
        nom = f"shape_{nom_sig}_{i}"
        y = shape_band(sig, fs, cb, sh, f0, q, g, block=8192, time_ms=(tm or None), sens=sens)
        dump(nom, sig, y)
        man.append(f"shape {nom} {fs} {sh} {f0} {q} {g} {cb} {tm} {sens}")
for fs in (44100, 48000, 88200, 96000, 192000):
    for sh in ("bell", "highshelf", "lowshelf"):
        for f0, q in ((20.0, 0.3), (42.0, 0.71), (1000.0, 1.0), (9600.0, 12.0), (18000.0, 0.7)):
            b, a = zone_filter(sh, fs, f0, q)
            man.append(f"zone z_{fs}_{sh}_{f0:g} {fs} {sh} {f0} {q} " + " ".join(f"{v:.17g}" for v in (b[0], b[1], b[2], a[1], a[2])))
open(os.path.join(OUT, "manifest.txt"), "w", encoding="utf-8").write("\n".join(man) + "\n")
print(len(man), "références écrites dans", os.path.abspath(OUT))
