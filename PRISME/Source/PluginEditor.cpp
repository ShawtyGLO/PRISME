#include "PluginEditor.h"

using namespace prismeUi;
namespace pp = prismeParams;
using prismeParams::U8;

static constexpr float kFMin = 20.0f, kFMax = 20000.0f, kGMax = 15.0f;

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
    proc.setAnalyserActive (true);
    startTimerHz (30);
}

float CurveDisplay::xOf (float f) const { return std::log (f / kFMin) / std::log (kFMax / kFMin) * (float) getWidth(); }
float CurveDisplay::fOf (float x) const { return kFMin * std::pow (kFMax / kFMin, x / (float) getWidth()); }
float CurveDisplay::yOf (float g) const { const float h = (float) getHeight(); return h / 2.0f - (g / kGMax) * (h / 2.0f - 16.0f); }
float CurveDisplay::gOf (float y) const { const float h = (float) getHeight(); return (h / 2.0f - y) / (h / 2.0f - 16.0f) * kGMax; }

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
    for (int gdb : { -12, -6, 0, 6, 12 })
    {
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
                     pp::raw (proc.apvts, pp::pid (i, "q")), pp::raw (proc.apvts, pp::pid (i, "gain")) };
    }

    for (int i = 0; i < pp::nBands; ++i)
    {
        const auto& b = bands[i];
        if (! b.on) continue;
        const auto c = col::forType (b.type);
        juce::Path fill;
        fill.startNewSubPath (0.0f, yOf (0.0f));
        for (int x = 0; x <= (int) w; x += 2) fill.lineTo ((float) x, yOf (response (b.shape, b.f0, b.q, b.gain, fOf ((float) x))));
        fill.lineTo (w, yOf (0.0f));
        fill.closeSubPath();
        g.setColour (c.withAlpha (i == sel ? 0.22f : 0.11f));
        g.fillPath (fill);
        juce::Path line;
        bool pen = false;
        for (int x = 0; x <= (int) w; x += 2)
        {
            const float gg = response (b.shape, b.f0, b.q, b.gain, fOf ((float) x));
            if (std::abs (gg) < 0.08f) { pen = false; continue; }
            if (! pen) line.startNewSubPath ((float) x, yOf (gg)); else line.lineTo ((float) x, yOf (gg));
            pen = true;
        }
        g.setColour (c.withAlpha (i == sel ? 1.0f : 0.6f));
        g.strokePath (line, juce::PathStrokeType (i == sel ? 2.0f : 1.0f));
    }

    juce::Path sum;
    for (int x = 0; x <= (int) w; x += 2)
    {
        float s = 0.0f;
        for (const auto& b : bands) if (b.on) s += response (b.shape, b.f0, b.q, b.gain, fOf ((float) x));
        if (x == 0) sum.startNewSubPath (0.0f, yOf (s)); else sum.lineTo ((float) x, yOf (s));
    }
    const bool delta = pp::raw (proc.apvts, "delta") > 0.5f;
    g.setColour (delta ? juce::Colour (0xffffd166) : juce::Colour (0xfff4f6f8));
    g.strokePath (sum, juce::PathStrokeType (2.0f));

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
        g.drawText (U8 ("DELTA : on n'entend que ce que les bandes ajoutent ou retirent"), 12, 6, 500, 16, juce::Justification::left);
    }
    g.setColour (col::mut);
    g.setFont (11.0f);
    g.drawText (U8 ("Glisser un nœud : fréquence et gain · molette : Q · double-clic : bande active / coupée"), 12, (int) h - 30, (int) w - 24, 14, juce::Justification::left);
    g.restoreState();
    g.setColour (col::line);
    g.drawRoundedRectangle (getLocalBounds().toFloat().reduced (0.5f), 10.0f, 1.0f);
}

void CurveDisplay::mouseDown (const juce::MouseEvent& e)
{
    int best = -1;
    float bd = 18.0f;
    for (int i = 0; i < pp::nBands; ++i)
    {
        const float x = xOf (pp::raw (proc.apvts, pp::pid (i, "freq"))), y = yOf (pp::raw (proc.apvts, pp::pid (i, "gain")));
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
    if (dragBand < 0) return;
    const float f = juce::jlimit (kFMin, kFMax, fOf (juce::jlimit (0.0f, (float) getWidth(), (float) e.x)));
    const bool exciter = juce::roundToInt (pp::raw (proc.apvts, pp::pid (dragBand, "type"))) == 0;      // Exciter : gain de 0 à +15 seulement
    const float g = std::round (juce::jlimit (exciter ? 0.0f : -kGMax, kGMax, gOf ((float) e.y)) * 10.0f) / 10.0f;
    setParam (pp::pid (dragBand, "freq"), f, false);
    setParam (pp::pid (dragBand, "gain"), g, false);
    repaint();
}

void CurveDisplay::mouseUp (const juce::MouseEvent&)
{
    if (dragBand < 0) return;
    for (const char* n : { "freq", "gain" })
        if (auto* p = proc.apvts.getParameter (pp::pid (dragBand, n))) p->endChangeGesture();
    dragBand = -1;
}

void CurveDisplay::mouseDoubleClick (const juce::MouseEvent&)
{
    const int s = selGet();
    const bool on = pp::raw (proc.apvts, pp::pid (s, "on")) > 0.5f;
    setParam (pp::pid (s, "on"), on ? 0.0f : 1.0f, true);
}

void CurveDisplay::mouseWheelMove (const juce::MouseEvent&, const juce::MouseWheelDetails& d)
{
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
        g.drawText (pp::formeNames()[forme] + U8 (" · ") + fmtFreq (pp::raw (proc.apvts, pp::pid (i, "freq"))) + U8 (" · ") + fmtGain (pp::raw (proc.apvts, pp::pid (i, "gain"))),
                    (int) r.getX() + 12, (int) r.getY() + 30, (int) r.getWidth() - 16, 18, juce::Justification::left);
    }
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
    if (type == 0)      { addSeg ("mode", "PROFIL", pp::modeNames()); addSeg ("source", "SOURCE", pp::sourceNames()); addKnob ("drive", "Harmoniques", [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; });
                          if (juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "source"))) == 1) addKnob ("tilt", "Tilt", [] (double v) { return (v > 0 ? juce::String ("+") : juce::String()) + juce::String (v, 2); }); }
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
    juce::String notes[4] = {
        U8 ("Ajoute des harmoniques dans la zone, en parallèle et seulement sur les pics au-dessus du niveau courant (gain de 0 à +15 dB : dose du wet). Profil : Doux, Chaud, Mordant, Mordant chaud. Harmoniques : de doux à dur. En mode Bande, Tilt penche la source : plus de saturation dans les graves (−) ou les aigus (+)."),
        U8 ("Atténue les résonances qui ressortent dans la zone (gain −) ou accentue les pics déjà forts (gain +). Largeur : de fin à large."),
        U8 ("Agit sur les transitoires ou sur le sustain de la bande, dans les deux sens. Durée : combien de temps dure l'effet après une attaque."),
        U8 ("Relève ce qui est faible dans la zone (gain +) ou l'abaisse (gain −). Amount : plus il monte, plus de matière est concernée. Protection du souffle automatique.") };
    note = notes[type];
    linkSlider.reset(); linkAttach.reset();
    if (type != 0 && juce::roundToInt (pp::raw (ap, pp::pid (b, "canal"))) == 0)         // liaison des détecteurs L/R : Tame, Shape, Lift en canal Stéréo
    {
        linkSlider = std::make_unique<juce::Slider> (juce::Slider::LinearHorizontal, juce::Slider::TextBoxRight);
        linkSlider->setTextBoxStyle (juce::Slider::TextBoxRight, false, 50, 22);
        linkSlider->setNumDecimalPlacesToDisplay (0);
        linkSlider->textFromValueFunction = [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; };
        linkSlider->setColour (juce::Slider::trackColourId, colour);
        linkSlider->setColour (juce::Slider::thumbColourId, col::txt);
        linkSlider->setColour (juce::Slider::textBoxTextColourId, col::txt);
        linkSlider->setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
        linkAttach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (ap, pp::pid (b, "link"), *linkSlider);
        addAndMakeVisible (*linkSlider);
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
        for (auto& k : typeKnobs) { k->setBounds (kx2, yTop + 76, Knob::preferredWidth(), Knob::preferredHeight()); kx2 += Knob::preferredWidth() + 8; }
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
        noteRect = { x3 + 232, yBot, w3 - 232, bottomH };
    }
    else
        noteRect = { x3, yBot, w3, bottomH };
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
    g.setFont (12.0f);
    g.drawFittedText (note, noteRect, juce::Justification::topLeft, 5);
}

// ------------------------------------------------------------------ éditeur
PrismeEditor::PrismeEditor (PrismeProcessor& p)
    : AudioProcessorEditor (&p), proc (p),
      display (p, [this] { return sel; }, [this] (int b) { select (b); }),
      tabs (p, [this] { return sel; }, [this] (int b) { select (b); }),
      card (p)
{
    addAndMakeVisible (content);
    for (auto* c : std::initializer_list<juce::Component*> { &display, &tabs, &card, &deltaBtn, &specBtn, &outSlider })
        content.addAndMakeVisible (c);
    deltaAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (p.apvts, "delta", deltaBtn);
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

    // Le titre « P R I S M E » est un bouton de bypass cache (clic = bypass / retour) ; il s'assombrit quand le bypass est actif.
    content.onPaint = [this] (juce::Graphics& g)
    {
        const bool byp = pp::raw (proc.apvts, "bypass") > 0.5f;
        g.setColour (byp ? juce::Colour (0xff5a606b) : col::txt);
        g.setFont (juce::Font (juce::FontOptions (22.0f, juce::Font::bold)));
        g.drawText ("P R I S M E", 16, 14, 240, 30, juce::Justification::left);
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
    header.removeFromRight (8);
    specBtn.setBounds (header.removeFromRight (90).withTrimmedTop (8).withHeight (28));
    header.removeFromRight (8);
    deltaBtn.setBounds (header.removeFromRight (150).withTrimmedTop (8).withHeight (28));
    a.removeFromTop (6);
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
