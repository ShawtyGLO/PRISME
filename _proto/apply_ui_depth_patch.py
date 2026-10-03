"""Patch UI 2026-10-03 : encadrements arrondis avec impression de profondeur (sombre conservé, relief discret, lumière venant du haut).
 - UiParts.h : namespace `depth` (chassis, raised, recessed, innerShadow) ; boutons / segments un peu plus arrondis
 - PluginEditor.cpp : châssis du plugin, écran de courbe EN CREUX, onglets de bande et carte de réglages EN RELIEF
"""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def edit(path, pairs):
    p = os.path.join(SRC, path)
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:90])
        s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)


DEPTH = '''
// ------------------------------------------------------------------ profondeur (lumière unique venant du haut ; relief discret sur fond sombre)
namespace depth
{
// Liseré de bord : clair en haut, sombre en bas (relief) ou l'inverse (creux).
inline void edge (juce::Graphics& g, juce::Rectangle<float> r, float radius, bool raisedLook, float hi = 0.10f, float lo = 0.45f)
{
    const auto top = juce::Colours::white.withAlpha (raisedLook ? hi : lo * 0.55f), bot = juce::Colours::black.withAlpha (raisedLook ? lo : hi * 0.8f);
    g.setGradientFill (juce::ColourGradient (raisedLook ? top : bot, r.getX(), r.getY(), raisedLook ? bot : top, r.getX(), r.getBottom(), false));
    g.drawRoundedRectangle (r.reduced (0.5f), radius, 1.0f);
}

// Châssis du plugin : grand cadre arrondi, dégradé vertical, arête haute claire.
inline void chassis (juce::Graphics& g, juce::Rectangle<float> r, float radius)
{
    for (int i = 5; i >= 1; --i)                                                   // ombre portée douce
    {
        g.setColour (juce::Colours::black.withAlpha (0.10f));
        g.fillRoundedRectangle (r.expanded ((float) i * 1.5f).translated (0.0f, (float) i * 0.8f), radius + (float) i);
    }
    g.setGradientFill (juce::ColourGradient (juce::Colour (0xff1a1e25), r.getX(), r.getY(), juce::Colour (0xff111419), r.getX(), r.getBottom(), false));
    g.fillRoundedRectangle (r, radius);
    edge (g, r, radius, true, 0.14f, 0.55f);
    edge (g, r.reduced (2.0f), radius - 2.0f, true, 0.04f, 0.0f);                  // second liseré intérieur très discret
}

// Module en relief : léger dégradé, ombre dessous, arête haute claire.
inline void raised (juce::Graphics& g, juce::Rectangle<float> r, float radius, juce::Colour base, float strength = 1.0f)
{
    g.setColour (juce::Colours::black.withAlpha (0.28f * strength));
    g.fillRoundedRectangle (r.translated (0.0f, 1.5f).expanded (0.5f), radius);
    g.setGradientFill (juce::ColourGradient (base.brighter (0.10f * strength), r.getX(), r.getY(), base.darker (0.10f * strength), r.getX(), r.getBottom(), false));
    g.fillRoundedRectangle (r, radius);
    edge (g, r, radius, true, 0.09f * strength, 0.35f * strength);
}

// Ombre intérieure (haut et côtés) à poser à l'intérieur d'une zone déjà écrêtée sur sa forme arrondie.
inline void innerShadow (juce::Graphics& g, juce::Rectangle<float> r, float depthPx = 22.0f)
{
    g.setGradientFill (juce::ColourGradient (juce::Colours::black.withAlpha (0.55f), r.getX(), r.getY(), juce::Colours::transparentBlack, r.getX(), r.getY() + depthPx, false));
    g.fillRect (r.getX(), r.getY(), r.getWidth(), depthPx);
    g.setGradientFill (juce::ColourGradient (juce::Colours::black.withAlpha (0.35f), r.getX(), r.getY(), juce::Colours::transparentBlack, r.getX() + 14.0f, r.getY(), false));
    g.fillRect (r.getX(), r.getY(), 14.0f, r.getHeight());
    g.setGradientFill (juce::ColourGradient (juce::Colours::black.withAlpha (0.35f), r.getRight(), r.getY(), juce::Colours::transparentBlack, r.getRight() - 14.0f, r.getY(), false));
    g.fillRect (r.getRight() - 14.0f, r.getY(), 14.0f, r.getHeight());
}
}
'''

edit("UiParts.h", [
    ('''inline int textWidth (const juce::Font& f, const juce::String& t)''', DEPTH + '''
inline int textWidth (const juce::Font& f, const juce::String& t)'''),
    # boutons pastille : relief léger, plus arrondis
    ('''        g.setColour (on ? juce::Colour (0xff2b3340) : (hover ? col::panel2 : col::panel));
        g.fillRoundedRectangle (r, 8.0f);
        g.setColour (on ? juce::Colour (0xff4a5568) : col::line);
        g.drawRoundedRectangle (r, 8.0f, 1.0f);''',
     '''        if (on)
        {
            g.setColour (juce::Colour (0xff222936));                                      // enfoncé : creux
            g.fillRoundedRectangle (r, 10.0f);
            g.setGradientFill (juce::ColourGradient (juce::Colours::black.withAlpha (0.45f), r.getX(), r.getY(), juce::Colours::transparentBlack, r.getX(), r.getY() + 12.0f, false));
            g.fillRoundedRectangle (r, 10.0f);
            depth::edge (g, r.expanded (0.5f), 10.0f, false, 0.10f, 0.5f);
            g.setColour (juce::Colour (0xff4a5568).withAlpha (0.6f));
            g.drawRoundedRectangle (r, 10.0f, 1.0f);
        }
        else
        {
            depth::raised (g, r, 10.0f, hover ? col::panel2 : col::panel, 0.8f);
        }'''),
])

edit("PluginEditor.cpp", [
    # écran de courbe en creux
    ('''    g.setColour (col::panel);
    g.fillRoundedRectangle (getLocalBounds().toFloat(), 10.0f);
    g.saveState();
    juce::Path clip;
    clip.addRoundedRectangle (getLocalBounds().toFloat(), 10.0f);''',
     '''    g.setColour (col::panel);
    g.fillRoundedRectangle (getLocalBounds().toFloat(), 18.0f);
    g.saveState();
    juce::Path clip;
    clip.addRoundedRectangle (getLocalBounds().toFloat(), 18.0f);'''),
    ('''    g.restoreState();
    g.setColour (col::line);
    g.drawRoundedRectangle (getLocalBounds().toFloat().reduced (0.5f), 10.0f, 1.0f);
}

juce::String CurveDisplay::helpAt''',
     '''    depth::innerShadow (g, getLocalBounds().toFloat());                              // l'écran est en creux : ombre intérieure en haut et sur les côtés
    g.restoreState();
    depth::edge (g, getLocalBounds().toFloat(), 18.0f, false, 0.10f, 0.60f);        // arête du creux : sombre en haut, claire en bas
}

juce::String CurveDisplay::helpAt'''),
    # onglets de bande en relief
    ('''        g.setColour (i == sel ? col::panel2 : col::panel);
        g.fillRoundedRectangle (r, 10.0f);
        g.setColour (i == sel ? c : col::line);
        g.drawRoundedRectangle (r.reduced (0.5f), 10.0f, 1.0f);''',
     '''        depth::raised (g, r, 14.0f, i == sel ? col::panel2 : col::panel, i == sel ? 1.2f : 0.9f);
        if (i == sel)
        {
            g.setColour (c.withAlpha (0.85f));
            g.drawRoundedRectangle (r.reduced (0.5f), 14.0f, 1.2f);
        }'''),
    # carte de réglages en relief
    ('''    g.setColour (col::panel);
    g.fillRoundedRectangle (getLocalBounds().toFloat(), 10.0f);
    g.setColour (col::line);
    g.drawRoundedRectangle (getLocalBounds().toFloat().reduced (0.5f), 10.0f, 1.0f);
    g.setColour (col::mut);
    g.setFont (juce::Font (juce::FontOptions (11.0f, juce::Font::bold)));''',
     '''    depth::raised (g, getLocalBounds().toFloat().reduced (1.0f), 16.0f, col::panel, 1.0f);
    g.setColour (col::mut);
    g.setFont (juce::Font (juce::FontOptions (11.0f, juce::Font::bold)));'''),
    # châssis
    ('''    content.onPaint = [this] (juce::Graphics& g)
    {
        const bool byp''', '''    content.onPaint = [this] (juce::Graphics& g)
    {
        depth::chassis (g, juce::Rectangle<float> (6.0f, 6.0f, (float) baseW - 12.0f, (float) baseH - 12.0f), 24.0f);
        const bool byp'''),
])
print("ok")
