"""Filtres de bande : Engine.h (tests), Params.h, processeur, interface (triangles), références et tests C++."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "PRISME")


def rd(p, base=ROOT):
    return open(os.path.join(base, p), encoding="utf-8").read()


def wr(p, s, base=ROOT):
    open(os.path.join(base, p), "w", encoding="utf-8").write(s)


def sub(s, old, new):
    assert old in s, old[:90]
    return s.replace(old, new, 1)


# ================================================================ Engine.h
g = rd("Source/Dsp/Engine.h")
g = sub(g, '#include "ExciterV3.h"', '#include "ExciterV3.h"\n#include "FiltresBandes.h"')
g = sub(g, "    double link = 0.5;\n", "    double link = 0.5;\n    // Filtres de la bande (coupe-bas / coupe-haut, phase compensée) — hors de l'égalité : ils ne reconstruisent jamais la bande\n    bool lcOn = false, hcOn = false;\n    double lcF = 20.0, hcF = 20000.0;\n    int lcPente = 12, hcPente = 12;\n")
g = sub(g, '''        bandes.clear();
        for (const auto& s : specs)
        {
            if (! s.actif()) continue;
            auto b = std::make_unique<BandeProc>();
            b->prepare (fs, s);
            bandes.push_back (std::move (b));
        }
    }''', '''        bandes.clear();
        filt.prepare (fs, true);
        for (size_t i = 0; i < specs.size(); ++i)
        {
            const auto& s = specs[i];
            if (i < (size_t) FiltresBandes::nBandes)
            {
                filt.regle ((int) i, false, { s.lcOn, s.lcF, s.lcPente }, s.actif());
                filt.regle ((int) i, true, { s.hcOn, s.hcF, s.hcPente }, s.actif());
            }
            if (! s.actif()) continue;
            auto b = std::make_unique<BandeProc>();
            b->prepare (fs, s);
            bandes.push_back ({ (int) i, std::move (b) });
        }
        filt.miseAJourBloc (0);
    }''')
g = sub(g, '''            double oL = secL.push (L), oR = secR.push (R);
            for (auto& b : bandes)
            {
                double dL, dR;
                b->process (L, R, dL, dR);
                oL += dL;
                oR += dR;
            }''', '''            double oL = secL.push (L), oR = secR.push (R);
            filt.sec (oL, oR);                                  // passe-tout des filtres actifs
            for (auto& b : bandes)
            {
                double dL, dR;
                b.second->process (L, R, dL, dR);
                if (b.first < FiltresBandes::nBandes) filt.delta (b.first, dL, dR);
                oL += dL;
                oR += dR;
            }
            filt.avance();''')
g = sub(g, "    std::vector<std::unique_ptr<BandeProc>> bandes;\n};\n}", "    std::vector<std::pair<int, std::unique_ptr<BandeProc>>> bandes;       // (emplacement, bande)\n    FiltresBandes filt;\n};\n}")
wr("Source/Dsp/Engine.h", g)

# ================================================================ Params.h
p = rd("Source/Params.h")
p = sub(p, '        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "purete"), 1 }', '''        {
            juce::NormalisableRange<float> rfl (20.0f, 20000.0f, 0.01f);
            rfl.setSkewForCentre (1000.0f);
            layout.add (std::make_unique<juce::AudioParameterBool>   (P { pid (b, "lc_on"), 1 }, n + U8 ("coupe-bas actif"), false));
            layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "lc_f"), 1 }, n + U8 ("coupe-bas fréquence"), rfl, 20.0f));
            layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "lc_pente"), 1 }, n + U8 ("coupe-bas pente"), sa ({ "12 dB/oct", "24 dB/oct" }), 0));
            layout.add (std::make_unique<juce::AudioParameterBool>   (P { pid (b, "hc_on"), 1 }, n + U8 ("coupe-haut actif"), false));
            layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "hc_f"), 1 }, n + U8 ("coupe-haut fréquence"), rfl, 20000.0f));
            layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "hc_pente"), 1 }, n + U8 ("coupe-haut pente"), sa ({ "12 dB/oct", "24 dB/oct" }), 0));
        }
        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "purete"), 1 }''')
p = sub(p, "    return sp;\n}", '''    sp.lcOn    = raw (s, pid (b, "lc_on")) > 0.5f;
    sp.lcF     = raw (s, pid (b, "lc_f"));
    sp.lcPente = juce::roundToInt (raw (s, pid (b, "lc_pente"))) == 1 ? 24 : 12;
    sp.hcOn    = raw (s, pid (b, "hc_on")) > 0.5f;
    sp.hcF     = raw (s, pid (b, "hc_f"));
    sp.hcPente = juce::roundToInt (raw (s, pid (b, "hc_pente"))) == 1 ? 24 : 12;
    return sp;
}''')
wr("Source/Params.h", p)

# ================================================================ Processeur
h = rd("Source/PluginProcessor.h")
h = sub(h, "    juce::SmoothedValue<float> bypassMix;\n", "    juce::SmoothedValue<float> bypassMix;\n    prisme::FiltresBandes filtres;                         // coupe-bas / coupe-haut par bande, phase compensée\n")
wr("Source/PluginProcessor.h", h)
c = rd("Source/PluginProcessor.cpp")
c = sub(c, "    bypassMix.reset (sampleRate, 0.01);", "    filtres.prepare (sampleRate, true);\n    bypassMix.reset (sampleRate, 0.01);")
c = sub(c, "        // ---- entrée : anneau d'historique + conversion en double ----", '''        // ---- filtres de bande : réglages du bloc (bande active = présente et non coupée) ----
        for (int b = 0; b < prismeParams::nBands; ++b)
        {
            const auto sp = prismeParams::readSpec (apvts, b);
            const bool actif = slots[(size_t) b].cur != nullptr && sp.on;
            filtres.regle (b, false, { sp.lcOn, sp.lcF, sp.lcPente }, actif);
            filtres.regle (b, true, { sp.hcOn, sp.hcF, sp.hcPente }, actif);
        }
        filtres.miseAJourBloc (n);

        // ---- entrée : anneau d'historique + conversion en double ----''')
c = sub(c, "            const double dryL = secL.push (L), dryR = secR.push (R);\n            double sumL = 0.0, sumR = 0.0, soloL = 0.0, soloR = 0.0;",
        "            const double dryL = secL.push (L), dryR = secR.push (R);\n            double apL = dryL, apR = dryR;\n            filtres.sec (apL, apR);                            // sec passé par les passe-tout des filtres actifs\n            double sumL = 0.0, sumR = 0.0, soloL = 0.0, soloR = 0.0;")
c = sub(c, "                else { dL = cL; dR = cR; }\n                sumL += dL; sumR += dR;", "                else { dL = cL; dR = cR; }\n                filtres.delta ((int) si, dL, dR);\n                sumL += dL; sumR += dR;")
c = sub(c, "            const double g = (double) outGain.getNextValue();\n            const double bm = (double) bypassMix.getNextValue();\n            const double wL = anySolo ? soloL : (delta ? sumL : dryL + sumL), wR = anySolo ? soloR : (delta ? sumR : dryR + sumR);",
        "            filtres.avance();\n            const double g = (double) outGain.getNextValue();\n            const double bm = (double) bypassMix.getNextValue();\n            const double wL = anySolo ? soloL : (delta ? sumL : apL + sumL), wR = anySolo ? soloR : (delta ? sumR : apR + sumR);")
wr("Source/PluginProcessor.cpp", c)

# ================================================================ Références et tests C++
x = rd("export_refs.py", HERE)
x = sub(x, 's.get("link", 0.5), s.get("purete", 0.0))) + "\\n")', 's.get("link", 0.5), s.get("purete", 0.0), int(s.get("lc_on", False)), s.get("lc_f", 20.0), s.get("lc_pente", 12), int(s.get("hc_on", False)), s.get("hc_f", 20000.0), s.get("hc_pente", 12))) + "\\n")')
x = sub(x, '    y = traite(xstereo, int(fs0), cfg)\n', '''    y = traite(xstereo, int(fs0), cfg)
    filt = {i: [("lc", s["lc_f"], s["lc_pente"]) if s.get("lc_on") else None, ("hc", s["hc_f"], s["hc_pente"]) if s.get("hc_on") else None]
            for i, s in enumerate(cfg) if s.get("on", True) and s["gain_db"] != 0.0 and (s.get("lc_on") or s.get("hc_on"))}
    if filt:                                                   # bandes indépendantes : delta_i = traite(bande i seule) − sec retardé
        D = LAT_ENG
        sec = np.concatenate([np.zeros((D, 2)), xstereo[:-D]])
        deltas = {i: traite(xstereo, int(fs0), [s]) - sec for i, s in enumerate(cfg) if s.get("on", True) and s["gain_db"] != 0.0}
        y = applique(sec, deltas, filt, int(fs0))
''')
x = sub(x, "from prisme_engine_stream import traite", "from prisme_engine_stream import traite, LATENCE as LAT_ENG\nfrom prisme_filtres import applique")
x = sub(x, 'for nom, cfg in (("type", config_type()), ("variee", cfg2), ("liee", cfg3)):', '''cfg4 = config_type()
cfg4[0].update(lc_on=True, lc_f=40.0, lc_pente=24)
cfg4[1].update(hc_on=True, hc_f=3000.0, hc_pente=12)
cfg4[2].update(lc_on=True, lc_f=300.0, lc_pente=12, hc_on=True, hc_f=2500.0, hc_pente=24)
cfg4[4].update(lc_on=True, lc_f=6000.0, lc_pente=24, hc_on=True, hc_f=15000.0, hc_pente=12)
for nom, cfg in (("type", config_type()), ("variee", cfg2), ("liee", cfg3), ("filtres", cfg4)):''')
wr("export_refs.py", x, HERE)
t = rd("tests/test_refs.cpp")
t = sub(t, "double lf0, lq, lg, lw, ltime, lsens, lam, lrel, llink, lpur;", "double lf0, lq, lg, lw, ltime, lsens, lam, lrel, llink, lpur, llcf, lhcf;\n            int llc, llcp, lhc, lhcp;")
t = sub(t, ">> lam >> lrel >> llink >> lpur)", ">> lam >> lrel >> llink >> lpur >> llc >> llcf >> llcp >> lhc >> lhcf >> lhcp)")
t = sub(t, "b.link = llink; b.dens = lpur;", "b.link = llink; b.dens = lpur;\n                b.lcOn = llc != 0; b.lcF = llcf; b.lcPente = llcp; b.hcOn = lhc != 0; b.hcF = lhcf; b.hcPente = lhcp;")
wr("tests/test_refs.cpp", t)
print("ok")
