"""Branche l'Exciter v2 dans Engine.h / Params.h / interface / tests C++ ; exporte les références."""
import os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME")


def rd(p):
    return open(os.path.join(ROOT, p), encoding="utf-8").read()


def wr(p, s):
    open(os.path.join(ROOT, p), "w", encoding="utf-8").write(s)


def sub(s, old, new, count=1):
    assert old in s, old[:90]
    return s.replace(old, new, count)


# ---------------------------------------------------------------- Engine.h
g = rd("Source/Dsp/Engine.h")
g = sub(g, '#include "Exciter.h"', '#include "Exciter.h"\n#include "ExciterV2.h"')
g = sub(g, "    ModeSat mode = ModeSat::Iron;\n", "    ProfilExc profil = ProfilExc::MordantChaud;              // Exciter v2 : Doux / Chaud / Mordant / Mordant chaud\n")
g = sub(g, "&& mode == o.mode", "&& profil == o.profil")
g = sub(g, "        n = s.canal == Canal::Stereo ? 2 : 1;", "        n = (s.canal == Canal::Stereo && s.type != TypeBande::Exciter) ? 2 : 1;      // Exciter v2 : une seule chaîne (non-linéarité LIÉE : source = milieu)")
g = sub(g, "exc[k] = std::make_unique<Exciter>(); exc[k]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.mode, s.source); exc[k]->setDrive (s.drive); exc[k]->setTilt (s.tilt); break;",
        "exc[k] = std::make_unique<ExciterV2>(); exc[k]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.profil, s.source, s.drive, s.tilt); break;")
g = sub(g, "    std::array<std::unique_ptr<Exciter>, 2> exc;", "    std::array<std::unique_ptr<ExciterV2>, 2> exc;")
g = sub(g, "            case Canal::Stereo: dL = delta (0, L); dR = delta (1, R); break;",
        "            case Canal::Stereo:\n                if (spec.type == TypeBande::Exciter) { const double d = delta (0, 0.5 * (L + R)); dL = dR = d; }      // Exciter : lié (milieu)\n                else { dL = delta (0, L); dR = delta (1, R); }\n                break;")
wr("Source/Dsp/Engine.h", g)

# ---------------------------------------------------------------- Params.h : le paramètre « mode » devient le PROFIL (identifiant conservé)
p = rd("Source/Params.h")
p = sub(p, 'sa ({ "Iron", "Triode", "Diode", "Class-A", "Rectifier" })', 'sa ({ "Doux", "Chaud", "Mordant", "Mordant chaud" })')
i = p.index("    static const prisme::ModeSat modes[5]")
j = p.index("\n", p.index("sp.mode    = modes[", i))
p = p[:i] + "    sp.profil  = (prisme::ProfilExc) juce::jlimit (0, 3, juce::roundToInt (raw (s, pid (b, \"mode\"))));      // Doux, Chaud, Mordant, Mordant chaud" + p[j:]
p = sub(p, 'layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "mode"), 1 }, n + "mode", modeNames(), 0));', 'layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "mode"), 1 }, n + "profil (Exciter)", modeNames(), 3));')
p = sub(p, 'juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.54f));', 'juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.71f));      // 0,71 → drive 2,5')
wr("Source/Params.h", p)

# ---------------------------------------------------------------- Interface
e = rd("Source/PluginEditor.cpp")
e = sub(e, 'addSeg ("mode", "MODE", pp::modeNames());', 'addSeg ("mode", "PROFIL", pp::modeNames());')
e = sub(e, 'addKnob ("drive", "Saturation",', 'addKnob ("drive", "Harmoniques",')
e = sub(e, "Ajoute des harmoniques dans la zone (gain de 0 à +15 dB). Saturation : de doux à très saturé.", "Ajoute des harmoniques dans la zone, en parallèle et seulement sur les pics au-dessus du niveau courant (gain de 0 à +15 dB : dose du wet). Profil : Doux, Chaud, Mordant, Mordant chaud. Harmoniques : de doux à dur.")
wr("Source/PluginEditor.cpp", e)

# ---------------------------------------------------------------- Tests C++
t = rd("tests/test_refs.cpp")
t = sub(t, '#include "../Source/Dsp/Exciter.h"', '#include "../Source/Dsp/Exciter.h"\n#include "../Source/Dsp/ExciterV2.h"')
bloc = '''        else if (type == "exciter2")
        {
            double g, dr, tl;
            std::string pr, so;
            is >> g >> pr >> so >> dr >> tl;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;
            if (xs.empty() || xs.size() != ref.size()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\\n"; continue; }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            const ProfilExc p = pr == "doux" ? ProfilExc::Doux : pr == "chaud" ? ProfilExc::Chaud : pr == "mordant" ? ProfilExc::Mordant : ProfilExc::MordantChaud;
            ExciterV2 ex;
            ex.prepare (fs, forme (sh), f0, q, g, p, so == "auto" ? SourceExc::Auto : SourceExc::Bande, dr, tl);
            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (ex.process (xs[i]) - ref[i]));
            e /= std::max (crete, 1e-30);
            pireExc2 = std::max (pireExc2, e);
            if (e > 1e-7) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\\n"; }
        }
'''
t = sub(t, '        else if (type == "tame")', bloc + '        else if (type == "tame")')
t = sub(t, "pireTame = 0, pireEngine = 0;", "pireTame = 0, pireEngine = 0, pireExc2 = 0;")
t = sub(t, '" ; tame : " << pireTame', '" ; exciter v2 : " << pireExc2 << " ; tame : " << pireTame')
# assemblage : le champ « mode » du fichier cfg devient un nom de profil
t = sub(t, 'b.mode = lmode == "iron" ? ModeSat::Iron : lmode == "triode" ? ModeSat::Triode : lmode == "diode" ? ModeSat::Diode : lmode == "classa" ? ModeSat::ClassA : ModeSat::Rect;',
        'b.profil = lmode == "doux" ? ProfilExc::Doux : lmode == "chaud" ? ProfilExc::Chaud : lmode == "mordant" ? ProfilExc::Mordant : ProfilExc::MordantChaud;')
# test de préchauffage : profil au lieu de mode
t = t.replace("ModeSat mo; const char* nom; };", "ProfilExc mo; const char* nom; };")
t = t.replace("ModeSat::Iron, \"Exciter", "ProfilExc::MordantChaud, \"Exciter").replace("ModeSat::Iron, \"Tame", "ProfilExc::MordantChaud, \"Tame").replace("ModeSat::Iron, \"Shape", "ProfilExc::MordantChaud, \"Shape").replace("ModeSat::Iron, \"Lift", "ProfilExc::MordantChaud, \"Lift")
t = t.replace("sp.mode = c.mo;", "sp.profil = c.mo;")
wr("tests/test_refs.cpp", t)

# ---------------------------------------------------------------- export_refs.py
x = open(os.path.join(ROOT, "..", "_proto", "export_refs.py"), encoding="utf-8").read()
x = sub(x, "from prisme_tame import tame_band", "from prisme_tame import tame_band\nfrom prisme_exciter_v2_stream import exciter_v2_stream")
x = sub(x, 's.get("mode", "iron"),', 's.get("profil", "mordant_chaud"),')
x = sub(x, "TCFG = [", '''E2CFG = [("mordant_chaud", "auto", "bell", 3000.0, 0.71, 6.0, 2.5, 0.0), ("doux", "auto", "bell", 1000.0, 1.0, 8.0, 1.5, 0.0), ("chaud", "auto", "highshelf", 9600.0, 0.71, 5.0, 3.0, 0.0),
         ("mordant", "auto", "lowshelf", 200.0, 0.71, 6.0, 2.5, 0.0), ("mordant_chaud", "band", "bell", 3000.0, 1.0, 6.0, 2.5, 0.7), ("mordant", "band", "highshelf", 8000.0, 0.71, 6.0, 4.0, -0.5)]
for fs, nom_sig, sig in ((int(fs0), "mus", mus), (44100, "syn44", synth(44100)), (96000, "syn96", synth(96000))):
    for i, (pr, so, sh, f0, q, g, dr, tl) in enumerate(E2CFG):
        nom = f"exc2_{nom_sig}_{i}"
        y = exciter_v2_stream(sig, fs, block=8192, shape=sh, f0=f0, q=q, gain_db=g, profil=pr, source=so, drive=dr, tilt=tl)
        dump(nom, sig, y)
        man.append(f"exciter2 {nom} {fs} {sh} {f0} {q} {g} {pr} {so} {dr} {tl}")
TCFG = [''')
open(os.path.join(ROOT, "..", "_proto", "export_refs.py"), "w", encoding="utf-8").write(x)
print("ok")
