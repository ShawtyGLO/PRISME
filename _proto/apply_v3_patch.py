"""Branche l'Exciter v3 « Aural » : assemblages Python, C++ (ExciterV3.h, Engine, Params, processeur, interface), références et tests."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "PRISME")


def rd(p, base=HERE):
    return open(os.path.join(base, p), encoding="utf-8").read()


def wr(p, s, base=HERE):
    open(os.path.join(base, p), "w", encoding="utf-8").write(s)


def sub(s, old, new):
    assert old in s, old[:90]
    return s.replace(old, new, 1)


# ================================================================ Python : assemblages
e = rd("prisme_engine.py")
e = sub(e, "from prisme_exciter_v2_stream import excite_v2_aligne", "from prisme_exciter_v3_stream import excite_v3_aligne")
i = e.index("        # Exciter v2 : seuil relatif")
j = e.index("\n", e.index("tilt=spec.get(\"tilt\", 0.0))", i))
e = e[:i] + '''        # Exciter v3 « Aural » : zone saturée entière (+ Pureté), entrée MONO (lié : voir delta_bande)
        return lambda z: z + excite_v3_aligne(z, fs, shape=sh, f0=f0, q=q, gain_db=g, profil=spec.get("profil", "mordant_chaud"),
                                              drive=spec.get("drive", 2.5), tilt=spec.get("tilt", 0.0), purete=spec.get("purete", 0.0))''' + e[j:]
e = e.replace("# Exciter v2 : non-linéarité LIÉE", "# Exciter : non-linéarité LIÉE")
wr("prisme_engine.py", e)

s = rd("prisme_engine_stream.py")
s = sub(s, "from prisme_exciter_v2_stream import ExciterV2Stream", "from prisme_exciter_v3_stream import ExciterV3Stream")
i = s.index("            return ExciterV2Stream(")
j = s.index("\n", s.index("tilt=spec.get(\"tilt\", 0.0))", i))
s = s[:i] + '''            return ExciterV3Stream(self.fs, shape=sh, f0=f0, q=q, gain_db=g, profil=spec.get("profil", "mordant_chaud"),
                                   drive=spec.get("drive", 2.5), tilt=spec.get("tilt", 0.0), purete=spec.get("purete", 0.0))''' + s[j:]
wr("prisme_engine_stream.py", s)

# ================================================================ Références C++
x = rd("export_refs.py")
x = sub(x, "from prisme_exciter_v2_stream import exciter_v2_stream", "from prisme_exciter_v2_stream import exciter_v2_stream\nfrom prisme_exciter_v3_stream import exciter_v3_stream")
x = sub(x, "TCFG = [", '''E3CFG = [("mordant_chaud", "bell", 3000.0, 0.71, 6.0, 2.5, 0.0, 0.0), ("doux", "bell", 1000.0, 1.0, 8.0, 1.5, 0.0, 0.5), ("chaud", "highshelf", 9600.0, 0.71, 5.0, 3.0, 0.6, 0.0),
         ("mordant", "lowshelf", 120.0, 0.71, 6.0, 2.5, -0.5, 0.2), ("mordant_chaud", "bell", 5000.0, 2.0, 12.0, 6.0, 0.0, 1.0)]
for fs, nom_sig, sig in ((int(fs0), "mus", mus), (44100, "syn44", synth(44100)), (96000, "syn96", synth(96000))):
    for i, (pr, sh, f0, q, g, dr, tl, pu) in enumerate(E3CFG):
        nom = f"exc3_{nom_sig}_{i}"
        y = exciter_v3_stream(sig, fs, block=8192, shape=sh, f0=f0, q=q, gain_db=g, profil=pr, drive=dr, tilt=tl, purete=pu)
        dump(nom, sig, y)
        man.append(f"exciter3 {nom} {fs} {sh} {f0} {q} {g} {pr} {dr} {tl} {pu}")
TCFG = [''')
x = sub(x, 's.get("amount", 50.0), s.get("release_ms", 150.0), s.get("link", 0.5))) + "\\n")', 's.get("amount", 50.0), s.get("release_ms", 150.0), s.get("link", 0.5), s.get("purete", 0.0))) + "\\n")')
x = sub(x, 'cfg2[1].update(type="exciter", gain_db=5.0, mode="triode", source="band", canal="left")', 'cfg2[1].update(type="exciter", gain_db=5.0, profil="chaud", purete=0.4, canal="left")')
wr("export_refs.py", x)

# ================================================================ C++ : ExciterV3.h
wr("Source/Dsp/ExciterV3.h", '''// PRISME — Exciter v3 « Aural » (port de _proto/prisme_exciter_v3_stream.py ; prototype jugé « précis et naturel » par llg53, 2026-09-28).
//   source = zone de la bande [+ Tilt] → niveau lent S (τ 400 ms) → u = drive·b/S → ×2 (FIR 41) → courbe ADAA ordre 1 → ×1 ; y0 = y − f(0)
//   → wet = (y0 − pureté·c1·u)·S/(drive·c1) → filtre de la zone (1 section) → coupe-continu 20 Hz → × k, k = 10^(g/20) − 1.
//   c1 : gain du fondamental de la courbe pour un sinus d'amplitude drive (le fondamental du wet ≈ la zone : « +g dB » ≈ renfort de g dB).
// Entrée MONO (milieu : non-linéarité liée). LATENCE 20 échantillons. Aucune dépendance JUCE ; aucune allocation dans process().
#pragma once
#include "Biquad.h"
#include "Exciter.h"
#include "ExciterV2.h"      // ProfilExc
#include <algorithm>
#include <cmath>

namespace prisme
{
class ExciterV3
{
public:
    static constexpr int latence = 20;

    void prepare (double fs, Forme forme_, double f0_, double q, double gainDb, ProfilExc profil_, double drive_ = 2.5, double tilt = 0.0, double purete_ = 0.0)
    {
        profil = profil_;
        forme = forme_;
        f0 = f0_;
        fsHz = fs;
        purete = purete_;
        setGain (gainDb);
        src.set (zoneFilter (forme, fs, f0, q));
        out.set (zoneFilter (forme, fs, f0, q));
        cS = std::exp (-1.0 / (0.4 * fs));
        rDc = 1.0 - 2.0 * kPi * 20.0 / fs;
        setDrive (drive_);
        reset();
        setTilt (tilt);
    }

    void setGain (double gainDb) { k = std::pow (10.0, gainDb / 20.0) - 1.0; }        // en direct
    void setPurete (double p) { purete = p; }                                            // en direct

    void setDrive (double d)                                                             // en direct (recalcule c1)
    {
        drive = d;
        fz = curveF (0.0);
        double acc = 0.0;
        for (int i = 0; i < 256; ++i)
        {
            const double th = 2.0 * kPi * (double) i / 256.0, s = std::sin (th);
            acc += (curveF (drive * s) - fz) * s;
        }
        c1 = std::max (2.0 * acc / 256.0 / drive, 1e-6);
    }

    void setTilt (double t)                                                              // en direct
    {
        if (std::abs (t) <= 1e-9 && ! tiltOn) return;
        const double pv = forme == Forme::ShelfAigu ? std::min (0.4 * fsHz, f0 * 2.5) : forme == Forme::ShelfGrave ? std::max (40.0, f0 / 2.5) : f0;
        tiltLo.set (rbjShelf (fsHz, pv, -0.5 * 9.0 * t, false));
        tiltHi.set (rbjShelf (fsHz, pv, +0.5 * 9.0 * t, true));
        tiltOn = true;
    }

    void reset()
    {
        src.reset(); out.reset(); tiltLo.reset(); tiltHi.reset();
        zS = 0.0; x1 = 0.0;
        hUp.reset(); hY.reset();
        du.init (0.0); dS.init (1e-7);
        dcX = dcY = 0.0;
    }

    inline double process (double x)
    {
        double b = src.process (x);
        if (tiltOn) b = tiltHi.process (tiltLo.process (b));
        zS = (1.0 - cS) * std::abs (b) + cS * zS;
        const double S = zS * (kPi / 2.0) + 1e-7;
        const double u = drive * b / S;
        hUp.push (u);
        double v0 = 0, v1 = 0;
        for (int i = 0; i < 21; ++i) v0 += tables::hUp[2 * i] * hUp.at (i);
        for (int i = 0; i < 20; ++i) v1 += tables::hUp[2 * i + 1] * hUp.at (i);
        hY.push (adaa (v0));
        double y = 0;
        for (int i = 0; i < 41; ++i) y += tables::h0[i] * hY.at (i);
        hY.push (adaa (v1));
        const double ud = du.push (u), Sd = dS.push (S);
        double res = (y - fz - purete * c1 * ud) * Sd / (drive * c1);
        res = out.process (res);
        const double rdc = res - dcX + rDc * dcY;
        dcX = res;
        dcY = rdc;
        return k * rdc;
    }

private:
    static double logcosh (double u) { const double a = std::abs (u); return a + std::log1p (std::exp (-2.0 * a)) - std::log (2.0); }

    inline double curveF (double x) const
    {
        switch (profil)
        {
            case ProfilExc::Doux:          return std::tanh (x);
            case ProfilExc::Chaud:         return std::tanh (x + 0.35);
            case ProfilExc::Mordant:       return courbes::f (ModeSat::ClassA, x);
            case ProfilExc::MordantChaud:  return courbes::f (ModeSat::ClassA, x + 0.25);
        }
        return x;
    }

    inline double curvePrim (double x) const
    {
        switch (profil)
        {
            case ProfilExc::Doux:          return logcosh (x);
            case ProfilExc::Chaud:         return logcosh (x + 0.35);
            case ProfilExc::Mordant:       return courbes::F (ModeSat::ClassA, x);
            case ProfilExc::MordantChaud:  return courbes::F (ModeSat::ClassA, x + 0.25);
        }
        return 0.5 * x * x;
    }

    inline double adaa (double v)
    {
        const double dxv = v - x1;
        const double r = std::abs (dxv) < 1e-6 ? curveF (0.5 * (v + x1)) : (curvePrim (v) - curvePrim (x1)) / dxv;
        x1 = v;
        return r;
    }

    ProfilExc profil = ProfilExc::MordantChaud;
    Forme forme = Forme::Cloche;
    double f0 = 1000.0, fsHz = 48000.0, drive = 2.5, purete = 0.0, k = 0.0, c1 = 1.0, fz = 0.0;
    Biquad src, out, tiltLo, tiltHi;
    bool tiltOn = false;
    double cS = 0, rDc = 0, zS = 0, x1 = 0, dcX = 0, dcY = 0;
    Historique<21> hUp;
    Historique<41> hY;
    Retard<latence> du, dS;
};
}
''', ROOT)

# ================================================================ Engine.h
g = rd("Source/Dsp/Engine.h", ROOT)
g = sub(g, '#include "ExciterV2.h"', '#include "ExciterV2.h"\n#include "ExciterV3.h"')
g = sub(g, "exc[k] = std::make_unique<ExciterV2>(); exc[k]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.profil, s.source, s.drive, s.tilt, s.dens); break;",
        "exc[k] = std::make_unique<ExciterV3>(); exc[k]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.profil, s.drive, s.tilt, s.dens); break;      // dens porte la Pureté (Exciter v3)")
g = sub(g, "    std::array<std::unique_ptr<ExciterV2>, 2> exc;", "    std::array<std::unique_ptr<ExciterV3>, 2> exc;")
g = sub(g, "            if (exc[(size_t) i]) exc[(size_t) i]->setDensite (d);", "            if (exc[(size_t) i]) exc[(size_t) i]->setPurete (d);")
g = sub(g, "    double dens = 1.0;                                      // « Densité » de la porte de l'Exciter (0 creuse … 1 régulière)", "    double dens = 0.0;                                      // Exciter v3 : « Pureté » (0 = zone saturée entière … 1 = harmoniques seules) — champ historique « dens »")
wr("Source/Dsp/Engine.h", g, ROOT)

# ================================================================ Params.h
p = rd("Source/Params.h", ROOT)
p = sub(p, 'P { pid (b, "dens"), 1 }', 'P { pid (b, "purete"), 1 }')
p = sub(p, 'n + U8 ("densité (Exciter)"), juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.5f));', 'n + U8 ("pureté (Exciter)"), juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.0f));')
p = sub(p, '    sp.dens    = raw (s, pid (b, "dens"));', '    sp.dens    = raw (s, pid (b, "purete"));                      // Exciter v3 : Pureté (champ historique « dens »)')
wr("Source/Params.h", p, ROOT)

# ================================================================ Interface : Source / Densité → Pureté, Tilt toujours
ed = rd("Source/PluginEditor.cpp", ROOT)
ed = sub(ed, 'addSeg ("mode", "PROFIL", pp::modeNames()); addSeg ("source", "SOURCE", pp::sourceNames());', 'addSeg ("mode", "PROFIL", pp::modeNames());')
ed = sub(ed, 'addKnob ("dens", U8 ("Densité"),', 'addKnob ("purete", U8 ("Pureté"),')
ed = sub(ed, 'if (juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "source"))) == 1) addKnob ("tilt"', 'addKnob ("tilt"')
ed = sub(ed, '        typeSegs[1]->setOptionHelp ({ U8 ("Auto : la saturation est alimentée par une bande centrée à f0/3 : ses harmoniques tombent dans la zone réglée."), U8 ("Bande : la saturation est alimentée par la zone elle-même (permet le Tilt).") });\n', '')
ed = sub(ed, 'aide (*typeKnobs[1], U8 ("Densité : 0 % = le wet ne réagit qu\'aux pics (salves nettes, peut pomper) ; 100 % = wet continu et régulier (halo)."));', 'aide (*typeKnobs[1], U8 ("Pureté : 0 % = la zone saturée entière est ajoutée (renfort et grain, naturel) ; 100 % = seulement les harmoniques nouvelles (plus fin, plus « piquant »)."));')
ed = sub(ed, 'Tilt : penche la source avant la saturation : négatif = plus de saturation dans les graves de la zone, positif = dans les aigus.', 'Tilt : penche la zone avant la saturation : négatif = plus de saturation dans le bas de la zone, positif = dans le haut.')
ed = sub(ed, 'aide (*typeKnobs[0], U8 ("Harmoniques : dureté de la saturation, de douce à dure (plus dur = plus d\'harmoniques élevées)."));', 'aide (*typeKnobs[0], U8 ("Harmoniques : dureté de la saturation, de douce à dure (plus dur = plus d\'harmoniques élevées). Le caractère ne dépend pas du niveau d\'entrée."));')
ed = sub(ed, 'U8 ("Gain de l\'Exciter (0 à +15 dB) : dose du signal ajouté (wet). Toutes les bandes sont multipliées par Intensité (en haut).")', 'U8 ("Gain de l\'Exciter (0 à +15 dB) : renfort saturé de la zone (+6 dB ≈ la zone renforcée de 6 dB, avec le grain du profil). Toutes les bandes sont multipliées par Intensité (en haut).")')
wr("Source/PluginEditor.cpp", ed, ROOT)

# ================================================================ tests C++
t = rd("tests/test_refs.cpp", ROOT)
t = sub(t, '#include "../Source/Dsp/ExciterV2.h"', '#include "../Source/Dsp/ExciterV2.h"\n#include "../Source/Dsp/ExciterV3.h"')
bloc = '''        else if (type == "exciter3")
        {
            double g, dr, tl, pu;
            std::string pr;
            is >> g >> pr >> dr >> tl >> pu;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;
            if (xs.empty() || xs.size() != ref.size()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\\n"; continue; }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            const ProfilExc p = pr == "doux" ? ProfilExc::Doux : pr == "chaud" ? ProfilExc::Chaud : pr == "mordant" ? ProfilExc::Mordant : ProfilExc::MordantChaud;
            ExciterV3 ex;
            ex.prepare (fs, forme (sh), f0, q, g, p, dr, tl, pu);
            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (ex.process (xs[i]) - ref[i]));
            e /= std::max (crete, 1e-30);
            pireExc3 = std::max (pireExc3, e);
            if (e > 1e-7) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\\n"; }
        }
'''
t = sub(t, '        else if (type == "tame")', bloc + '        else if (type == "tame")')
t = sub(t, "pireEngine = 0, pireExc2 = 0;", "pireEngine = 0, pireExc2 = 0, pireExc3 = 0;")
t = sub(t, '" ; exciter v2 : " << pireExc2', '" ; exciter v2 : " << pireExc2 << " ; exciter v3 : " << pireExc3')
t = sub(t, "double lf0, lq, lg, lw, ltime, lsens, lam, lrel, llink;", "double lf0, lq, lg, lw, ltime, lsens, lam, lrel, llink, lpur;")
t = sub(t, ">> lam >> lrel >> llink)", ">> lam >> lrel >> llink >> lpur)")
t = sub(t, "b.link = llink;", "b.link = llink; b.dens = lpur;")
wr("tests/test_refs.cpp", t, ROOT)
print("ok")
