"""Interface des filtres de bande (maquette validée) : triangles dans la bande du haut de la courbe, courbes fines, autres bandes en pointillés (affichables / masquables)."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def rd(n):
    return open(os.path.join(SRC, n), encoding="utf-8").read()


def wr(n, s):
    open(os.path.join(SRC, n), "w", encoding="utf-8").write(s)


def sub(s, old, new):
    assert old in s, old[:90]
    return s.replace(old, new, 1)


h = rd("PluginEditor.h")
h = sub(h, "    static float response (int shape, float f0, float q, float gain, float f);",
        "    static float response (int shape, float f0, float q, float gain, float f);\n    float magFiltre (int band, float f) const;                 // module des filtres de la bande (Linkwitz-Riley)\n    float effectif (int band, int shape, float f0, float q, float gain, float f) const;   // effet de la bande, filtres compris\n    float fyDb (float db) const;\n    int triangleAt (juce::Point<int> p) const;                 // 0 coupe-bas, 1 coupe-haut, −1 aucun\n    juce::Rectangle<int> autresRect() const;\n    void setFiltre (int k, bool on, float f);")
h = sub(h, "    int dragBand = -1;", "    int dragBand = -1, dragFilt = -1;")
wr("PluginEditor.h", h)

e = rd("PluginEditor.cpp")
e = sub(e, "static constexpr float kFMin = 20.0f, kFMax = 20000.0f, kGMax = 15.0f;", "static constexpr float kFMin = 20.0f, kFMax = 20000.0f, kGMax = 15.0f, kTop = 30.0f;      // kTop : bande du haut réservée aux triangles des filtres")
e = sub(e, "float CurveDisplay::yOf (float g) const { const float h = (float) getHeight(); return h / 2.0f - (g / kGMax) * (h / 2.0f - 16.0f); }\nfloat CurveDisplay::gOf (float y) const { const float h = (float) getHeight(); return (h / 2.0f - y) / (h / 2.0f - 16.0f) * kGMax; }",
        '''float CurveDisplay::yOf (float g) const { const float hh = (float) getHeight() - kTop; return kTop + hh / 2.0f - (g / kGMax) * (hh / 2.0f - 16.0f); }
float CurveDisplay::gOf (float y) const { const float hh = (float) getHeight() - kTop; return (kTop + hh / 2.0f - y) / (hh / 2.0f - 16.0f) * kGMax; }
float CurveDisplay::fyDb (float db) const { return kTop + (-db / 48.0f) * ((float) getHeight() - kTop - 8.0f); }      // courbe de filtre : 0 dB en haut, −48 dB en bas

float CurveDisplay::magFiltre (int b, float f) const
{
    float m = 1.0f;
    if (pp::raw (proc.apvts, pp::pid (b, "lc_on")) > 0.5f)
    {
        const float n = juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "lc_pente"))) == 1 ? 4.0f : 2.0f;       // LR4 : 1/(1+(fc/f)^4) ; LR2 : 1/(1+(fc/f)^2)
        m *= 1.0f / (1.0f + std::pow (pp::raw (proc.apvts, pp::pid (b, "lc_f")) / f, n));
    }
    if (pp::raw (proc.apvts, pp::pid (b, "hc_on")) > 0.5f)
    {
        const float n = juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "hc_pente"))) == 1 ? 4.0f : 2.0f;
        m *= 1.0f / (1.0f + std::pow (f / pp::raw (proc.apvts, pp::pid (b, "hc_f")), n));
    }
    return m;
}

float CurveDisplay::effectif (int b, int shape, float f0, float q, float gain, float f) const
{
    const float a = std::pow (10.0f, response (shape, f0, q, gain, f) / 20.0f) - 1.0f;          // les filtres agissent sur le signal AJOUTÉ (phase compensée : module exact)
    return 20.0f * std::log10 (juce::jmax (1e-6f, 1.0f + a * magFiltre (b, f)));
}

juce::Rectangle<int> CurveDisplay::autresRect() const { return { getWidth() / 2 - 90, 6, 180, 18 }; }

int CurveDisplay::triangleAt (juce::Point<int> p) const
{
    if ((float) p.y > kTop + 4.0f) return -1;
    const int s = selGet();
    const float xl = pp::raw (proc.apvts, pp::pid (s, "lc_on")) > 0.5f ? xOf (pp::raw (proc.apvts, pp::pid (s, "lc_f"))) : 14.0f;
    const float xr = pp::raw (proc.apvts, pp::pid (s, "hc_on")) > 0.5f ? xOf (pp::raw (proc.apvts, pp::pid (s, "hc_f"))) : (float) getWidth() - 14.0f;
    if (std::abs ((float) p.x - xl) < 16.0f) return 0;
    if (std::abs ((float) p.x - xr) < 16.0f) return 1;
    return -1;
}

void CurveDisplay::setFiltre (int k, bool on, float f)
{
    const int s = selGet();
    const char* pre = k == 0 ? "lc" : "hc";
    setParam (pp::pid (s, (juce::String (pre) + "_on").toRawUTF8()), on ? 1.0f : 0.0f, false);
    if (on) setParam (pp::pid (s, (juce::String (pre) + "_f").toRawUTF8()), f, false);
}''')
# courbes de bande effectives
e = sub(e, "        for (int x = 0; x <= (int) w; x += 2) fill.lineTo ((float) x, yOf (response (b.shape, b.f0, b.q, b.gain, fOf ((float) x))));",
        "        for (int x = 0; x <= (int) w; x += 2) fill.lineTo ((float) x, yOf (effectif (i, b.shape, b.f0, b.q, b.gain, fOf ((float) x))));")
e = sub(e, "            const float gg = response (b.shape, b.f0, b.q, b.gain, fOf ((float) x));\n            if (std::abs (gg) < 0.08f) { pen = false; continue; }",
        "            const float gg = effectif (i, b.shape, b.f0, b.q, b.gain, fOf ((float) x));\n            if (std::abs (gg) < 0.08f) { pen = false; continue; }")
e = sub(e, "        g.setColour (c.withAlpha (i == sel ? 1.0f : 0.6f));\n        g.strokePath (line, juce::PathStrokeType (i == sel ? 2.0f : 1.0f));\n    }",
        '''        g.setColour (c.withAlpha (i == sel ? 1.0f : 0.6f));
        g.strokePath (line, juce::PathStrokeType (i == sel ? 2.0f : 1.0f));
        if (i == sel && (pp::raw (proc.apvts, pp::pid (i, "lc_on")) > 0.5f || pp::raw (proc.apvts, pp::pid (i, "hc_on")) > 0.5f))
        {   // la forme SANS filtre, en pointillé : on voit ce qui est retiré
            juce::Path orig;
            bool pn = false;
            for (int x = 0; x <= (int) w; x += 2)
            {
                const float gg = response (b.shape, b.f0, b.q, b.gain, fOf ((float) x));
                if (std::abs (gg) < 0.08f) { pn = false; continue; }
                if (! pn) orig.startNewSubPath ((float) x, yOf (gg)); else orig.lineTo ((float) x, yOf (gg));
                pn = true;
            }
            juce::Path dashed;
            const float dl[] = { 4.0f, 4.0f };
            juce::PathStrokeType (1.0f).createDashedStroke (dashed, orig, dl, 2);
            g.setColour (c.withAlpha (0.45f));
            g.fillPath (dashed);
        }
    }''')
e = sub(e, "        for (const auto& b : bands) if (b.on) s += response (b.shape, b.f0, b.q, b.gain, fOf ((float) x));",
        "        for (int i = 0; i < pp::nBands; ++i) if (bands[i].on) s += effectif (i, bands[i].shape, bands[i].f0, bands[i].q, bands[i].gain, fOf ((float) x));")
# filtres + triangles, avant les nœuds
e = sub(e, "    for (int i = 0; i < pp::nBands; ++i)\n    {\n        const auto& b = bands[i];\n        const float x = xOf (b.f0), y = yOf (b.gain), r = i == sel ? 9.0f : 7.0f;",
        '''    // ---- filtres : bande sélectionnée en trait fin plein ; autres bandes en pointillés (ou masquées) ----
    const bool autres = (bool) proc.apvts.state.getProperty ("filtresAutres", true);
    for (int pass = 0; pass < 2; ++pass)
        for (int i = 0; i < pp::nBands; ++i)
        {
            if ((pass == 0) == (i == sel)) continue;                                 // autres d'abord, sélectionnée par-dessus
            if (i != sel && ! autres) continue;
            if (! bands[i].on || (pp::raw (proc.apvts, pp::pid (i, "lc_on")) < 0.5f && pp::raw (proc.apvts, pp::pid (i, "hc_on")) < 0.5f)) continue;
            juce::Path fp;
            bool pn = false;
            for (int x = 0; x <= (int) w; x += 2)
            {
                const float db = 20.0f * std::log10 (juce::jmax (1e-6f, magFiltre (i, fOf ((float) x))));
                if (db < -46.0f) { pn = false; continue; }                             // pas de ligne plate jusqu'au bord
                if (! pn) fp.startNewSubPath ((float) x, fyDb (db)); else fp.lineTo ((float) x, fyDb (db));
                pn = true;
            }
            const auto c = col::forType (bands[i].type);
            if (i == sel)
            {
                g.setColour (c);
                g.strokePath (fp, juce::PathStrokeType (1.5f));
            }
            else
            {
                juce::Path dashed;
                const float dl[] = { 5.0f, 4.0f };
                juce::PathStrokeType (1.0f).createDashedStroke (dashed, fp, dl, 2);
                g.setColour (c.withAlpha (0.45f));
                g.fillPath (dashed);
            }
        }
    {   // bande du haut : triangles de la bande sélectionnée + choix d'affichage des autres filtres
        g.setColour (juce::Colour (0xff15181d));
        g.fillRect (0.0f, 0.0f, w, kTop);
        const auto c = col::forType (bands[sel].type);
        const bool lcOn = pp::raw (proc.apvts, pp::pid (sel, "lc_on")) > 0.5f, hcOn = pp::raw (proc.apvts, pp::pid (sel, "hc_on")) > 0.5f;
        const float xl = lcOn ? xOf (pp::raw (proc.apvts, pp::pid (sel, "lc_f"))) : 14.0f;
        const float xr = hcOn ? xOf (pp::raw (proc.apvts, pp::pid (sel, "hc_f"))) : w - 14.0f;
        auto tri = [&] (float x, bool actif)
        {
            juce::Path t;
            t.addTriangle (x - 10.0f, 5.0f, x + 10.0f, 5.0f, x, 25.0f);
            g.setColour (actif ? c : juce::Colour (0xff3a3f47));
            g.fillPath (t);
            g.setColour (juce::Colour (0xff0b0d10));
            g.strokePath (t, juce::PathStrokeType (1.2f));
        };
        tri (xl, lcOn);
        tri (xr, hcOn);
        g.setFont (11.0f);
        auto pente = [&] (const char* id) { return juce::roundToInt (pp::raw (proc.apvts, pp::pid (sel, id))) == 1 ? juce::String ("24") : juce::String ("12"); };
        const bool proches = xr - xl < 260.0f;
        g.setColour (lcOn ? c : col::mut);
        g.drawText (lcOn ? fmtFreq (pp::raw (proc.apvts, pp::pid (sel, "lc_f"))) + U8 (" · ") + pente ("lc_pente") + " dB/oct" : U8 ("coupe-bas"),
                    (int) juce::jmin (xl + 15.0f, w - 150.0f), proches ? (int) kTop + 4 : 8, 140, 14, juce::Justification::left);
        g.setColour (hcOn ? c : col::mut);
        g.drawText (hcOn ? fmtFreq (pp::raw (proc.apvts, pp::pid (sel, "hc_f"))) + U8 (" · ") + pente ("hc_pente") + " dB/oct" : U8 ("coupe-haut"),
                    (int) juce::jmax (xr - 155.0f, 10.0f), 8, 140, 14, juce::Justification::right);
        g.setColour (col::mut.withAlpha (0.8f));
        g.setFont (10.0f);
        g.drawText (autres ? U8 ("autres filtres : visibles") : U8 ("autres filtres : masqués"), autresRect(), juce::Justification::centred);
    }

    for (int i = 0; i < pp::nBands; ++i)
    {
        const auto& b = bands[i];
        const float x = xOf (b.f0), y = yOf (b.gain), r = i == sel ? 9.0f : 7.0f;''')
e = sub(e, "        g.drawText (U8 (\"DELTA : on n'entend que ce que les bandes ajoutent ou retirent\"), 12, 6, 500, 16, juce::Justification::left);",
        "        g.drawText (U8 (\"DELTA : on n'entend que ce que les bandes ajoutent ou retirent\"), 12, (int) kTop + 4, 500, 16, juce::Justification::left);")
# aide
e = sub(e, "juce::String CurveDisplay::helpAt (juce::Point<int> p) const\n{\n", '''juce::String CurveDisplay::helpAt (juce::Point<int> p) const
{
    if (autresRect().contains (p)) return U8 ("Clic : afficher (en pointillés) ou masquer les filtres des autres bandes.");
    const int t = triangleAt (p);
    if (t >= 0) return (t == 0 ? U8 ("Coupe-bas") : U8 ("Coupe-haut")) + U8 (" de la bande sélectionnée (sur le signal qu'elle ajoute) : glisser = fréquence, molette ou clic droit = pente 12 / 24 dB/oct, double-clic ou pousser contre le bord = désactiver.");
''')
# souris
e = sub(e, "void CurveDisplay::mouseDown (const juce::MouseEvent& e)\n{\n", '''void CurveDisplay::mouseDown (const juce::MouseEvent& e)
{
    if (autresRect().contains (e.getPosition()))
    {
        proc.apvts.state.setProperty ("filtresAutres", ! (bool) proc.apvts.state.getProperty ("filtresAutres", true), nullptr);
        repaint();
        return;
    }
    const int t = triangleAt (e.getPosition());
    if (t >= 0)
    {
        const int s = selGet();
        const char* pre = t == 0 ? "lc" : "hc";
        if (e.mods.isPopupMenu())                                                    // clic droit : pente 12 ↔ 24
        {
            const auto id = pp::pid (s, (juce::String (pre) + "_pente").toRawUTF8());
            setParam (id, juce::roundToInt (pp::raw (proc.apvts, id)) == 1 ? 0.0f : 1.0f, true);
            return;
        }
        dragFilt = t;
        for (const char* n : { "_on", "_f" })
            if (auto* p = proc.apvts.getParameter (pp::pid (s, (juce::String (pre) + n).toRawUTF8()))) p->beginChangeGesture();
        return;
    }
''')
e = sub(e, "void CurveDisplay::mouseDrag (const juce::MouseEvent& e)\n{\n", '''void CurveDisplay::mouseDrag (const juce::MouseEvent& e)
{
    if (dragFilt >= 0)
    {
        const int s = selGet();
        const float x = juce::jlimit (0.0f, (float) getWidth(), (float) e.x);
        constexpr float bord = 10.0f;                                                 // poussé contre le bord → désactivé
        if (dragFilt == 0)
        {
            if (x <= bord) setFiltre (0, false, 0.0f);
            else
            {
                const float lim = pp::raw (proc.apvts, pp::pid (s, "hc_on")) > 0.5f ? pp::raw (proc.apvts, pp::pid (s, "hc_f")) / 1.2f : kFMax / 1.2f;
                setFiltre (0, true, juce::jlimit (kFMin, lim, fOf (x)));
            }
        }
        else
        {
            if (x >= (float) getWidth() - bord) setFiltre (1, false, 0.0f);
            else
            {
                const float lim = pp::raw (proc.apvts, pp::pid (s, "lc_on")) > 0.5f ? pp::raw (proc.apvts, pp::pid (s, "lc_f")) * 1.2f : kFMin * 1.2f;
                setFiltre (1, true, juce::jlimit (lim, kFMax, fOf (x)));
            }
        }
        repaint();
        return;
    }
''')
e = sub(e, "void CurveDisplay::mouseUp (const juce::MouseEvent&)\n{\n", '''void CurveDisplay::mouseUp (const juce::MouseEvent&)
{
    if (dragFilt >= 0)
    {
        const char* pre = dragFilt == 0 ? "lc" : "hc";
        for (const char* n : { "_on", "_f" })
            if (auto* p = proc.apvts.getParameter (pp::pid (selGet(), (juce::String (pre) + n).toRawUTF8()))) p->endChangeGesture();
        dragFilt = -1;
        return;
    }
''')
e = sub(e, "void CurveDisplay::mouseDoubleClick (const juce::MouseEvent&)\n{\n", '''void CurveDisplay::mouseDoubleClick (const juce::MouseEvent& e)
{
    const int t = triangleAt (e.getPosition());
    if (t >= 0) { setParam (pp::pid (selGet(), t == 0 ? "lc_on" : "hc_on"), 0.0f, true); return; }         // double-clic sur un triangle : désactiver
    if ((float) e.y < kTop) return;
''')
e = sub(e, "void CurveDisplay::mouseWheelMove (const juce::MouseEvent&, const juce::MouseWheelDetails& d)\n{\n", '''void CurveDisplay::mouseWheelMove (const juce::MouseEvent& e, const juce::MouseWheelDetails& d)
{
    const int t = triangleAt (e.getPosition());
    if (t >= 0)                                                                         // molette sur un triangle : pente 12 ↔ 24
    {
        const auto id = pp::pid (selGet(), t == 0 ? "lc_pente" : "hc_pente");
        setParam (id, d.deltaY > 0.0f ? 1.0f : 0.0f, true);
        return;
    }
''')
wr("PluginEditor.cpp", e)
print("ok")
