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
inline juce::StringArray formeNames()  { return sa ({ "Cloche", "Shelf grave", "Shelf aigu" }); }
inline juce::StringArray canalNames()  { return sa ({ U8 ("Stéréo"), "Mid", "Side", "L", "R" }); }
inline juce::StringArray modeNames()   { return sa ({ "Iron", "Triode", "Diode", "Class-A", "Rectifier" }); }
inline juce::StringArray sourceNames() { return sa ({ "Auto", "Bande" }); }
inline juce::StringArray cibleNames()  { return sa ({ "Transitoires", "Sustain" }); }

inline juce::AudioProcessorValueTreeState::ParameterLayout createLayout()
{
    using P = juce::ParameterID;
    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    const int    defType[nBands]  = { 0, 3, 1, 2, 0 };                 // Exciter, Lift, Tame, Shape, Exciter
    const int    defForme[nBands] = { 1, 0, 0, 0, 2 };                 // shelf grave, cloche ×3, shelf aigu
    const float  defFreq[nBands]  = { 42.0f, 164.0f, 632.0f, 2800.0f, 9600.0f };
    const float  defQ[nBands]     = { 0.71f, 0.71f, 1.2f, 0.9f, 0.71f };

    for (int b = 0; b < nBands; ++b)
    {
        const auto n = "Bande " + juce::String (b + 1) + " ";
        layout.add (std::make_unique<juce::AudioParameterBool>   (P { pid (b, "on"), 1 }, n + "active", true));
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
        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "mode"), 1 }, n + "mode", modeNames(), 0));
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
    layout.add (std::make_unique<juce::AudioParameterFloat> (P { "output", 1 }, "Sortie", juce::NormalisableRange<float> (-12.0f, 12.0f, 0.1f), 0.0f));
    return layout;
}

inline float raw (juce::AudioProcessorValueTreeState& s, const juce::String& id) { return s.getRawParameterValue (id)->load(); }

inline prisme::BandeSpec readSpec (juce::AudioProcessorValueTreeState& s, int b)
{
    prisme::BandeSpec sp;
    sp.on      = raw (s, pid (b, "on")) > 0.5f;
    sp.type    = (prisme::TypeBande) juce::roundToInt (raw (s, pid (b, "type")));
    const int fo = juce::roundToInt (raw (s, pid (b, "forme")));
    sp.forme   = fo == 0 ? prisme::Forme::Cloche : fo == 1 ? prisme::Forme::ShelfGrave : prisme::Forme::ShelfAigu;
    sp.f0      = raw (s, pid (b, "freq"));
    sp.q       = raw (s, pid (b, "q"));
    sp.gainDb  = raw (s, pid (b, "gain"));
    sp.canal   = (prisme::Canal) juce::roundToInt (raw (s, pid (b, "canal")));
    static const prisme::ModeSat modes[5] = { prisme::ModeSat::Iron, prisme::ModeSat::Triode, prisme::ModeSat::Diode, prisme::ModeSat::ClassA, prisme::ModeSat::Rect };   // ordre de modeNames()
    sp.mode    = modes[juce::jlimit (0, 4, juce::roundToInt (raw (s, pid (b, "mode"))))];
    sp.source  = (prisme::SourceExc) juce::roundToInt (raw (s, pid (b, "source")));
    sp.width   = raw (s, pid (b, "width"));
    sp.cible   = (prisme::Shape::Cible) juce::roundToInt (raw (s, pid (b, "cible")));
    sp.timeMs  = raw (s, pid (b, "time"));
    sp.sens    = raw (s, pid (b, "sens"));
    sp.amount  = raw (s, pid (b, "amount"));
    sp.releaseMs = raw (s, pid (b, "release"));
    return sp;
}
}
