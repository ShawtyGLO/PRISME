"""Patch 2026-10-04 : compensation de sonie dans le processeur (paramètre « sonie », défaut OFF ; AUCUN changement visuel)."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def edit(path, pairs):
    p = os.path.join(SRC, path)
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:90])
        s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)


edit("Params.h", [
    ('''    layout.add (std::make_unique<juce::AudioParameterBool>  (P { "dpos", 1 },''',
     '''    layout.add (std::make_unique<juce::AudioParameterBool>  (P { "sonie", 1 }, U8 ("Compensation de sonie (traité recalé sur la sonie du sec)"), false));
    layout.add (std::make_unique<juce::AudioParameterBool>  (P { "dpos", 1 },'''),
])

edit("PluginProcessor.h", [
    ('''    prisme::Retard<prisme::Engine::latence> secL, secR;''',
     '''    prisme::Retard<prisme::Engine::latence> secL, secR;
    prisme::Sonie sonie;                                         // compensation de sonie (paramètre « sonie »)
    juce::SmoothedValue<float> sonieMix;
    bool sonieWasOn = false;
public:
    std::atomic<float> sonieGainDb { 0.0f };                     // correction appliquée (dB), pour un futur affichage
private:'''),
])

edit("PluginProcessor.cpp", [
    ('''    outGain.reset (sampleRate, 0.02);''',
     '''    sonie.prepare (sampleRate);
    sonieMix.reset (sampleRate, 0.05);
    sonieMix.setCurrentAndTargetValue (0.0f);
    sonieWasOn = false;
    sonieGainDb.store (0.0f);
    outGain.reset (sampleRate, 0.02);'''),
    ('''    outGain.setTargetValue (juce::Decibels::decibelsToGain (prismeParams::raw (apvts, "output")));

    for (int start = 0;''',
     '''    outGain.setTargetValue (juce::Decibels::decibelsToGain (prismeParams::raw (apvts, "output")));
    const bool sonieOn = prismeParams::raw (apvts, "sonie") > 0.5f;
    if (sonieOn && ! sonieWasOn) sonie.reset();                                  // mesure repartie de zéro à l'activation
    sonieWasOn = sonieOn;
    sonieMix.setTargetValue (sonieOn ? 1.0f : 0.0f);

    for (int start = 0;'''),
    ('''            const double wL = anySolo ? soloL : (delta ? dsL : apL + sumL), wR = anySolo ? soloR : (delta ? dsR : apR + sumR);''',
     '''            double wL = anySolo ? soloL : (delta ? dsL : apL + sumL), wR = anySolo ? soloR : (delta ? dsR : apR + sumR);
            const double mixS = (double) sonieMix.getNextValue();
            if (sonieOn || mixS > 1.0e-4)                                        // compensation de sonie : le traité complet est recalé sur la sonie du sec (pas en delta / delta de bande)
            {
                double gdb = 0.0;
                sonie.process (dryL, dryR, apL + sumL, apR + sumR, gdb);
                if (! delta && ! anySolo)
                {
                    const double f = std::pow (10.0, gdb * mixS / 20.0);
                    wL *= f;
                    wR *= f;
                }
                lastSonieDb = (float) (gdb * mixS);
            }'''),
    ('''        if (wetOn)
            for (size_t b = 0; b < slots.size(); ++b)''',
     '''        sonieGainDb.store (lastSonieDb);
        if (wetOn)
            for (size_t b = 0; b < slots.size(); ++b)'''),
    ('''    const bool wetOn = analyserOn.load();''', '''    const bool wetOn = analyserOn.load();
    float lastSonieDb = 0.0f;'''),
])
print("ok")
