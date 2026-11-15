"""Patch v0.4 (retours de test n°3) : numérotation et ordre des bandes suivant la fréquence, taille de base plus petite et mémorisée, wet du canal Side visible."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def rd(n):
    return open(os.path.join(SRC, n), encoding="utf-8").read()


def wr(n, s):
    open(os.path.join(SRC, n), "w", encoding="utf-8").write(s)


# ---- Params.h : ordre d'affichage = ordre des fréquences (les emplacements de paramètres ne bougent pas : aucune automation déplacée)
p = rd("Params.h")
p = p.replace("inline float raw (juce::AudioProcessorValueTreeState& s", '''// Ordre d'AFFICHAGE des bandes : par fréquence croissante (égalité : emplacement). order[rang] = emplacement ; rankOf[emplacement] = rang.
// Seul l'affichage suit la position : les emplacements (b1_… b5_…) et l'automation ne bougent jamais.
struct BandOrder { int order[nBands]; int rankOf[nBands]; };

inline float raw (juce::AudioProcessorValueTreeState& s''', 1)
p = p.replace("inline prisme::BandeSpec readSpec", '''inline BandOrder bandOrder (juce::AudioProcessorValueTreeState& s)
{
    BandOrder o;
    float f[nBands];
    for (int b = 0; b < nBands; ++b) { f[b] = raw (s, pid (b, "freq")); o.order[b] = b; }
    std::stable_sort (o.order, o.order + nBands, [&] (int a, int c) { return f[a] < f[c]; });
    for (int r = 0; r < nBands; ++r) o.rankOf[o.order[r]] = r;
    return o;
}

inline prisme::BandeSpec readSpec''', 1)
wr("Params.h", p)

# ---- PluginProcessor.cpp : wet du canal Side (delta = +d à gauche, −d à droite : la moyenne est nulle)
c = rd("PluginProcessor.cpp")
old = "                if (wetOn) wetTmp[si][(size_t) i] = (float) (0.5 * (dL + dR));"
new = "                if (wetOn) wetTmp[si][(size_t) i] = (float) (0.5 * ((s.cur && s.cur->getSpec().canal == prisme::Canal::Side) ? dL - dR : dL + dR));   // Side : d à gauche, −d à droite"
assert old in c
c = c.replace(old, new, 1)
wr("PluginProcessor.cpp", c)

# ---- PluginEditor.cpp : numéros, onglets, taille
e = rd("PluginEditor.cpp")
old = '        g.drawText (juce::String (i + 1), (int) (x - r), (int) (y - r), (int) (2 * r), (int) (2 * r), juce::Justification::centred);'
new = '        g.drawText (juce::String (order.rankOf[i] + 1), (int) (x - r), (int) (y - r), (int) (2 * r), (int) (2 * r), juce::Justification::centred);'
assert old in e
e = e.replace(old, new, 1)
e = e.replace("    const int sel = selGet();\n    struct B { bool on;", "    const int sel = selGet();\n    const auto order = pp::bandOrder (proc.apvts);\n    struct B { bool on;", 1)

# onglets : la cellule de rang r montre l'emplacement order[r]
old_paint = e[e.index("void BandTabs::paint (juce::Graphics& g)"):e.index("void BandTabs::mouseDoubleClick")]
new_paint = old_paint
new_paint = new_paint.replace("    const int sel = selGet();\n    for (int i = 0; i < pp::nBands; ++i)\n    {\n        const auto r = cell (i).toFloat();",
                              "    const int sel = selGet();\n    const auto ord = pp::bandOrder (proc.apvts);\n    for (int rank = 0; rank < pp::nBands; ++rank)\n    {\n        const int i = ord.order[rank];\n        const auto r = cell (rank).toFloat();")
new_paint = new_paint.replace("g.drawText (juce::String (i + 1) + \" · \"", "g.drawText (juce::String (rank + 1) + \" · \"")
e = e.replace(old_paint, new_paint, 1)
old_dc = e[e.index("void BandTabs::mouseDoubleClick"):e.index("void BandTabs::mouseDown")]
new_dc = old_dc.replace("    for (int i = 0; i < pp::nBands; ++i)\n        if (cell (i).contains (e.getPosition()))\n            if (auto* p = proc.apvts.getParameter (pp::pid (i, \"on\")))",
                        "    const auto ord = pp::bandOrder (proc.apvts);\n    for (int rank = 0; rank < pp::nBands; ++rank)\n        if (cell (rank).contains (e.getPosition()))\n            if (auto* p = proc.apvts.getParameter (pp::pid (ord.order[rank], \"on\")))")
e = e.replace(old_dc, new_dc, 1)
old_md = e[e.index("void BandTabs::mouseDown"):e.index("// ------------------------------------------------------------------ fiche de bande")]
new_md = old_md.replace("    for (int i = 0; i < pp::nBands; ++i)\n        if (cell (i).contains (e.getPosition())) { selSet (i); return; }",
                        "    const auto ord = pp::bandOrder (proc.apvts);\n    for (int rank = 0; rank < pp::nBands; ++rank)\n        if (cell (rank).contains (e.getPosition())) { selSet (ord.order[rank]); return; }")
e = e.replace(old_md, new_md, 1)

# taille : mémorisée dans l'état du plugin
e = e.replace("    setSize (baseW, baseH);\n    startTimerHz (15);",
              "    const int w = juce::jlimit (560, 2240, (int) proc.apvts.state.getProperty (\"uiWidth\", defaultW));      // taille mémorisée (état du plugin)\n    setSize (w, juce::roundToInt ((double) w * baseH / baseW));\n    startTimerHz (15);", 1)
e = e.replace("    layoutContent();\n    content.setTransform (juce::AffineTransform::scale ((float) getWidth() / (float) baseW));",
              "    layoutContent();\n    content.setTransform (juce::AffineTransform::scale ((float) getWidth() / (float) baseW));\n    if (getWidth() > 0) proc.apvts.state.setProperty (\"uiWidth\", getWidth(), nullptr);", 1)
wr("PluginEditor.cpp", e)

h = rd("PluginEditor.h")
NL = chr(10)
h = h.replace("static constexpr int baseW = 1120, baseH = 780;", "static constexpr int baseW = 1120, baseH = 780;                    // taille de CONCEPTION (mise a l'echelle ensuite)" + NL + "    static constexpr int defaultW = 900;                               // taille a l'ouverture (retour de llg53) ; la derniere taille utilisee est memorisee")
wr("PluginEditor.h", h)
print("ok")
