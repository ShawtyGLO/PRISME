"""Patch UI 2026-10-03 (suite) : boutons Delta + / Delta − dans l'en-tête, delta de bande EXCLUSIF (Maj / Ctrl-clic = ajouter)."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def edit(path, pairs):
    p = os.path.join(SRC, path)
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:80])
        s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)


edit("PluginEditor.h", [
    ('''    prismeUi::PillButton deltaBtn { U8 ("Écouter le delta"), U8 ("Écouter le delta") }, specBtn { "Spectre", "Spectre" };
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> deltaAttach;''',
     '''    prismeUi::PillButton deltaPosBtn { U8 ("Δ +  ajouté"), U8 ("Δ +  ajouté") }, deltaNegBtn { U8 ("Δ −  retiré"), U8 ("Δ −  retiré") }, specBtn { "Spectre", "Spectre" };
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> deltaPosAttach, deltaNegAttach;'''),
])

edit("PluginEditor.cpp", [
    ('''&card, &deltaBtn, &specBtn,''', '''&card, &deltaPosBtn, &deltaNegBtn, &specBtn,'''),
    ('''    deltaAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (p.apvts, "delta", deltaBtn);''',
     '''    deltaPosAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (p.apvts, "dpos", deltaPosBtn);
    deltaNegAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (p.apvts, "dneg", deltaNegBtn);'''),
    ('''    aide (deltaBtn, U8 ("Écouter le delta : n'écoute que ce que les bandes ajoutent ou retirent (toutes les bandes)."));''',
     '''    aide (deltaPosBtn, U8 ("Delta + : n'écoute que ce que les bandes AJOUTENT (bandes à gain positif). Avec Delta − : tout le delta."));
    aide (deltaNegBtn, U8 ("Delta − : n'écoute que ce que les bandes RETIRENT (bandes à gain négatif). Avec Delta + : tout le delta."));'''),
    ('''    deltaBtn.setBounds (header.removeFromRight (150).withTrimmedTop (8).withHeight (28));''',
     '''    deltaNegBtn.setBounds (header.removeFromRight (110).withTrimmedTop (8).withHeight (28));
    header.removeFromRight (6);
    deltaPosBtn.setBounds (header.removeFromRight (110).withTrimmedTop (8).withHeight (28));'''),
    # delta de bande exclusif
    ('''    onAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (ap, pp::pid (b, "solo"), *onButton);''',
     '''    onAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (ap, pp::pid (b, "solo"), *onButton);
    onButton->onClick = [this, b]                                                  // delta de bande EXCLUSIF : activer celui-ci coupe les autres ; Maj / Ctrl / Cmd-clic = en écouter plusieurs
    {
        const auto m = juce::ModifierKeys::getCurrentModifiers();
        if (! onButton->getToggleState() || m.isShiftDown() || m.isCtrlDown() || m.isCommandDown()) return;
        for (int o = 0; o < pp::nBands; ++o)
            if (o != b)
                if (auto* p = proc.apvts.getParameter (pp::pid (o, "solo"))) p->setValueNotifyingHost (0.0f);
    };'''),
])
print("ok")
