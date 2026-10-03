"""Patch UI 2026-10-03 (v2) : l'INTÉRIEUR des cadres redevient comme avant (aplat) ; seuls les CONTOURS prennent un relief arrondi (lunette moulée, comme l'anneau des
bobines de la 2e référence) : ombre portée douce, anneau dégradé clair en haut / sombre en bas, arête extérieure claire, lèvre intérieure sombre."""
import os, re
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def read(p):
    return open(os.path.join(SRC, p), encoding="utf-8").read()


def write(p, s):
    open(os.path.join(SRC, p), "w", encoding="utf-8").write(s)


# ---------------- UiParts.h : nouveau namespace depth
s = read("UiParts.h")
i = s.index("// ------------------------------------------------------------------ profondeur")
j = s.index("inline int textWidth")
NEW = '''// ------------------------------------------------------------------ profondeur : seuls les CONTOURS ont du relief (l'intérieur des cadres reste en aplat)
namespace depth
{
// Liseré fin : clair en haut / sombre en bas (relief) ou l'inverse (creux).
inline void edge (juce::Graphics& g, juce::Rectangle<float> r, float radius, bool raisedLook, float hi = 0.10f, float lo = 0.45f)
{
    const auto top = juce::Colours::white.withAlpha (raisedLook ? hi : lo * 0.55f), bot = juce::Colours::black.withAlpha (raisedLook ? lo : hi * 0.8f);
    g.setGradientFill (juce::ColourGradient (raisedLook ? top : bot, r.getX(), r.getY(), raisedLook ? bot : top, r.getX(), r.getBottom(), false));
    g.drawRoundedRectangle (r.reduced (0.5f), radius, 1.0f);
}

// Lunette moulée autour d'un cadre : à dessiner APRÈS le contenu (elle recouvre `th` pixels de bord). Ombre douce autour, anneau dégradé (lumière venant du haut),
// arête extérieure claire, lèvre intérieure sombre. raisedLook = false : le cadre est en creux (lumière inversée).
inline void bezel (juce::Graphics& g, juce::Rectangle<float> r, float radius, float th, bool raisedLook = true, float strength = 1.0f)
{
    for (int i = 4; i >= 1; --i)                                                       // ombre portée douce, hors du cadre
    {
        g.setColour (juce::Colours::black.withAlpha (0.07f * strength));
        g.fillRoundedRectangle (r.expanded ((float) i * 1.1f).translated (0.0f, (float) i * 0.7f), radius + (float) i);
    }
    juce::Path ring;
    ring.addRoundedRectangle (r, radius);
    ring.addRoundedRectangle (r.reduced (th), juce::jmax (2.0f, radius - th));
    ring.setUsingNonZeroWinding (false);
    const juce::Colour clair (0xff3a424d), sombre (0xff14171c);
    g.setGradientFill (juce::ColourGradient (raisedLook ? clair : sombre, r.getX(), r.getY(), raisedLook ? sombre : clair, r.getX(), r.getBottom(), false));
    g.fillPath (ring);
    edge (g, r, radius, raisedLook, 0.20f * strength, 0.55f * strength);                  // arête extérieure
    edge (g, r.reduced (th), juce::jmax (2.0f, radius - th), ! raisedLook, 0.10f * strength, 0.60f * strength);   // lèvre intérieure (relief inversé)
}
}

'''
s = s[:i] + NEW + s[j:]

# bouton pastille : fond d'origine, contour en relief (inversé quand enfoncé)
a = s.index("        if (on)\n        {\n            g.setColour (juce::Colour (0xff222936));")
b = s.index("        g.setColour (col::txt);\n        g.setFont (13.0f);\n        g.drawText (on ? textOn : textOff")
s = s[:a] + '''        g.setColour (on ? juce::Colour (0xff2b3340) : (hover ? col::panel2 : col::panel));
        g.fillRoundedRectangle (r, 10.0f);
        depth::bezel (g, r, 10.0f, 2.5f, ! on, 0.8f);
''' + s[b:]
write("UiParts.h", s)

# ---------------- PluginEditor.cpp
e = read("PluginEditor.cpp")


def sub(a, b):
    global e
    assert a in e, a[:90]
    e = e.replace(a, b, 1)


# écran de courbe : fond d'origine, lunette en creux
sub('''    depth::innerShadow (g, getLocalBounds().toFloat());                              // l'écran est en creux : ombre intérieure en haut et sur les côtés
    g.restoreState();
    depth::edge (g, getLocalBounds().toFloat(), 18.0f, false, 0.10f, 0.60f);        // arête du creux : sombre en haut, claire en bas
}''', '''    g.restoreState();
    depth::bezel (g, getLocalBounds().toFloat(), 18.0f, 5.0f, false);                // l'écran est en creux : seule la lunette a du relief
}''')
# onglets : fond d'origine, lunette en relief ; la bande sélectionnée garde sa couleur sur la lèvre intérieure
sub('''        depth::raised (g, r, 14.0f, i == sel ? col::panel2 : col::panel, i == sel ? 1.2f : 0.9f);
        if (i == sel)
        {
            g.setColour (c.withAlpha (0.85f));
            g.drawRoundedRectangle (r.reduced (0.5f), 14.0f, 1.2f);
        }''', '''        g.setColour (i == sel ? col::panel2 : col::panel);
        g.fillRoundedRectangle (r, 14.0f);
        depth::bezel (g, r, 14.0f, 3.5f, true, 0.9f);
        if (i == sel)
        {
            g.setColour (c.withAlpha (0.9f));
            g.drawRoundedRectangle (r.reduced (3.5f), 10.5f, 1.2f);
        }''')
# carte de réglages
sub('''    depth::raised (g, getLocalBounds().toFloat().reduced (1.0f), 16.0f, col::panel, 1.0f);
    g.setColour (col::mut);''', '''    g.setColour (col::panel);
    g.fillRoundedRectangle (getLocalBounds().toFloat().reduced (1.0f), 16.0f);
    depth::bezel (g, getLocalBounds().toFloat().reduced (1.0f), 16.0f, 4.0f, true);
    g.setColour (col::mut);''')
# châssis : pas de fond, une lunette seulement
sub('''        depth::chassis (g, juce::Rectangle<float> (6.0f, 6.0f, (float) baseW - 12.0f, (float) baseH - 12.0f), 24.0f);''',
    '''        depth::bezel (g, juce::Rectangle<float> (5.0f, 5.0f, (float) baseW - 10.0f, (float) baseH - 10.0f), 24.0f, 7.0f, true, 1.1f);''')
write("PluginEditor.cpp", e)
print("ok")
