"""Exporte les vecteurs de référence du prototype pour les tests C++ (PRISME/tests/refs/).

Fichiers : <nom>.in.f64 / <nom>.out.f64 (float64 brut, mono) + manifest.txt (une ligne par test).
  lift  <nom> <fs> <forme> <f0> <q> <gain_db> <amount> <release_ms>
  shape <nom> <fs> <forme> <f0> <q> <gain_db> <cible> <time_ms(0=défaut)> <sens>
  exciter <nom> <fs> <forme> <f0> <q> <gain_db> <mode> <source>   (sortie = delta aligné sur l'entrée retardée de 20)
  shape : sortie brute de Shape5 = x + (g−1)·b(n−192)  (voir prisme_shape5.py)
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
from prisme_shape5 import Shape5
from prisme_exciter_stream import exciter_stream, H0, H_UP
from prisme_tame import tame_band
from prisme_exciter_v2_stream import exciter_v2_stream
from prisme_exciter_v3_stream import exciter_v3_stream

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
        s5 = Shape5(fs, cb, sh, f0, q, g, None, (tm or None), sens)                       # sortie brute : x + (g−1)·b retardé de la latence
        y = np.concatenate([s5.process(sig[k:k + 8192]) for k in range(0, len(sig), 8192)])
        dump(nom, sig, y)
        man.append(f"shape {nom} {fs} {sh} {f0} {q} {g} {cb} {tm} {sens}")
# tables de coefficients (FIR du suréchantillonnage) : les MÊMES nombres que le prototype
TAB = os.path.join(HERE, "..", "PRISME", "Source", "Dsp", "Tables.h")
with open(TAB, "w", encoding="utf-8") as f:
    f.write("// GÉNÉRÉ par _proto/export_refs.py — ne pas éditer. FIR de resample_poly(x, 2, 1) : firwin(41, 0.5, kaiser 5).NL#pragma once NLNLnamespace prisme::tables NL{NL".replace("NL", chr(10)))
    for nom, v in (("h0", H0), ("hUp", H_UP)):
        f.write(f"inline constexpr double {nom}[41] = {{" + chr(10) + "    " + ("," + chr(10) + "    ").join(f"{x:.17g}" for x in v) + chr(10) + "};" + chr(10))
    f.write("}" + chr(10))
ECFG = [("iron", "auto", "bell", 12000.0, 2.0, 5.0), ("iron", "auto", "highshelf", 9600.0, 0.71, 5.0), ("triode", "auto", "bell", 2500.0, 1.0, 6.0),
        ("diode", "band", "bell", 3000.0, 1.0, 5.0), ("classa", "auto", "lowshelf", 80.0, 0.71, 4.0), ("rect", "auto", "bell", 250.0, 1.0, 5.0),
        ("iron", "band", "highshelf", 8000.0, 0.71, 6.0), ("iron", "auto", "bell", 5000.0, 1.5, -5.0),
        ("iron", "band", "bell", 3000.0, 1.0, 4.0, 1.5, 0.8), ("triode", "band", "lowshelf", 200.0, 0.71, 4.0, 3.0, -0.6), ("rect", "auto", "bell", 1000.0, 1.0, 5.0, 0.6, 0.0),
        ("rect", "auto", "bell", 1000.0, 1.0, 5.0, 4.0, 0.0), ("classa", "auto", "highshelf", 6000.0, 0.71, 3.0, 4.0, 0.0), ("diode", "band", "highshelf", 5000.0, 0.71, 3.0, 0.5, 1.0)]
for fs, nom_sig, sig in ((int(fs0), "mus", mus), (44100, "syn44", synth(44100)), (96000, "syn96", synth(96000))):
    for i, cfg in enumerate(ECFG):
        mo, so, sh, f0, q, g = cfg[:6]
        dr, tl = (cfg[6], cfg[7]) if len(cfg) > 6 else (1.5, 0.0)
        nom = f"exc_{nom_sig}_{i}"
        y = exciter_stream(sig, fs, block=8192, shape=sh, f0=f0, q=q, gain_db=g, mode=mo, source=so, drive=dr, tilt=tl)
        dump(nom, sig, y)
        man.append(f"exciter {nom} {fs} {sh} {f0} {q} {g} {mo} {so} {dr} {tl}")
E2CFG = [("mordant_chaud", "auto", "bell", 3000.0, 0.71, 6.0, 2.5, 0.0), ("doux", "auto", "bell", 1000.0, 1.0, 8.0, 1.5, 0.0), ("chaud", "auto", "highshelf", 9600.0, 0.71, 5.0, 3.0, 0.0),
         ("mordant", "auto", "lowshelf", 200.0, 0.71, 6.0, 2.5, 0.0), ("mordant_chaud", "band", "bell", 3000.0, 1.0, 6.0, 2.5, 0.7), ("mordant", "band", "highshelf", 8000.0, 0.71, 6.0, 4.0, -0.5),
         ("mordant_chaud", "auto", "bell", 3000.0, 0.71, 6.0, 2.5, 0.0, 0.0), ("mordant_chaud", "auto", "bell", 3000.0, 0.71, 6.0, 2.5, 0.0, 0.5), ("doux", "auto", "highshelf", 9600.0, 0.71, 6.0, 2.0, 0.0, 0.25)]
for fs, nom_sig, sig in ((int(fs0), "mus", mus), (44100, "syn44", synth(44100)), (96000, "syn96", synth(96000))):
    for i, cfg in enumerate(E2CFG):
        pr, so, sh, f0, q, g, dr, tl = cfg[:8]
        dn = cfg[8] if len(cfg) > 8 else 1.0
        nom = f"exc2_{nom_sig}_{i}"
        y = exciter_v2_stream(sig, fs, block=8192, shape=sh, f0=f0, q=q, gain_db=g, profil=pr, source=so, drive=dr, tilt=tl, dens=dn)
        dump(nom, sig, y)
        man.append(f"exciter2 {nom} {fs} {sh} {f0} {q} {g} {pr} {so} {dr} {tl} {dn}")
E3CFG = [("mordant_chaud", "bell", 3000.0, 0.71, 6.0, 2.5, 0.0, 0.0), ("doux", "bell", 1000.0, 1.0, 8.0, 1.5, 0.0, 0.5), ("chaud", "highshelf", 9600.0, 0.71, 5.0, 3.0, 0.6, 0.0),
         ("mordant", "lowshelf", 120.0, 0.71, 6.0, 2.5, -0.5, 0.2), ("mordant_chaud", "bell", 5000.0, 2.0, 12.0, 6.0, 0.0, 1.0)]
for fs, nom_sig, sig in ((int(fs0), "mus", mus), (44100, "syn44", synth(44100)), (96000, "syn96", synth(96000))):
    for i, (pr, sh, f0, q, g, dr, tl, pu) in enumerate(E3CFG):
        nom = f"exc3_{nom_sig}_{i}"
        y = exciter_v3_stream(sig, fs, block=8192, shape=sh, f0=f0, q=q, gain_db=g, profil=pr, drive=dr, tilt=tl, purete=pu)
        dump(nom, sig, y)
        man.append(f"exciter3 {nom} {fs} {sh} {f0} {q} {g} {pr} {dr} {tl} {pu}")
TCFG = [("bell", 3000.0, 0.7, -9.0, 0.5), ("bell", 632.0, 1.2, -4.0, 1.0), ("bell", 250.0, 0.71, 6.0, 0.2), ("highshelf", 9600.0, 0.71, -6.0, 0.5),
        ("lowshelf", 120.0, 0.71, -6.0, 0.8), ("bell", 8000.0, 2.0, -9.0, 0.0)]
for fs, nom_sig, sig in ((int(fs0), "mus", mus[:int(2 * fs0)]), (44100, "syn44", synth(44100)[:int(4 * 44100)]), (96000, "syn96", synth(96000)[:int(3 * 96000)])):
    for i, (sh, f0, q, g, wd) in enumerate(TCFG):
        nom = f"tame_{nom_sig}_{i}"
        y = tame_band(sig, fs, shape=sh, f0=f0, q=q, gain_db=g, width=wd, block=8192)
        dump(nom, sig, y)
        man.append(f"tame {nom} {fs} {sh} {f0} {q} {g} {wd}")
for fs, nom_sig, sig in ((int(fs0), "mus", mus[:int(2 * fs0)]), (44100, "syn44", synth(44100)[:int(4 * 44100)])):         # zone « raide » (option, exposant 2)
    for i, (sh, f0, q, g, wd) in enumerate((("bell", 120.0, 4.0, -9.0, 0.5), ("lowshelf", 150.0, 0.71, -6.0, 0.8), ("bell", 3000.0, 2.0, -9.0, 0.3))):
        nom = f"tamezr_{nom_sig}_{i}"
        y = tame_band(sig, fs, shape=sh, f0=f0, q=q, gain_db=g, width=wd, block=8192, zone_pente=2.0)
        dump(nom, sig, y)
        man.append(f"tame {nom} {fs} {sh} {f0} {q} {g} {wd} 2.0")
from prisme_engine_stream import traite, LATENCE as LAT_ENG
from prisme_filtres import applique
from tests_engine import config as config_type
cfg2 = config_type()
cfg2[0].update(type="lift", cible=None, gain_db=6.0, amount=70.0, canal="stereo")
cfg2[1].update(type="exciter", gain_db=5.0, profil="chaud", purete=0.4, canal="left")
cfg2[2].update(type="lift", gain_db=-6.0, amount=60.0, release_ms=300.0, canal="side")
cfg2[3].update(type="tame", gain_db=4.0, width=0.3, canal="right")
cfg2[4].update(type="shape", cible="sustain", gain_db=-4.0, time_ms=None, canal="mid")
cfg3 = config_type()
cfg3[0].update(type="tame", gain_db=-6.0, width=0.5, canal="stereo", link=0.5)
cfg3[1].update(type="tame", shape="highshelf", f0=8000.0, gain_db=-4.0, width=0.3, canal="stereo", link=1.0)
cfg3[2].update(type="lift", gain_db=5.0, amount=80.0, canal="stereo", link=0.3)
cfg3[3].update(type="shape", cible="sustain", gain_db=-4.0, canal="stereo", link=0.8)
cfg3[4].update(type="tame", gain_db=-3.0, canal="stereo", link=0.0)
xs_full = load(SRC)[1]
xstereo = np.ascontiguousarray(xs_full[int(30 * fs0): int(32 * fs0)])
np.asarray(np.ascontiguousarray(xs_full[int(30 * fs0): int(42 * fs0)]), dtype="<f8").tofile(os.path.join(OUT, "music12.f64"))     # 12 s stéréo entrelacées : test de préchauffage
cfg4 = config_type()
cfg4[0].update(lc_on=True, lc_f=40.0, lc_pente=24)
cfg4[1].update(hc_on=True, hc_f=3000.0, hc_pente=12)
cfg4[2].update(lc_on=True, lc_f=300.0, lc_pente=12, hc_on=True, hc_f=2500.0, hc_pente=24)
cfg4[4].update(lc_on=True, lc_f=6000.0, lc_pente=24, hc_on=True, hc_f=15000.0, hc_pente=12)
cfg5 = config_type()
cfg5[0].update(type="tame", gain_db=-6.0, canal="stereo", link=0.5, st_width=0.0)
cfg5[1].update(type="lift", gain_db=5.0, amount=80.0, canal="stereo", link=0.3, st_width=2.0)
cfg5[2].update(type="shape", gain_db=4.0, canal="stereo", link=0.0, st_width=0.4)
cfg5[3].update(type="tame", gain_db=-4.0, canal="stereo", link=1.0, st_width=1.6)
cfg5[4].update(type="exciter", gain_db=5.0, canal="stereo", st_width=0.3)        # l'Exciter (delta mono) ignore le curseur
for nom, cfg in (("type", config_type()), ("variee", cfg2), ("liee", cfg3), ("filtres", cfg4), ("largeur", cfg5)):
    y = traite(xstereo, int(fs0), cfg)
    filt = {i: [("lc", s["lc_f"], s["lc_pente"]) if s.get("lc_on") else None, ("hc", s["hc_f"], s["hc_pente"]) if s.get("hc_on") else None]
            for i, s in enumerate(cfg) if s.get("on", True) and s["gain_db"] != 0.0 and (s.get("lc_on") or s.get("hc_on"))}
    if filt:                                                   # bandes indépendantes : delta_i = traite(bande i seule) − sec retardé
        D = LAT_ENG
        sec = np.concatenate([np.zeros((D, 2)), xstereo[:-D]])
        deltas = {i: traite(xstereo, int(fs0), [s]) - sec for i, s in enumerate(cfg) if s.get("on", True) and s["gain_db"] != 0.0}
        y = applique(sec, deltas, filt, int(fs0))
    np.asarray(xstereo, dtype="<f8").tofile(os.path.join(OUT, f"engine_{nom}.in.f64"))
    np.asarray(y, dtype="<f8").tofile(os.path.join(OUT, f"engine_{nom}.out.f64"))
    with open(os.path.join(OUT, f"engine_{nom}.cfg"), "w", encoding="utf-8") as f:
        for s in cfg:
            f.write(" ".join(str(v) for v in (int(s.get("on", True)), s["type"], s["shape"], s["f0"], s["q"], s["gain_db"], s.get("canal", "stereo"), s.get("profil", "mordant_chaud"),
                                            s.get("source", "auto"), s.get("width", 0.5), s.get("cible") or "transitoires", s.get("time_ms") or 0.0, s.get("sens", 0.85),
                                            s.get("amount", 50.0), s.get("release_ms", 150.0), s.get("link", 0.5), s.get("purete", 0.0), int(s.get("lc_on", False)), s.get("lc_f", 20.0), s.get("lc_pente", 12), int(s.get("hc_on", False)), s.get("hc_f", 20000.0), s.get("hc_pente", 12), s.get("st_width", 1.0))) + "\n")
    man.append(f"engine engine_{nom} {int(fs0)} x 0 0")
# compensation de sonie : entrée [sec, traité] entrelacés, sortie [traité corrigé, gain dB]
from prisme_sonie import sonie_band
sec_s = np.concatenate([np.zeros((LAT_ENG, 2)), xstereo[:-LAT_ENG]])
wet_s = traite(xstereo, int(fs0), config_type())
for nom, fs_, sec_, wet_ in (("musique", int(fs0), sec_s, wet_s),
                              ("silence_saut", 44100, np.concatenate([xstereo[:44100], np.zeros((30000, 2)), xstereo[44100:88200]]), None)):
    if wet_ is None:
        wet_ = sec_ * 1.7
        wet_[60000:] *= 0.6
    out_, g_ = sonie_band(sec_, wet_, fs_)
    np.concatenate([sec_, wet_], axis=1).astype("<f8").tofile(os.path.join(OUT, f"sonie_{nom}.in.f64"))
    np.concatenate([out_, g_[:, None]], axis=1).astype("<f8").tofile(os.path.join(OUT, f"sonie_{nom}.out.f64"))
    man.append(f"sonie sonie_{nom} {fs_} x 0 0")
for fs in (44100, 48000, 88200, 96000, 192000):
    for sh in ("bell", "highshelf", "lowshelf"):
        for f0, q in ((20.0, 0.3), (42.0, 0.71), (1000.0, 1.0), (9600.0, 12.0), (18000.0, 0.7)):
            b, a = zone_filter(sh, fs, f0, q)
            man.append(f"zone z_{fs}_{sh}_{f0:g} {fs} {sh} {f0} {q} " + " ".join(f"{v:.17g}" for v in (b[0], b[1], b[2], a[1], a[2])))
open(os.path.join(OUT, "manifest.txt"), "w", encoding="utf-8").write("\n".join(man) + "\n")
print(len(man), "références écrites dans", os.path.abspath(OUT))
