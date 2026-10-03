"""Patch UI 2026-10-03 : filtres contournables (clic sur le triangle), Delta + / Delta −. Idempotent non : à lancer une fois."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def edit(path, pairs):
    p = os.path.join(SRC, path)
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:80])
        s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)


edit("PluginEditor.cpp", [
    # magFiltre : un filtre contourné est absent
    ('''    if (pp::raw (proc.apvts, pp::pid (b, "lc_on")) > 0.5f)
    {
        const float n = juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "lc_pente"))) == 1 ? 4.0f''',
     '''    if (filtreActif (b, "lc"))
    {
        const float n = juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "lc_pente"))) == 1 ? 4.0f'''),
    ('''    if (pp::raw (proc.apvts, pp::pid (b, "hc_on")) > 0.5f)
    {
        const float n = juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "hc_pente"))) == 1 ? 4.0f''',
     '''    if (filtreActif (b, "hc"))
    {
        const float n = juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "hc_pente"))) == 1 ? 4.0f'''),
    ('''float CurveDisplay::magFiltre (int b, float f) const''',
     '''// Un filtre est « actif » s'il est posé ET non contourné (clic sur son triangle = coupé / remis pour comparer, il garde sa fréquence).
bool CurveDisplay::filtreActif (int b, const char* pre) const
{
    return pp::raw (proc.apvts, pp::pid (b, (juce::String (pre) + "_on").toRawUTF8())) > 0.5f
        && pp::raw (proc.apvts, pp::pid (b, (juce::String (pre) + "_mute").toRawUTF8())) < 0.5f;
}

float CurveDisplay::magFiltre (int b, float f) const'''),
    ('''        if (i == sel && (pp::raw (proc.apvts, pp::pid (i, "lc_on")) > 0.5f || pp::raw (proc.apvts, pp::pid (i, "hc_on")) > 0.5f))''',
     '''        if (i == sel && (filtreActif (i, "lc") || filtreActif (i, "hc")))'''),
    ('''            if (! bands[i].on || (pp::raw (proc.apvts, pp::pid (i, "lc_on")) < 0.5f && pp::raw (proc.apvts, pp::pid (i, "hc_on")) < 0.5f)) continue;''',
     '''            if (! bands[i].on || (! filtreActif (i, "lc") && ! filtreActif (i, "hc"))) continue;'''),
    ('''        const bool lcOn = pp::raw (proc.apvts, pp::pid (sel, "lc_on")) > 0.5f, hcOn = pp::raw (proc.apvts, pp::pid (sel, "hc_on")) > 0.5f;''',
     '''        const bool lcOn = pp::raw (proc.apvts, pp::pid (sel, "lc_on")) > 0.5f, hcOn = pp::raw (proc.apvts, pp::pid (sel, "hc_on")) > 0.5f;      // posés (position)
        const bool lcAct = filtreActif (sel, "lc"), hcAct = filtreActif (sel, "hc");                                                       // posés et non contournés'''),
    ('''        auto tri = [&] (float x, bool actif)
        {
            juce::Path t;
            t.addTriangle (x - 10.0f, 5.0f, x + 10.0f, 5.0f, x, 25.0f);
            g.setColour (actif ? c : juce::Colour (0xff3a3f47));
            g.fillPath (t);
            g.setColour (juce::Colour (0xff0b0d10));
            g.strokePath (t, juce::PathStrokeType (1.2f));
        };
        tri (xl, lcOn);
        tri (xr, hcOn);''',
     '''        auto tri = [&] (float x, bool pose, bool actif)
        {
            juce::Path t;
            t.addTriangle (x - 10.0f, 5.0f, x + 10.0f, 5.0f, x, 25.0f);
            if (pose && ! actif)                                                   // contourné (A/B) : triangle vide, à sa place
            {
                g.setColour (c.withAlpha (0.8f));
                g.strokePath (t, juce::PathStrokeType (1.5f));
                return;
            }
            g.setColour (actif ? c : juce::Colour (0xff3a3f47));
            g.fillPath (t);
            g.setColour (juce::Colour (0xff0b0d10));
            g.strokePath (t, juce::PathStrokeType (1.2f));
        };
        tri (xl, lcOn, lcAct);
        tri (xr, hcOn, hcAct);'''),
    ('''        g.setColour (lcOn ? c : col::mut);
        g.drawText (lcOn ? fmtFreq''', '''        g.setColour (lcAct ? c : col::mut);
        g.drawText (lcOn ? fmtFreq'''),
    ('''        g.setColour (hcOn ? c : col::mut);
        g.drawText (hcOn ? fmtFreq''', '''        g.setColour (hcAct ? c : col::mut);
        g.drawText (hcOn ? fmtFreq'''),
    # delta + / −
    ('''    const bool delta = pp::raw (proc.apvts, "delta") > 0.5f;
    g.setColour (delta ?''',
     '''    const bool dAnc = pp::raw (proc.apvts, "delta") > 0.5f;
    const bool dPos = dAnc || pp::raw (proc.apvts, "dpos") > 0.5f, dNeg = dAnc || pp::raw (proc.apvts, "dneg") > 0.5f;
    const bool delta = dPos || dNeg;
    g.setColour (delta ?'''),
    ('''        g.drawText (U8 ("DELTA : on n'entend que ce que les bandes ajoutent ou retirent"), 12, (int) kTop + 4, 500, 16, juce::Justification::left);''',
     '''        g.drawText (dPos && dNeg ? U8 ("DELTA : on n'entend que ce que les bandes ajoutent et retirent")
                    : dPos ? U8 ("DELTA + : on n'entend que ce que les bandes AJOUTENT (gain positif)") : U8 ("DELTA − : on n'entend que ce que les bandes RETIRENT (gain négatif)"),
                    12, (int) kTop + 4, 520, 16, juce::Justification::left);'''),
    # glissé : simple clic sur un triangle = contourner / remettre
    ('''        dragFilt = t;
        for (const char* n : { "_on", "_f" })''', '''        dragFilt = t;
        filtDownX = e.x;
        filtMoved = false;
        for (const char* n : { "_on", "_f" })'''),
    ('''    if (dragFilt >= 0)
    {
        const int s = selGet();
        const float x = juce::jlimit (0.0f, (float) getWidth(), (float) e.x);
        constexpr float bord = 10.0f;''', '''    if (dragFilt >= 0)
    {
        const int s = selGet();
        if (! filtMoved && std::abs (e.x - filtDownX) < 4) return;                    // simple clic en cours : pas de déplacement
        if (! filtMoved)
        {
            filtMoved = true;
            setParam (pp::pid (s, dragFilt == 0 ? "lc_mute" : "hc_mute"), 0.0f, false);       // on déplace : le filtre se remet en service
        }
        const float x = juce::jlimit (0.0f, (float) getWidth(), (float) e.x);
        constexpr float bord = 10.0f;'''),
    ('''        const char* pre = dragFilt == 0 ? "lc" : "hc";
        for (const char* n : { "_on", "_f" })
            if (auto* p = proc.apvts.getParameter (pp::pid (selGet(), (juce::String (pre) + n).toRawUTF8()))) p->endChangeGesture();
        dragFilt = -1;
        return;''', '''        const char* pre = dragFilt == 0 ? "lc" : "hc";
        for (const char* n : { "_on", "_f" })
            if (auto* p = proc.apvts.getParameter (pp::pid (selGet(), (juce::String (pre) + n).toRawUTF8()))) p->endChangeGesture();
        if (! filtMoved && pp::raw (proc.apvts, pp::pid (selGet(), (juce::String (pre) + "_on").toRawUTF8())) > 0.5f)       // simple clic sur un filtre posé : A/B
        {
            const auto id = pp::pid (selGet(), (juce::String (pre) + "_mute").toRawUTF8());
            setParam (id, pp::raw (proc.apvts, id) > 0.5f ? 0.0f : 1.0f, true);
        }
        dragFilt = -1;
        return;'''),
])
edit("PluginEditor.h", [
    ("    int dragBand = -1, dragFilt = -1;", "    int dragBand = -1, dragFilt = -1, filtDownX = 0;\n    bool filtMoved = false;"),
    ("    float magFiltre (int band, float f) const;", "    bool filtreActif (int band, const char* pre) const;         // filtre posé et non contourné\n    float magFiltre (int band, float f) const;"),
])
print("ok")
