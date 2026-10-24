#include "PluginEditor.h"

using namespace prismeUi;
namespace pp = prismeParams;
using prismeParams::U8;

static constexpr float kFMin = 20.0f, kFMax = 20000.0f, kGMax = 15.0f, kTop = 30.0f;      // kTop : bande du haut réservée aux triangles des filtres

static float scaleOf (PrismeProcessor& p) { return pp::raw (p.apvts, "scale"); }                              // Intensité globale (échelle du gain de toutes les bandes)
static void aide (juce::Component& c, const juce::String& t) { c.getProperties().set ("aide", t); }

static juce::File uiFile()
{
    return juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory).getChildFile ("Shawty").getChildFile ("PRISME").getChildFile ("ui.xml");
}

// Largeur de fenetre memorisee entre les sessions et entre les projets (0 si absente)
static int loadWidth()
{
    if (auto xml = juce::parseXML (uiFile())) return xml->getIntAttribute ("width", 0);
    return 0;
}

static void saveWidth (int w)
{
    const auto f = uiFile();
    f.getParentDirectory().createDirectory();
    juce::XmlElement x ("PRISME_UI");
    x.setAttribute ("width", w);
    x.writeTo (f);
}

// ------------------------------------------------------------------ courbe
CurveDisplay::CurveDisplay (PrismeProcessor& p, std::function<int()> getSel, std::function<void (int)> setSel)
    : proc (p), selGet (std::move (getSel)), selSet (std::move (setSel))
{
    pastilleAutres.icone = [] (juce::Graphics& g, juce::Rectangle<float> r, bool on)          // œil (barré quand les filtres des autres bandes sont masqués)
    {
        const float cx = r.getCentreX(), cy = r.getCentreY();
        juce::Path oeil;
        oeil.startNewSubPath (cx - 8.0f, cy);
        oeil.quadraticTo (cx, cy - 9.0f, cx + 8.0f, cy);
        oeil.quadraticTo (cx, cy + 9.0f, cx - 8.0f, cy);
        g.setColour (on ? col::txt : col::mut);
        g.strokePath (oeil, juce::PathStrokeType (1.6f));
        g.drawEllipse (cx - 2.6f, cy - 2.6f, 5.2f, 5.2f, 1.6f);
        if (! on) g.drawLine (cx - 7.0f, cy + 8.0f, cx + 7.0f, cy - 8.0f, 1.6f);
    };
    pastilleAutres.actif = [this] { return (bool) proc.apvts.state.getProperty ("filtresAutres", true); };
    pastilleAutres.libelle = [this] { return (bool) proc.apvts.state.getProperty ("filtresAutres", true) ? U8 ("Filtres des autres bandes : visibles") : U8 ("Filtres des autres bandes : masqués"); };
    pastilleAutres.clic = [this] { proc.apvts.state.setProperty ("filtresAutres", ! (bool) proc.apvts.state.getProperty ("filtresAutres", true), nullptr); repaint(); };
    aide (pastilleAutres, U8 ("Clic : afficher (en pointillés) ou masquer les filtres des autres bandes."));
    addAndMakeVisible (pastilleAutres);
    proc.setAnalyserActive (true);
    startTimerHz (30);
}

float CurveDisplay::xOf (float f) const { return std::log (f / kFMin) / std::log (kFMax / kFMin) * (float) getWidth(); }
float CurveDisplay::fOf (float x) const { return kFMin * std::pow (kFMax / kFMin, x / (float) getWidth()); }
// Échelle verticale AUTOMATIQUE : ±15 dB, élargie par pas de 5 dB (jusqu'à ±30) quand le gain effectif (réglage × Intensité) d'une bande dépasse — la courbe continue de bouger.
void CurveDisplay::updateView()
{
    float m = 0.0f;
    for (int i = 0; i < pp::nBands; ++i)
        if (pp::raw (proc.apvts, pp::pid (i, "on")) > 0.5f) m = juce::jmax (m, std::abs (pp::raw (proc.apvts, pp::pid (i, "gain")) * scaleOf (proc)));
    gView = juce::jlimit (kGMax, 30.0f, std::ceil (m / 5.0f) * 5.0f);
}

float CurveDisplay::yOf (float g) const { const float hh = (float) getHeight() - kTop; return kTop + hh / 2.0f - (g / gView) * (hh / 2.0f - 16.0f); }
float CurveDisplay::gOf (float y) const { const float hh = (float) getHeight() - kTop; return (kTop + hh / 2.0f - y) / (hh / 2.0f - 16.0f) * gView; }
float CurveDisplay::fyDb (float db) const { return kTop + (-db / 48.0f) * ((float) getHeight() - kTop - 8.0f); }      // courbe de filtre : 0 dB en haut, −48 dB en bas

// Un filtre est « actif » s'il est posé ET non contourné (clic sur son triangle = coupé / remis pour comparer, il garde sa fréquence).
bool CurveDisplay::filtreActif (int b, const char* pre) const
{
    return pp::raw (proc.apvts, pp::pid (b, (juce::String (pre) + "_on").toRawUTF8())) > 0.5f
        && pp::raw (proc.apvts, pp::pid (b, (juce::String (pre) + "_mute").toRawUTF8())) < 0.5f;
}

float CurveDisplay::magFiltre (int b, float f) const
{
    float m = 1.0f;
    if (filtreActif (b, "lc"))
    {
        const float n = juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "lc_pente"))) == 1 ? 4.0f : 2.0f;       // LR4 : 1/(1+(fc/f)^4) ; LR2 : 1/(1+(fc/f)^2)
        m *= 1.0f / (1.0f + std::pow (pp::raw (proc.apvts, pp::pid (b, "lc_f")) / f, n));
    }
    if (filtreActif (b, "hc"))
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
}

// Allure indicative de la correction (0 shelf grave, 1 cloche, 2 shelf aigu) : la vraie réponse dépend du type de traitement.
float CurveDisplay::response (int shape, float f0, float q, float gain, float f)
{
    const float oct = std::log2 (f / f0), s = 1.0f / juce::jmax (0.25f, q);
    if (shape == 1) { const float u = oct / (0.55f * s + 0.05f); return gain * std::exp (-u * u); }
    const float k = 1.0f / (1.0f + std::exp (-oct * 3.2f / (s * 0.9f + 0.2f)));
    return gain * (shape == 2 ? k : 1.0f - k);
}

void CurveDisplay::setParam (const juce::String& id, float v, bool gesture)
{
    if (auto* p = proc.apvts.getParameter (id))
    {
        if (gesture) p->beginChangeGesture();
        p->setValueNotifyingHost (p->convertTo0to1 (v));
        if (gesture) p->endChangeGesture();
    }
}

void CurveDisplay::resized()
{
    pastilleAutres.setBounds (getWidth() - 10 - 330, getHeight() - 9 - 30, 330, 30);          // coin bas droit : hors de la bande des triangles
}

void CurveDisplay::timerCallback()
{
    float tmp[2048];
    int got;
    while ((got = proc.readAnalyser (tmp, 2048)) > 0)
    {
        for (int i = 0; i < got; ++i) { ring[(size_t) ringPos] = tmp[i]; ringPos = (ringPos + 1) & 2047; }
        sinceFft += got;
    }
    if (sinceFft >= 1024)
    {
        sinceFft = 0;
        for (int i = 0; i < 2048; ++i) fftData[(size_t) i] = ring[(size_t) ((ringPos + i) & 2047)];
        std::fill (fftData.begin() + 2048, fftData.end(), 0.0f);
        window.multiplyWithWindowingTable (fftData.data(), 2048);
        fft.performFrequencyOnlyForwardTransform (fftData.data());
        for (int i = 0; i < 1024; ++i)
        {
            const float db = 20.0f * std::log10 (fftData[(size_t) i] / 512.0f + 1e-9f);
            specDb[(size_t) i] = juce::jmax (db, specDb[(size_t) i] - 1.5f);
        }
    }
    for (int b = 0; b < pp::nBands; ++b)
    {
        auto& a = wetAna[(size_t) b];
        while ((got = proc.readWet (b, tmp, 2048)) > 0)
        {
            for (int i = 0; i < got; ++i) { a.ring[(size_t) a.pos] = tmp[i]; a.pos = (a.pos + 1) & 2047; }
            a.since += got;
        }
        if (a.since >= 1024) { a.since = 0; runFft (a); }
    }
    repaint();                                                       // toujours : l'etat des bandes (active / coupee, gain) doit se voir meme sans spectre
}

void CurveDisplay::runFft (Ana& a)
{
    for (int i = 0; i < 2048; ++i) fftData[(size_t) i] = a.ring[(size_t) ((a.pos + i) & 2047)];
    std::fill (fftData.begin() + 2048, fftData.end(), 0.0f);
    window.multiplyWithWindowingTable (fftData.data(), 2048);
    fft.performFrequencyOnlyForwardTransform (fftData.data());
    for (int i = 0; i < 1024; ++i)
    {
        const float db = 20.0f * std::log10 (fftData[(size_t) i] / 512.0f + 1e-9f);
        a.spec[(size_t) i] = juce::jmax (db, a.spec[(size_t) i] - 1.5f);
    }
}

void CurveDisplay::paint (juce::Graphics& g)
{
    updateView();
    const float w = (float) getWidth(), h = (float) getHeight();
    g.setColour (col::panel);
    g.fillRoundedRectangle (getLocalBounds().toFloat(), 10.0f);
    g.saveState();
    juce::Path clip;
    clip.addRoundedRectangle (getLocalBounds().toFloat(), 10.0f);
    g.reduceClipRegion (clip);
    g.setColour (juce::Colour (0xff12151a));
    g.fillRect (getLocalBounds());

    g.setFont (10.0f);
    for (float f : { 30.0f, 50.0f, 100.0f, 200.0f, 500.0f, 1000.0f, 2000.0f, 5000.0f, 10000.0f })
    {
        const float x = xOf (f);
        g.setColour (juce::Colour (0xff242a32));
        g.drawVerticalLine ((int) x, 0.0f, h);
        g.setColour (juce::Colour (0xff6c7482));
        g.drawText (f >= 1000.0f ? juce::String (f / 1000.0f, 0) + "k" : juce::String ((int) f), (int) x + 3, (int) h - 14, 30, 12, juce::Justification::left);
    }
    const std::vector<int> graduations = gView <= 15.0f ? std::vector<int> { -12, -6, 0, 6, 12 } : std::vector<int> { -30, -20, -10, 0, 10, 20, 30 };
    for (int gdb : graduations)
    {
        if (std::abs ((float) gdb) > gView) continue;
        const float y = yOf ((float) gdb);
        g.setColour (gdb == 0 ? juce::Colour (0xff39414c) : juce::Colour (0xff22272e));
        g.drawHorizontalLine ((int) y, 0.0f, w);
        g.setColour (juce::Colour (0xff6c7482));
        g.drawText ((gdb > 0 ? "+" : "") + juce::String (gdb), 4, (int) y - 13, 30, 12, juce::Justification::left);
    }

    if (showSpec)
    {
        const double fs = juce::jmax (8000.0, proc.getSampleRateHz());
        juce::Path sp;
        sp.startNewSubPath (0.0f, h);
        for (int x = 0; x <= (int) w; x += 3)
        {
            const float f = fOf ((float) x);
            const float bin = juce::jlimit (0.0f, 1022.0f, f / (float) fs * 2048.0f);
            const int i0 = (int) bin;
            const float db = specDb[(size_t) i0] + (specDb[(size_t) i0 + 1] - specDb[(size_t) i0]) * (bin - (float) i0);
            const float y = h - juce::jlimit (0.0f, 1.0f, (db + 100.0f) / 100.0f) * h * 0.85f;
            sp.lineTo ((float) x, y);
        }
        sp.lineTo (w, h);
        sp.closeSubPath();
        g.setColour (juce::Colour (0x1a8ca0be));
        g.fillPath (sp);
    }

    {   // signal WET de chaque bande, a la couleur du traitement (le rendu bouge dans la courbe : pas la courbe)
        const double fs = juce::jmax (8000.0, proc.getSampleRateHz());
        for (int b = 0; b < pp::nBands; ++b)
        {
            if (pp::raw (proc.apvts, pp::pid (b, "on")) < 0.5f || pp::raw (proc.apvts, pp::pid (b, "gain")) == 0.0f) continue;
            const auto& a = wetAna[(size_t) b];
            juce::Path wp;
            wp.startNewSubPath (0.0f, h);
            for (int x = 0; x <= (int) w; x += 2)
            {
                const float bin = juce::jlimit (0.0f, 1022.0f, fOf ((float) x) / (float) fs * 2048.0f);
                const int i0 = (int) bin;
                const float db = a.spec[(size_t) i0] + (a.spec[(size_t) i0 + 1] - a.spec[(size_t) i0]) * (bin - (float) i0);
                wp.lineTo ((float) x, h - juce::jlimit (0.0f, 1.0f, (db + 100.0f) / 100.0f) * h * 0.85f);
            }
            wp.lineTo (w, h);
            wp.closeSubPath();
            const auto c = col::forType (juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "type"))));
            g.setColour (c.withAlpha (b == selGet() ? 0.55f : 0.32f));
            g.fillPath (wp);
        }
    }

    const int sel = selGet();
    const auto order = pp::bandOrder (proc.apvts);
    struct B { bool on; int type, shape; float f0, q, gain; };
    B bands[pp::nBands];
    for (int i = 0; i < pp::nBands; ++i)
    {
        bands[i] = { pp::raw (proc.apvts, pp::pid (i, "on")) > 0.5f, juce::roundToInt (pp::raw (proc.apvts, pp::pid (i, "type"))),
                     juce::roundToInt (pp::raw (proc.apvts, pp::pid (i, "forme"))), pp::raw (proc.apvts, pp::pid (i, "freq")),
                     pp::raw (proc.apvts, pp::pid (i, "q")), juce::jlimit (-gView, gView, pp::raw (proc.apvts, pp::pid (i, "gain")) * scaleOf (proc)) };
    }

    for (int i = 0; i < pp::nBands; ++i)
    {
        const auto& b = bands[i];
        if (! b.on) continue;
        const auto c = col::forType (b.type);
        juce::Path fill;
        fill.startNewSubPath (0.0f, yOf (0.0f));
        for (int x = 0; x <= (int) w; x += 2) fill.lineTo ((float) x, yOf (effectif (i, b.shape, b.f0, b.q, b.gain, fOf ((float) x))));
        fill.lineTo (w, yOf (0.0f));
        fill.closeSubPath();
        g.setColour (c.withAlpha (i == sel ? 0.22f : 0.11f));
        g.fillPath (fill);
        juce::Path line;
        bool pen = false;
        for (int x = 0; x <= (int) w; x += 2)
        {
            const float gg = effectif (i, b.shape, b.f0, b.q, b.gain, fOf ((float) x));
            if (std::abs (gg) < 0.08f) { pen = false; continue; }
            if (! pen) line.startNewSubPath ((float) x, yOf (gg)); else line.lineTo ((float) x, yOf (gg));
            pen = true;
        }
        g.setColour (c.withAlpha (i == sel ? 1.0f : 0.6f));
        g.strokePath (line, juce::PathStrokeType (i == sel ? 2.0f : 1.0f));
        if (i == sel && (filtreActif (i, "lc") || filtreActif (i, "hc")))
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
    }

    juce::Path sum;
    for (int x = 0; x <= (int) w; x += 2)
    {
        float s = 0.0f;
        for (int i = 0; i < pp::nBands; ++i) if (bands[i].on) s += effectif (i, bands[i].shape, bands[i].f0, bands[i].q, bands[i].gain, fOf ((float) x));
        if (x == 0) sum.startNewSubPath (0.0f, yOf (s)); else sum.lineTo ((float) x, yOf (s));
    }
    const bool dAnc = pp::raw (proc.apvts, "delta") > 0.5f;
    const bool dPos = dAnc || pp::raw (proc.apvts, "dpos") > 0.5f, dNeg = dAnc || pp::raw (proc.apvts, "dneg") > 0.5f;
    const bool delta = dPos || dNeg;
    g.setColour (delta ? juce::Colour (0xffffd166) : juce::Colour (0xfff4f6f8));
    g.strokePath (sum, juce::PathStrokeType (2.0f));

    // ---- filtres : bande sélectionnée en trait fin plein ; autres bandes en pointillés (ou masquées) ----
    const bool autres = (bool) proc.apvts.state.getProperty ("filtresAutres", true);
    for (int pass = 0; pass < 2; ++pass)
        for (int i = 0; i < pp::nBands; ++i)
        {
            if ((pass == 0) == (i == sel)) continue;                                 // autres d'abord, sélectionnée par-dessus
            if (i != sel && ! autres) continue;
            if (! filtreActif (i, "lc") && ! filtreActif (i, "hc")) continue;                    // les filtres s'affichent aussi quand le module est coupé (plus discrets)
            juce::Path fp;
            bool pn = false;
            for (int x = 0; x <= (int) w; x += 2)
            {
                const float db = 20.0f * std::log10 (juce::jmax (1e-6f, magFiltre (i, fOf ((float) x))));
                if (db < -46.0f) { pn = false; continue; }                             // pas de ligne plate jusqu'au bord
                if (! pn) fp.startNewSubPath ((float) x, fyDb (db)); else fp.lineTo ((float) x, fyDb (db));
                pn = true;
            }
            const auto c = col::forType (bands[i].type).withMultipliedAlpha (bands[i].on ? 1.0f : 0.5f);
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
        const bool lcOn = pp::raw (proc.apvts, pp::pid (sel, "lc_on")) > 0.5f, hcOn = pp::raw (proc.apvts, pp::pid (sel, "hc_on")) > 0.5f;      // posés (position)
        const bool lcAct = filtreActif (sel, "lc"), hcAct = filtreActif (sel, "hc");                                                       // posés et non contournés
        const float xl = lcOn ? xOf (pp::raw (proc.apvts, pp::pid (sel, "lc_f"))) : 14.0f;
        const float xr = hcOn ? xOf (pp::raw (proc.apvts, pp::pid (sel, "hc_f"))) : w - 14.0f;
        auto tri = [&] (float x, bool pose, bool actif)
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
        tri (xr, hcOn, hcAct);
        g.setFont (11.0f);
        auto pente = [&] (const char* id) { return juce::roundToInt (pp::raw (proc.apvts, pp::pid (sel, id))) == 1 ? juce::String ("24") : juce::String ("12"); };
        const bool proches = xr - xl < 260.0f;
        g.setColour (lcAct ? c : col::mut);
        g.drawText (lcOn ? fmtFreq (pp::raw (proc.apvts, pp::pid (sel, "lc_f"))) + U8 (" · ") + pente ("lc_pente") + " dB/oct" : U8 ("coupe-bas"),
                    (int) juce::jmin (xl + 15.0f, w - 150.0f), proches ? (int) kTop + 4 : 8, 140, 14, juce::Justification::left);
        g.setColour (hcAct ? c : col::mut);
        g.drawText (hcOn ? fmtFreq (pp::raw (proc.apvts, pp::pid (sel, "hc_f"))) + U8 (" · ") + pente ("hc_pente") + " dB/oct" : U8 ("coupe-haut"),
                    (int) juce::jmax (xr - 155.0f, 10.0f), 8, 140, 14, juce::Justification::right);
    }

    for (int i = 0; i < pp::nBands; ++i)
    {
        const auto& b = bands[i];
        const float x = xOf (b.f0), y = yOf (b.gain), r = i == sel ? 9.0f : 7.0f;
        g.setColour (b.on ? col::forType (b.type) : juce::Colour (0xff3a3f47));
        g.fillEllipse (x - r, y - r, 2 * r, 2 * r);
        g.setColour (juce::Colour (0xff0b0d10));
        g.drawEllipse (x - r, y - r, 2 * r, 2 * r, 2.0f);
        g.setFont (juce::Font (juce::FontOptions (10.0f, juce::Font::bold)));
        g.drawText (juce::String (order.rankOf[i] + 1), (int) (x - r), (int) (y - r), (int) (2 * r), (int) (2 * r), juce::Justification::centred);
    }
    if (delta)
    {
        g.setColour (juce::Colour (0xffffd166));
        g.setFont (12.0f);
        g.drawText (dPos && dNeg ? U8 ("DELTA : on n'entend que ce que les bandes ajoutent et retirent")
                    : dPos ? U8 ("DELTA + : on n'entend que ce que les bandes AJOUTENT (gain positif)") : U8 ("DELTA − : on n'entend que ce que les bandes RETIRENT (gain négatif)"),
                    12, (int) kTop + 4, 520, 16, juce::Justification::left);
    }
    g.setColour (col::mut);
    g.setFont (11.0f);
    g.drawText (U8 ("Glisser un nœud : fréquence et gain · molette : Q · double-clic : bande active / coupée"), 12, (int) h - 30, (int) w - 24, 14, juce::Justification::left);
    g.restoreState();
    g.setColour (col::line);
    g.drawRoundedRectangle (getLocalBounds().toFloat().reduced (0.5f), 10.0f, 1.0f);
}

juce::String CurveDisplay::helpAt (juce::Point<int> p) const
{
    const int t = triangleAt (p);
    if (t >= 0) return (t == 0 ? U8 ("Coupe-bas") : U8 ("Coupe-haut")) + U8 (" de la bande sélectionnée (sur le signal qu'elle ajoute) : clic = contourner / remettre (pour comparer en A/B), glisser = fréquence, molette ou clic droit = pente 12 / 24 dB/oct, double-clic ou pousser contre le bord = désactiver.");
    const auto ord = pp::bandOrder (proc.apvts);
    for (int i = 0; i < pp::nBands; ++i)
    {
        const float x = xOf (pp::raw (proc.apvts, pp::pid (i, "freq"))), y = yOf (juce::jlimit (-gView, gView, pp::raw (proc.apvts, pp::pid (i, "gain")) * scaleOf (proc)));
        if (std::hypot (x - (float) p.x, y - (float) p.y) < 18.0f)
            return U8 ("Bande ") + juce::String (ord.rankOf[i] + 1) + U8 (" (") + pp::typeNames()[juce::roundToInt (pp::raw (proc.apvts, pp::pid (i, "type")))]
                 + U8 (") : glisser = fréquence et gain, molette = Q, double-clic = activer / couper.");
    }
    return U8 ("Courbe : glisser un nœud (fréquence, gain), molette = Q de la bande sélectionnée. La zone colorée derrière montre le signal ajouté (wet) de chaque bande.");
}

void CurveDisplay::mouseDown (const juce::MouseEvent& e)
{
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
        filtDownX = e.x;
        filtMoved = false;
        for (const char* n : { "_on", "_f" })
            if (auto* p = proc.apvts.getParameter (pp::pid (s, (juce::String (pre) + n).toRawUTF8()))) p->beginChangeGesture();
        return;
    }
    int best = -1;
    float bd = 18.0f;
    for (int i = 0; i < pp::nBands; ++i)
    {
        const float x = xOf (pp::raw (proc.apvts, pp::pid (i, "freq"))), y = yOf (juce::jlimit (-gView, gView, pp::raw (proc.apvts, pp::pid (i, "gain")) * scaleOf (proc)));
        const float d = std::hypot (x - (float) e.x, y - (float) e.y);
        if (d < bd) { bd = d; best = i; }
    }
    if (best >= 0)
    {
        selSet (best);
        dragBand = best;
        for (const char* n : { "freq", "gain" })
            if (auto* p = proc.apvts.getParameter (pp::pid (best, n))) p->beginChangeGesture();
    }
}

void CurveDisplay::mouseDrag (const juce::MouseEvent& e)
{
    if (dragFilt >= 0)
    {
        const int s = selGet();
        if (! filtMoved && std::abs (e.x - filtDownX) < 4) return;                    // simple clic en cours : pas de déplacement
        if (! filtMoved)
        {
            filtMoved = true;
            setParam (pp::pid (s, dragFilt == 0 ? "lc_mute" : "hc_mute"), 0.0f, false);       // on déplace : le filtre se remet en service
        }
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
    if (dragBand < 0) return;
    updateView();
    const float f = juce::jlimit (kFMin, kFMax, fOf (juce::jlimit (0.0f, (float) getWidth(), (float) e.x)));
    const bool exciter = juce::roundToInt (pp::raw (proc.apvts, pp::pid (dragBand, "type"))) == 0;      // Exciter : gain de 0 à +15 seulement
    const float g = std::round (juce::jlimit (exciter ? 0.0f : -gView, gView, gOf ((float) e.y)) * 10.0f) / 10.0f;
    setParam (pp::pid (dragBand, "freq"), f, false);
    const float sc = scaleOf (proc);                                                    // g est le gain EFFECTIF (affiché) : le réglage de la bande est g / Intensité
    const float gBase = sc > 0.05f ? std::round (juce::jlimit (-kGMax, kGMax, g / sc) * 10.0f) / 10.0f : pp::raw (proc.apvts, pp::pid (dragBand, "gain"));
    setParam (pp::pid (dragBand, "gain"), gBase, false);
    repaint();
}

void CurveDisplay::mouseUp (const juce::MouseEvent&)
{
    if (dragFilt >= 0)
    {
        const char* pre = dragFilt == 0 ? "lc" : "hc";
        for (const char* n : { "_on", "_f" })
            if (auto* p = proc.apvts.getParameter (pp::pid (selGet(), (juce::String (pre) + n).toRawUTF8()))) p->endChangeGesture();
        if (! filtMoved && pp::raw (proc.apvts, pp::pid (selGet(), (juce::String (pre) + "_on").toRawUTF8())) > 0.5f)       // simple clic sur un filtre posé : A/B
        {
            const auto id = pp::pid (selGet(), (juce::String (pre) + "_mute").toRawUTF8());
            setParam (id, pp::raw (proc.apvts, id) > 0.5f ? 0.0f : 1.0f, true);
        }
        dragFilt = -1;
        return;
    }
    if (dragBand < 0) return;
    for (const char* n : { "freq", "gain" })
        if (auto* p = proc.apvts.getParameter (pp::pid (dragBand, n))) p->endChangeGesture();
    dragBand = -1;
}

void CurveDisplay::mouseDoubleClick (const juce::MouseEvent& e)
{
    const int t = triangleAt (e.getPosition());
    if (t >= 0) { setParam (pp::pid (selGet(), t == 0 ? "lc_on" : "hc_on"), 0.0f, true); return; }         // double-clic sur un triangle : désactiver
    if ((float) e.y < kTop) return;
    const int s = selGet();
    const bool on = pp::raw (proc.apvts, pp::pid (s, "on")) > 0.5f;
    setParam (pp::pid (s, "on"), on ? 0.0f : 1.0f, true);
}

void CurveDisplay::mouseWheelMove (const juce::MouseEvent& e, const juce::MouseWheelDetails& d)
{
    const int t = triangleAt (e.getPosition());
    if (t >= 0)                                                                         // molette sur un triangle : pente 12 ↔ 24
    {
        const auto id = pp::pid (selGet(), t == 0 ? "lc_pente" : "hc_pente");
        setParam (id, d.deltaY > 0.0f ? 1.0f : 0.0f, true);
        return;
    }
    const int s = selGet();
    const float q = pp::raw (proc.apvts, pp::pid (s, "q"));
    const float nq = juce::jlimit (0.3f, 12.0f, q * (d.deltaY > 0.0f ? 1.08f : 1.0f / 1.08f));
    setParam (pp::pid (s, "q"), nq, true);
}

// ------------------------------------------------------------------ onglets
void BandTabs::paint (juce::Graphics& g)
{
    const int sel = selGet();
    const auto ord = pp::bandOrder (proc.apvts);
    for (int rank = 0; rank < pp::nBands; ++rank)
    {
        const int i = ord.order[rank];
        const auto r = cell (rank).toFloat();
        const int type = juce::roundToInt (pp::raw (proc.apvts, pp::pid (i, "type")));
        const bool on = pp::raw (proc.apvts, pp::pid (i, "on")) > 0.5f;
        const auto c = col::forType (type);
        g.setOpacity (on ? 1.0f : 0.45f);
        g.setColour (i == sel ? col::panel2 : col::panel);
        g.fillRoundedRectangle (r, 10.0f);
        g.setColour (i == sel ? c : col::line);
        g.drawRoundedRectangle (r.reduced (0.5f), 10.0f, 1.0f);
        g.setColour (c.withAlpha (on ? 1.0f : 0.45f));
        g.fillRect (r.getX(), r.getY() + 6.0f, 3.0f, r.getHeight() - 12.0f);
        g.setFont (juce::Font (juce::FontOptions (14.0f, juce::Font::bold)));
        g.drawText (juce::String (i + 1) + U8 (" · ") + pp::typeNames()[type], (int) r.getX() + 12, (int) r.getY() + 8, (int) r.getWidth() - 60, 18, juce::Justification::left);
        g.setColour (col::mut.withAlpha (on ? 1.0f : 0.45f));
        g.setFont (12.0f);
        const int canal = juce::roundToInt (pp::raw (proc.apvts, pp::pid (i, "canal")));
        g.drawText (pp::canalNames()[canal], (int) r.getRight() - 56, (int) r.getY() + 8, 48, 18, juce::Justification::right);
        const int forme = juce::roundToInt (pp::raw (proc.apvts, pp::pid (i, "forme")));
        g.drawText (pp::formeNames()[forme] + U8 (" · ") + fmtFreq (pp::raw (proc.apvts, pp::pid (i, "freq"))) + U8 (" · ") + fmtGain (pp::raw (proc.apvts, pp::pid (i, "gain")) * scaleOf (proc)),
                    (int) r.getX() + 12, (int) r.getY() + 30, (int) r.getWidth() - 16, 18, juce::Justification::left);
    }
}

juce::String BandTabs::helpAt (juce::Point<int> p) const
{
    for (int rank = 0; rank < pp::nBands; ++rank)
        if (cell (rank).contains (p)) return U8 ("Bande ") + juce::String (rank + 1) + U8 (" : clic = sélectionner, double-clic = activer / couper. Les bandes sont numérotées selon leur fréquence.");
    return {};
}

void BandTabs::mouseDoubleClick (const juce::MouseEvent& e)
{
    const auto ord = pp::bandOrder (proc.apvts);
    for (int rank = 0; rank < pp::nBands; ++rank)
        if (cell (rank).contains (e.getPosition()))
            if (auto* p = proc.apvts.getParameter (pp::pid (ord.order[rank], "on")))
            {
                p->beginChangeGesture();
                p->setValueNotifyingHost (p->getValue() > 0.5f ? 0.0f : 1.0f);
                p->endChangeGesture();
            }
}

void BandTabs::mouseDown (const juce::MouseEvent& e)
{
    const auto ord = pp::bandOrder (proc.apvts);
    for (int rank = 0; rank < pp::nBands; ++rank)
        if (cell (rank).contains (e.getPosition())) { selSet (ord.order[rank]); return; }
}

// ------------------------------------------------------------------ fiche de bande
void BandCard::rebuild (int b)
{
    band = b;
    types.reset(); onButton.reset(); onAttach.reset(); forme.reset(); canal.reset();
    posKnobs.clear(); typeKnobs.clear(); typeSegs.clear(); typeSegTitles.clear();
    removeAllChildren();

    BandCard* self = this;
    auto& ap = proc.apvts;
    const int type = juce::roundToInt (pp::raw (ap, pp::pid (b, "type")));
    colour = col::forType (type);

    types = std::make_unique<TypeButtons> (ap, pp::pid (b, "type"), [safe = juce::Component::SafePointer<BandCard> (this)] { if (safe != nullptr) safe->rebuild (safe->band); });
    addAndMakeVisible (*types);
    onButton = std::make_unique<PillButton> ("Delta", "Delta");
    onAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (ap, pp::pid (b, "solo"), *onButton);
    onButton->onClick = [this, b]                                                  // delta de bande EXCLUSIF : activer celui-ci coupe les autres ; Maj / Ctrl / Cmd-clic = en écouter plusieurs
    {
        const auto m = juce::ModifierKeys::getCurrentModifiers();
        if (! onButton->getToggleState() || m.isShiftDown() || m.isCtrlDown() || m.isCommandDown()) return;
        for (int o = 0; o < pp::nBands; ++o)
            if (o != b)
                if (auto* p = proc.apvts.getParameter (pp::pid (o, "solo"))) p->setValueNotifyingHost (0.0f);
    };
    addAndMakeVisible (*onButton);
    forme = std::make_unique<Seg> (ap, pp::pid (b, "forme"), pp::formeNames(), colour);
    addAndMakeVisible (*forme);
    canal = std::make_unique<Seg> (ap, pp::pid (b, "canal"), pp::canalNames(), colour, [safe = juce::Component::SafePointer<BandCard> (self)] { if (safe != nullptr) safe->rebuild (safe->band); });
    addAndMakeVisible (*canal);

    auto addPos = [&] (const char* id, const juce::String& label, std::function<juce::String (double)> f)
    {
        posKnobs.push_back (std::make_unique<Knob> (ap, pp::pid (b, id), label, colour, std::move (f)));
        addAndMakeVisible (*posKnobs.back());
    };
    addPos ("freq", U8 ("Fréquence"), [] (double v) { return fmtFreq (v); });
    addPos ("q", "Q", [] (double v) { return juce::String (v, 2); });
    juce::String gl[4] = { U8 ("Gain (+ seulement)"), U8 ("Gain (− réduit)"), U8 ("Gain (±)"), U8 ("Gain (− expandeur)") };
    addPos ("gain", gl[type], [] (double v) { return fmtGain (v); });

    auto addKnob = [&] (const char* id, const juce::String& label, std::function<juce::String (double)> f)
    {
        typeKnobs.push_back (std::make_unique<Knob> (ap, pp::pid (b, id), label, colour, std::move (f)));
        addAndMakeVisible (*typeKnobs.back());
    };
    auto addSeg = [&] (const char* id, const juce::String& title, const juce::StringArray& names)
    {
        typeSegs.push_back (std::make_unique<Seg> (ap, pp::pid (b, id), names, colour, [safe = juce::Component::SafePointer<BandCard> (self)] { if (safe != nullptr) safe->rebuild (safe->band); }));
        typeSegTitles.push_back (title);
        addAndMakeVisible (*typeSegs.back());
    };
    if (type == 0)      { addSeg ("mode", "PROFIL", pp::modeNames()); addKnob ("drive", "Harmoniques", [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; });
                          addKnob ("purete", U8 ("Pureté"), [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; });
                          addKnob ("tilt", "Tilt", [] (double v) { return (v > 0 ? juce::String ("+") : juce::String()) + juce::String (v, 2); }); }
    else if (type == 1) { addKnob ("width", "Largeur", [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; }); }
    else if (type == 2)
    {
        addSeg ("cible", "CIBLE", pp::cibleNames());
        addKnob ("time", U8 ("Durée"), [] (double v) { return juce::String (juce::roundToInt (v)) + " ms"; });
        addKnob ("sens", U8 ("Sensibilité"), [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; });
    }
    else
    {
        addKnob ("amount", "Amount", [] (double v) { return juce::String (juce::roundToInt (v)) + " %  (" + juce::String (juce::roundToInt (-60.0 + 0.48 * v)) + " dBFS)"; });
        addKnob ("release", U8 ("Relâchement"), [] (double v) { return juce::String (juce::roundToInt (v)) + " ms"; });
    }
    // ---- aides du bandeau ----
    aide (*onButton, U8 ("Delta de la bande : n'écoute que le signal ajouté (wet) par cette bande. Activer celui d'une autre bande remplace celui-ci ; Maj ou Ctrl + clic pour en écouter plusieurs."));
    forme->setOptionHelp ({ U8 ("Shelf grave : la bande agit en dessous de la fréquence (le Q est fixe)."), U8 ("Cloche : la bande agit autour de la fréquence, avec la largeur donnée par Q."), U8 ("Shelf aigu : la bande agit au-dessus de la fréquence (le Q est fixe).") });
    canal->setOptionHelp ({ U8 ("Stéréo : la bande traite les deux canaux (Exciter : source prise sur le milieu, même wet à gauche et à droite)."), U8 ("Mid : ne traite que le milieu (L+R)/2."), U8 ("Side : ne traite que les côtés (L−R)/2."),
                            U8 ("L : ne traite que le canal gauche."), U8 ("R : ne traite que le canal droit.") });
    aide (*posKnobs[0], U8 ("Fréquence de la bande (pour un shelf : fréquence de coupure). Maj = réglage fin, double-clic = valeur par défaut."));
    aide (*posKnobs[1], U8 ("Q : largeur de la cloche (plus élevé = plus étroit). Sans effet sur les shelfs."));
    const juce::String aideGain[4] = { U8 ("Gain de l'Exciter (0 à +15 dB) : renfort saturé de la zone (+6 dB ≈ la zone renforcée de 6 dB, avec le grain du profil). Toutes les bandes sont multipliées par Intensité (en haut)."),
                                       U8 ("Gain du Tame : négatif = atténue les résonances jusqu'à cette profondeur, positif = accentue les pics déjà forts."),
                                       U8 ("Gain du Shape : appliqué aux transitoires ou au sustain (selon Cible), dans les deux sens."),
                                       U8 ("Gain du Lift : positif = relève ce qui est faible, négatif = l'abaisse (expandeur).") };
    aide (*posKnobs[2], aideGain[type]);
    if (type == 0)
    {
        typeSegs[0]->setOptionHelp ({ U8 ("Doux : distorsion douce (tanh), harmoniques impaires discrètes : brillance sans agressivité."), U8 ("Chaud : distorsion asymétrique, harmoniques paires : chaleur et épaisseur."),
                                      U8 ("Mordant : écrêtage plus dur, harmoniques impaires : mordant et présence."), U8 ("Mordant chaud : écrêtage dur asymétrique : mordant et chaleur (profil de référence).") });
        aide (*typeKnobs[0], U8 ("Harmoniques : dureté de la saturation, de douce à dure (plus dur = plus d'harmoniques élevées). Le caractère ne dépend pas du niveau d'entrée."));
        aide (*typeKnobs[1], U8 ("Pureté : 0 % = la zone saturée entière est ajoutée (renfort et grain, naturel) ; 100 % = seulement les harmoniques nouvelles (plus fin, plus « piquant »)."));
        if (typeKnobs.size() > 2) aide (*typeKnobs[2], U8 ("Tilt : penche la zone avant la saturation : négatif = plus de saturation dans le bas de la zone, positif = dans le haut."));
    }
    else if (type == 1)
        aide (*typeKnobs[0], U8 ("Largeur de traitement : de fin (résonances étroites) à large (bosses larges)."));
    else if (type == 2)
    {
        typeSegs[0]->setOptionHelp ({ U8 ("Transitoires : le gain s'applique aux attaques de la zone."), U8 ("Sustain : le gain s'applique au corps du son, entre les attaques.") });
        aide (*typeKnobs[0], U8 ("Durée : combien de temps l'effet dure après une attaque (5 à 200 ms)."));
        aide (*typeKnobs[1], U8 ("Sensibilité : à 100 % toutes les attaques déclenchent, à 0 % seulement les plus vives."));
    }
    else
    {
        aide (*typeKnobs[0], U8 ("Amount : seuil absolu du relevé (−60 à −12 dBFS). Plus il monte, plus de matière est relevée."));
        aide (*typeKnobs[1], U8 ("Relâchement : vitesse à laquelle le gain revient (20 à 1000 ms)."));
    }
    linkSlider.reset(); linkAttach.reset();
    if (type != 0 && juce::roundToInt (pp::raw (ap, pp::pid (b, "canal"))) == 0)         // liaison des détecteurs L/R : Tame, Shape, Lift en canal Stéréo
    {
        linkSlider = std::make_unique<juce::Slider> (juce::Slider::LinearHorizontal, juce::Slider::TextBoxRight);
        linkSlider->setTextBoxStyle (juce::Slider::TextBoxRight, false, 50, 22);
        linkSlider->setNumDecimalPlacesToDisplay (0);
        linkSlider->setColour (juce::Slider::trackColourId, colour);
        linkSlider->setColour (juce::Slider::thumbColourId, col::txt);
        linkSlider->setColour (juce::Slider::textBoxTextColourId, col::txt);
        linkSlider->setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
        linkAttach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (ap, pp::pid (b, "link"), *linkSlider);
        linkSlider->textFromValueFunction = [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; };
        linkSlider->updateText();
        addAndMakeVisible (*linkSlider);
        aide (*linkSlider, U8 ("Liaison L/R des détecteurs : 0 % = indépendants (précis par canal, l'image peut bouger), 100 % = mêmes décisions (image stable). 50 % = compromis."));
    }
    resized();
    repaint();
}

void BandCard::resized()
{
    labels.clear();
    if (! types) return;
    auto area = getLocalBounds().reduced (14);
    const int gap = 36, total = area.getWidth() - 2 * gap;
    const int w1 = (int) (total * 0.9 / 3.15), w2 = (int) (total * 1.0 / 3.15), w3 = total - w1 - w2;
    const int x1 = area.getX(), x2 = x1 + w1 + gap, x3 = x2 + w2 + gap;
    const int bottomH = 58, topH = area.getHeight() - bottomH - 12, yTop = area.getY(), yBot = yTop + topH + 12;

    // colonne 1
    labels.push_back ({ "TYPE DE TRAITEMENT", { x1, yTop, w1 - 120, 20 } });
    onButton->setBounds (x1 + w1 - 112, yTop - 3, 112, 26);
    types->setBounds (x1, yTop + 30, w1, topH - 30);
    labels.push_back ({ "FORME", { x1, yBot, w1, 16 } });
    forme->setBounds (x1, yBot + 22, juce::jmin (w1, forme->preferredWidth()), 30);
    // colonne 2
    labels.push_back ({ "POSITION", { x2, yTop, w2, 20 } });
    int kx = x2;
    for (auto& k : posKnobs) { k->setBounds (kx, yTop + 24, Knob::preferredWidth(), Knob::preferredHeight()); kx += Knob::preferredWidth() + 10; }
    labels.push_back ({ "CANAL", { x2, yBot, w2, 16 } });
    canal->setBounds (x2, yBot + 22, juce::jmin (w2, canal->preferredWidth()), 30);
    // colonne 3
    const int type = juce::roundToInt (pp::raw (proc.apvts, pp::pid (band, "type")));
    if (type != 2) labels.push_back ({ juce::String (pp::typeNames()[type]).toUpperCase(), { x3, yTop, w3, 20 } });
    int cx = x3, cy = yTop + 24;
    if (type == 0)
    {
        for (size_t i = 0; i < typeSegs.size(); ++i)
        {
            labels.push_back ({ typeSegTitles[i], { x3, cy, w3, 16 } });
            typeSegs[i]->setBounds (x3, cy + 20, juce::jmin (w3, typeSegs[i]->preferredWidth()), 30);
            cy += 56;
        }
        // Saturation (et Tilt en mode Bande) à droite de la rangée SOURCE : sous le sélecteur de mode, qui est large
        int kx2 = x3 + (typeSegs.size() > 1 ? juce::jmin (w3, typeSegs[1]->preferredWidth()) : 0) + 28;
        for (auto& k : typeKnobs) { k->setBounds (kx2, yTop + 76, Knob::preferredWidth(), Knob::preferredHeight()); kx2 += Knob::preferredWidth() + 2; }
    }
    else
    {
        for (size_t i = 0; i < typeSegs.size(); ++i)
        {
            const int sw = juce::jmin (w3, typeSegs[i]->preferredWidth());
            labels.push_back ({ typeSegTitles[i], { cx, cy + 12, sw, 16 } });
            typeSegs[i]->setBounds (cx, cy + 34, sw, 30);
            cx += sw + 16;
        }
        for (auto& k : typeKnobs) { k->setBounds (cx, cy, Knob::preferredWidth() + 40 * (type == 3), Knob::preferredHeight()); cx += Knob::preferredWidth() + 10 + 40 * (type == 3); }
    }
    if (linkSlider)
    {
        labels.push_back ({ U8 ("LIAISON L/R"), { x3, yBot, 200, 16 } });
        linkSlider->setBounds (x3, yBot + 22, 215, 26);
    }
}

void BandCard::paint (juce::Graphics& g)
{
    g.setColour (col::panel);
    g.fillRoundedRectangle (getLocalBounds().toFloat(), 10.0f);
    g.setColour (col::line);
    g.drawRoundedRectangle (getLocalBounds().toFloat().reduced (0.5f), 10.0f, 1.0f);
    g.setColour (col::mut);
    g.setFont (juce::Font (juce::FontOptions (11.0f, juce::Font::bold)));
    for (const auto& l : labels)
    {
        juce::String spaced;
        for (auto c : l.text) { spaced << juce::String::charToString (c) << juce::String::charToString (0x200A); }
        g.drawText (spaced, l.r, juce::Justification::centredLeft);
    }
}

// ------------------------------------------------------------------ éditeur
PrismeEditor::PrismeEditor (PrismeProcessor& p)
    : AudioProcessorEditor (&p), proc (p),
      display (p, [this] { return sel; }, [this] (int b) { select (b); }),
      tabs (p, [this] { return sel; }, [this] (int b) { select (b); }),
      card (p)
{
    addAndMakeVisible (content);
    for (auto* c : std::initializer_list<juce::Component*> { &display, &tabs, &card, &deltaPosBtn, &deltaNegBtn, &specBtn, &outSlider, &scaleSlider, &helpBar })
        content.addAndMakeVisible (c);
    content.addMouseListener (&helpBar, true);
    content.addAndMakeVisible (autogainPill);
    autogainPill.icone = [] (juce::Graphics& g, juce::Rectangle<float> r, bool on)             // témoin rond (vert allumé quand l'autogain est actif)
    {
        const auto c = r.getCentre();
        if (on)
        {
            for (int i = 3; i >= 1; --i) { g.setColour (juce::Colour (0xff7ddc6a).withAlpha (0.10f)); g.fillEllipse (c.x - 4.5f - (float) i * 1.4f, c.y - 4.5f - (float) i * 1.4f, 9.0f + (float) i * 2.8f, 9.0f + (float) i * 2.8f); }
            g.setColour (juce::Colour (0xff7ddc6a));
        }
        else g.setColour (juce::Colour (0xff3a414c));
        g.fillEllipse (c.x - 4.5f, c.y - 4.5f, 9.0f, 9.0f);
    };
    autogainPill.actif = [this] { return pp::raw (proc.apvts, "sonie") > 0.5f; };
    autogainPill.libelle = [this]
    {
        if (pp::raw (proc.apvts, "sonie") < 0.5f) return U8 ("Autogain : inactif");
        const float g = proc.sonieGainDb.load();
        return U8 ("Autogain  ") + (g > 0.0f ? juce::String ("+") : juce::String()) + juce::String (g, 1).replace ("-", U8 ("−")) + " dB";
    };
    autogainPill.clic = [this]
    {
        if (auto* p = proc.apvts.getParameter ("sonie"))
        {
            p->beginChangeGesture();
            p->setValueNotifyingHost (pp::raw (proc.apvts, "sonie") > 0.5f ? 0.0f : 1.0f);
            p->endChangeGesture();
        }
    };
    aide (autogainPill, U8 ("Autogain : recale en continu le signal traité sur la sonie du signal d'entrée, pour comparer (bypass) à volume égal. Le curseur Sortie est alors inactif. Cliquer pour activer ou couper."));
    deltaPosAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (p.apvts, "dpos", deltaPosBtn);
    deltaNegAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (p.apvts, "dneg", deltaNegBtn);
    specBtn.setToggleState (true, juce::dontSendNotification);
    specBtn.onClick = [this] { display.setShowSpectrum (specBtn.getToggleState()); };

    outSlider.setSliderStyle (juce::Slider::LinearHorizontal);
    outSlider.setTextBoxStyle (juce::Slider::TextBoxRight, false, 70, 22);
    outSlider.setTextValueSuffix (" dB");
    outSlider.setColour (juce::Slider::trackColourId, col::mut);
    outSlider.setColour (juce::Slider::thumbColourId, col::txt);
    outSlider.setColour (juce::Slider::textBoxTextColourId, col::txt);
    outSlider.setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    outAttach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (p.apvts, "output", outSlider);
    scaleSlider.setSliderStyle (juce::Slider::LinearHorizontal);
    scaleSlider.setTextBoxStyle (juce::Slider::TextBoxRight, false, 56, 22);
    scaleSlider.setColour (juce::Slider::trackColourId, col::mut);
    scaleSlider.setColour (juce::Slider::thumbColourId, col::txt);
    scaleSlider.setColour (juce::Slider::textBoxTextColourId, col::txt);
    scaleSlider.setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    scaleAttach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (p.apvts, "scale", scaleSlider);
    scaleSlider.textFromValueFunction = [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; };      // après l'attachement, qui installe la sienne
    scaleSlider.updateText();
    aide (scaleSlider, U8 ("Intensité : multiplie proportionnellement le gain de TOUTES les bandes. 100 % = vos réglages ; moins = traitement réduit ; plus (jusqu'à 200 %) = poussé à l'extrême."));
    aide (outSlider, U8 ("Niveau de sortie du plugin (−12 à +12 dB)."));
    aide (deltaPosBtn, U8 ("Delta + : n'écoute que ce que les bandes AJOUTENT (bandes à gain positif). Avec Delta − : tout le delta."));
    aide (deltaNegBtn, U8 ("Delta − : n'écoute que ce que les bandes RETIRENT (bandes à gain négatif). Avec Delta + : tout le delta."));
    aide (specBtn, U8 ("Affiche ou masque le spectre de fond dans la courbe."));

    // Le titre « P R I S M E » est un bouton de bypass cache (clic = bypass / retour) ; il s'assombrit quand le bypass est actif.
    content.onPaint = [this] (juce::Graphics& g)
    {
        const bool byp = pp::raw (proc.apvts, "bypass") > 0.5f;
        g.setColour (byp ? juce::Colour (0xff5a606b) : col::txt);
        g.setFont (juce::Font (juce::FontOptions (22.0f, juce::Font::bold)));
        g.drawText ("P R I S M E", 16, 14, 240, 30, juce::Justification::left);
        g.setColour (col::mut);
        g.setFont (12.0f);
        g.drawText (U8 ("Intensité"), scaleSlider.getX() - 66, scaleSlider.getY() + 2, 64, 22, juce::Justification::centredRight);
        g.drawText ("Sortie", outSlider.getX() - 46, outSlider.getY() + 2, 44, 22, juce::Justification::centredRight);
    };
    content.onMouseDown = [this] (const juce::MouseEvent& e)
    {
        if (juce::Rectangle<int> (10, 8, 190, 42).contains (e.getPosition()))
            if (auto* b = proc.apvts.getParameter ("bypass"))
            {
                b->beginChangeGesture();
                b->setValueNotifyingHost (b->getValue() > 0.5f ? 0.0f : 1.0f);
                b->endChangeGesture();
            }
    };

    card.rebuild (sel);
    setResizable (true, true);
    getConstrainer()->setFixedAspectRatio ((double) baseW / (double) baseH);
    setResizeLimits (560, 390, 2240, 1560);
    const int saved = loadWidth();                                                     // derniere taille utilisee (fichier utilisateur)
    const int w = (saved >= 560 && saved <= 2240) ? saved : defaultW;
    setSize (w, juce::roundToInt ((double) w * baseH / baseW));
    startTimerHz (15);
}

PrismeEditor::~PrismeEditor()
{
    stopTimer();
    if (uiWidth > 0) saveWidth (uiWidth);
}

void PrismeEditor::select (int b)
{
    if (b == sel) return;
    sel = b;
    card.rebuild (sel);
    tabs.repaint();
    display.repaint();
}

void PrismeEditor::timerCallback()
{
    if (uiDirty && uiWidth == lastUiWidth) { saveWidth (uiWidth); uiDirty = false; }        // taille stable depuis un tick : on l'ecrit
    lastUiWidth = uiWidth;
    tabs.repaint();
    content.repaint (0, 0, 260, 50);
    const bool ag = pp::raw (proc.apvts, "sonie") > 0.5f;                                    // Sortie grisé quand l'autogain est actif
    if (outSlider.isEnabled() == ag) { outSlider.setEnabled (! ag); outSlider.setAlpha (ag ? 0.45f : 1.0f); }
    autogainPill.repaint();
}

void PrismeEditor::paint (juce::Graphics& g)
{
    g.fillAll (col::bg);
}

void PrismeEditor::layoutContent()
{
    content.setBounds (0, 0, baseW, baseH);
    auto a = juce::Rectangle<int> (0, 0, baseW, baseH).reduced (16);
    auto header = a.removeFromTop (44);
    outSlider.setBounds (header.removeFromRight (190).withTrimmedTop (10).withHeight (26));
    autogainPill.setBounds (outSlider.getX() - 50 - 320, outSlider.getY() - 2, 320, 30);        // à gauche de « Sortie » ; s'ouvre vers la gauche
    header.removeFromRight (56 + 38);                                                          // place de la pastille repliée (30 px) entre l'Intensité et « Sortie »
    scaleSlider.setBounds (header.removeFromRight (190).withTrimmedTop (10).withHeight (26));
    header.removeFromRight (80);
    specBtn.setBounds (header.removeFromRight (90).withTrimmedTop (8).withHeight (28));
    header.removeFromRight (8);
    deltaNegBtn.setBounds (header.removeFromRight (110).withTrimmedTop (8).withHeight (28));
    header.removeFromRight (6);
    deltaPosBtn.setBounds (header.removeFromRight (110).withTrimmedTop (8).withHeight (28));
    a.removeFromTop (6);
    helpBar.setBounds (a.removeFromBottom (30));
    a.removeFromBottom (8);
    const int cardH = 262, tabsH = 64;
    card.setBounds (a.removeFromBottom (cardH));
    a.removeFromBottom (10);
    tabs.setBounds (a.removeFromBottom (tabsH));
    a.removeFromBottom (10);
    display.setBounds (a);
}

void PrismeEditor::resized()
{
    layoutContent();
    content.setTransform (juce::AffineTransform::scale ((float) getWidth() / (float) baseW));
    if (getWidth() > 0) { uiWidth = getWidth(); uiDirty = true; }
}
