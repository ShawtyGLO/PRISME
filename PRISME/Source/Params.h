#pragma once

#include <JuceHeader.h>
#include "Dsp/Engine.h"

// Paramètres PRISME : 5 bandes × 15 réglages + delta + sortie. Identifiants STABLES (automation, projets sauvegardés) : ne jamais renommer.
namespace prismeParams
{
constexpr int nBands = 5;

// Littéral UTF-8 → juce::String (le constructeur `String (const char*)` suppose de l'ASCII : les accents deviendraient du charabia).
inline juce::String U8 (const char* s) { return juce::String::fromUTF8 (s); }
inline juce::StringArray sa (std::initializer_list<juce::String> l) { juce::StringArray a; for (auto& x : l) a.add (x); return a; }

inline juce::String pid (int band, const char* name) { return "b" + juce::String (band + 1) + "_" + name; }

inline juce::StringArray typeNames()   { return sa ({ "Exciter", "Tame", "Shape", "Lift" }); }
inline juce::StringArray formeNames()  { return sa ({ "Shelf grave", "Cloche", "Shelf aigu" }); }
inline juce::StringArray canalNames()  { return sa ({ U8 ("Stéréo"), "Mid", "Side", "L", "R" }); }
inline juce::StringArray modeNames()   { return sa ({ "Doux", "Chaud", "Mordant", "Mordant chaud" }); }
inline juce::StringArray sourceNames() { return sa ({ "Auto", "Bande" }); }
inline juce::StringArray cibleNames()  { return sa ({ "Transitoires", "Sustain" }); }

inline juce::AudioProcessorValueTreeState::ParameterLayout createLayout()
{
    using P = juce::ParameterID;
    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    const int    defType[nBands]  = { 0, 3, 1, 2, 0 };                 // Exciter, Lift, Tame, Shape, Exciter
    const int    defForme[nBands] = { 0, 1, 1, 1, 2 };                 // shelf grave, cloche ×3, shelf aigu (ordre : Shelf grave | Cloche | Shelf aigu)
    const float  defFreq[nBands]  = { 42.0f, 164.0f, 632.0f, 2800.0f, 9600.0f };
    const float  defQ[nBands]     = { 0.71f, 0.71f, 1.2f, 0.9f, 0.71f };

    for (int b = 0; b < nBands; ++b)
    {
        const auto n = "Bande " + juce::String (b + 1) + " ";
        layout.add (std::make_unique<juce::AudioParameterBool>   (P { pid (b, "on"), 1 }, n + "active", true));
        layout.add (std::make_unique<juce::AudioParameterBool>   (P { pid (b, "solo"), 1 }, n + U8 ("delta (écoute seule)"), false));
        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "tilt"), 1 }, n + "tilt (mode Bande)", juce::NormalisableRange<float> (-1.0f, 1.0f, 0.01f), 0.0f));
        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "purete"), 1 }, n + U8 ("pureté (Exciter)"), juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.0f));
        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "link"), 1 }, n + "liaison L/R (Tame, Shape, Lift)", juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.5f));
        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "drive"), 1 }, n + "saturation", juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.71f));      // 0,71 → drive 2,5
        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "type"), 1 }, n + "type", typeNames(), defType[b]));
        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "forme"), 1 }, n + "forme", formeNames(), defForme[b]));

        juce::NormalisableRange<float> rf (20.0f, 20000.0f, 0.01f);
        rf.setSkewForCentre (1000.0f);
        layout.add (std::make_unique<juce::AudioParameterFloat> (P { pid (b, "freq"), 1 }, n + U8 ("fréquence"), rf, defFreq[b]));

        juce::NormalisableRange<float> rq (0.3f, 12.0f, 0.01f);
        rq.setSkewForCentre (1.5f);
        layout.add (std::make_unique<juce::AudioParameterFloat> (P { pid (b, "q"), 1 }, n + "Q", rq, defQ[b]));

        layout.add (std::make_unique<juce::AudioParameterFloat> (P { pid (b, "gain"), 1 }, n + "gain", juce::NormalisableRange<float> (-15.0f, 15.0f, 0.1f), 0.0f));
        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "canal"), 1 }, n + "canal", canalNames(), 0));
        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "mode"), 1 }, n + "profil (Exciter)", modeNames(), 3));
        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "source"), 1 }, n + "source", sourceNames(), 0));
        layout.add (std::make_unique<juce::AudioParameterFloat> (P { pid (b, "width"), 1 }, n + "largeur", juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.5f));
        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "cible"), 1 }, n + "cible", cibleNames(), 0));
        layout.add (std::make_unique<juce::AudioParameterFloat> (P { pid (b, "time"), 1 }, n + U8 ("durée"), juce::NormalisableRange<float> (5.0f, 200.0f, 1.0f), 60.0f));
        layout.add (std::make_unique<juce::AudioParameterFloat> (P { pid (b, "sens"), 1 }, n + U8 ("sensibilité"), juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.85f));
        layout.add (std::make_unique<juce::AudioParameterFloat> (P { pid (b, "amount"), 1 }, n + "amount", juce::NormalisableRange<float> (0.0f, 100.0f, 0.5f), 60.0f));
        juce::NormalisableRange<float> rr (20.0f, 1000.0f, 1.0f);
        rr.setSkewForCentre (150.0f);
        layout.add (std::make_unique<juce::AudioParameterFloat> (P { pid (b, "release"), 1 }, n + U8 ("relâchement"), rr, 150.0f));
    }
    layout.add (std::make_unique<juce::AudioParameterBool>  (P { "delta", 1 }, "Delta", false));
    layout.add (std::make_unique<juce::AudioParameterBool>  (P { "bypass", 1 }, "Bypass", false));
    layout.add (std::make_unique<juce::AudioParameterFloat> (P { "scale", 1 }, U8 ("Intensité (échelle du gain de toutes les bandes)"), juce::NormalisableRange<float> (0.0f, 2.0f, 0.01f), 1.0f));
    layout.add (std::make_unique<juce::AudioParameterFloat> (P { "output", 1 }, "Sortie", juce::NormalisableRange<float> (-12.0f, 12.0f, 0.1f), 0.0f));
    return layout;
}

// Réglage « Saturation » 0…1 → niveau visé à l'entrée de la courbe : 0,3 (doux) … 6 (très saturé), géométrique ; 0,54 ≈ 1,5 = valeur historique.
inline double driveFromKnob (float x) { return 0.3 * std::pow (20.0, (double) x); }

// Ordre d'AFFICHAGE des bandes : par fréquence croissante (égalité : emplacement). order[rang] = emplacement ; rankOf[emplacement] = rang.
// Seul l'affichage suit la position : les emplacements (b1_… b5_…) et l'automation ne bougent jamais.
struct BandOrder { int order[nBands]; int rankOf[nBands]; };

inline float raw (juce::AudioProcessorValueTreeState& s, const juce::String& id) { return s.getRawParameterValue (id)->load(); }

inline BandOrder bandOrder (juce::AudioProcessorValueTreeState& s)
{
    BandOrder o;
    float f[nBands];
    for (int b = 0; b < nBands; ++b) { f[b] = raw (s, pid (b, "freq")); o.order[b] = b; }
    std::stable_sort (o.order, o.order + nBands, [&] (int a, int c) { return f[a] < f[c]; });
    for (int r = 0; r < nBands; ++r) o.rankOf[o.order[r]] = r;
    return o;
}

inline prisme::BandeSpec readSpec (juce::AudioProcessorValueTreeState& s, int b)
{
    prisme::BandeSpec sp;
    sp.on      = raw (s, pid (b, "on")) > 0.5f;
    sp.type    = (prisme::TypeBande) juce::roundToInt (raw (s, pid (b, "type")));
    const int fo = juce::roundToInt (raw (s, pid (b, "forme")));
    sp.forme   = fo == 0 ? prisme::Forme::ShelfGrave : fo == 1 ? prisme::Forme::Cloche : prisme::Forme::ShelfAigu;
    sp.f0      = raw (s, pid (b, "freq"));
    sp.q       = raw (s, pid (b, "q"));
    sp.gainDb  = juce::jlimit (-30.0f, 30.0f, raw (s, pid (b, "gain")) * raw (s, "scale"));      // Intensité globale : échelle proportionnelle du gain de toutes les bandes
    sp.canal   = (prisme::Canal) juce::roundToInt (raw (s, pid (b, "canal")));
    sp.profil  = (prisme::ProfilExc) juce::jlimit (0, 3, juce::roundToInt (raw (s, pid (b, "mode"))));      // Doux, Chaud, Mordant, Mordant chaud
    sp.source  = (prisme::SourceExc) juce::roundToInt (raw (s, pid (b, "source")));
    sp.tilt    = raw (s, pid (b, "tilt"));
    sp.link    = raw (s, pid (b, "link"));
    sp.dens    = raw (s, pid (b, "purete"));                      // Exciter v3 : Pureté (champ historique « dens »)
    sp.drive   = driveFromKnob (raw (s, pid (b, "drive")));
    sp.width   = raw (s, pid (b, "width"));
    sp.cible   = (prisme::Shape::Cible) juce::roundToInt (raw (s, pid (b, "cible")));
    sp.timeMs  = raw (s, pid (b, "time"));
    sp.sens    = raw (s, pid (b, "sens"));
    sp.amount  = raw (s, pid (b, "amount"));
    sp.releaseMs = raw (s, pid (b, "release"));
    return sp;
}
}
