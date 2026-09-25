#include "PluginEditor.h"

using namespace prismeUi;
namespace pp = prismeParams;
using prismeParams::U8;

static constexpr float kFMin = 20.0f, kFMax = 20000.0f, kGMax = 15.0f;

// ------------------------------------------------------------------ courbe
CurveDisplay::CurveDisplay (PrismeProcessor& p, std::function<int()> getSel, std::function<void (int)> setSel)
    : proc (p), selGet (std::move (getSel)), selSet (std::move (setSel))
{
    startTimerHz (30);
}

float CurveDisplay::xOf (float f) const { return std::log (f / kFMin) / std::log (kFMax / kFMin) * (float) getWidth(); }
float CurveDisplay::fOf (float x) const { return kFMin * std::pow (kFMax / kFMin, x / (float) getWidth()); }
float CurveDisplay::yOf (float g) const { const float h = (float) getHeight(); return h / 2.0f - (g / kGMax) * (h / 2.0f - 16.0f); }
float CurveDisplay::gOf (float y) const { const float h = (float) getHeight(); return (h / 2.0f - y) / (h / 2.0f - 16.0f) * kGMax; }

// Allure indicative de la correction (0 cloche, 1 shelf grave, 2 shelf aigu) : la vraie réponse dépend du type de traitement.
float CurveDisplay::response (int shape, float f0, float q, float gain, float f)
{
    const float oct = std::log2 (f / f0), s = 1.0f / juce::jmax (0.25f, q);
    if (shape == 0) { const float u = oct / (0.55f * s + 0.05f); return gain * std::exp (-u * u); }
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
    if (showSpec) repaint();
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

    const int sel = selGet();
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
        g.drawText (juce::String (i + 1), (int) (x - r), (int) (y - r), (int) (2 * r), (int) (2 * r), juce::Justification::centred);
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
    const float g = std::round (juce::jlimit (-kGMax, kGMax, gOf ((float) e.y)) * 10.0f) / 10.0f;
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
    for (int i = 0; i < pp::nBands; ++i)
    {
        const auto r = cell (i).toFloat();
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

void BandTabs::mouseDown (const juce::MouseEvent& e)
{
    for (int i = 0; i < pp::nBands; ++i)
        if (cell (i).contains (e.getPosition())) { selSet (i); return; }
}

// ------------------------------------------------------------------ fiche de bande
void BandCard::rebuild (int b)
{
    band = b;
    types.reset(); onButton.reset(); onAttach.reset(); forme.reset(); canal.reset();
    posKnobs.clear(); typeKnobs.clear(); typeSegs.clear(); typeSegTitles.clear();
    removeAllChildren();

    auto& ap = proc.apvts;
    const int type = juce::roundToInt (pp::raw (ap, pp::pid (b, "type")));
    colour = col::forType (type);

    types = std::make_unique<TypeButtons> (ap, pp::pid (b, "type"), [safe = juce::Component::SafePointer<BandCard> (this)] { if (safe != nullptr) safe->rebuild (safe->band); });
    addAndMakeVisible (*types);
    onButton = std::make_unique<PillButton> (U8 ("Bande coupée"), "Bande active");
    onAttach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (ap, pp::pid (b, "on"), *onButton);
    addAndMakeVisible (*onButton);
    forme = std::make_unique<Seg> (ap, pp::pid (b, "forme"), pp::formeNames(), colour);
    addAndMakeVisible (*forme);
    canal = std::make_unique<Seg> (ap, pp::pid (b, "canal"), pp::canalNames(), colour);
    addAndMakeVisible (*canal);

    auto addPos = [&] (const char* id, const juce::String& label, std::function<juce::String (double)> f)
    {
        posKnobs.push_back (std::make_unique<Knob> (ap, pp::pid (b, id), label, colour, std::move (f)));
        addAndMakeVisible (*posKnobs.back());
    };
    addPos ("freq", U8 ("Fréquence"), [] (double v) { return fmtFreq (v); });
    addPos ("q", "Q", [] (double v) { return juce::String (v, 2); });
    juce::String gl[4] = { U8 ("Gain (− négatif)"), U8 ("Gain (− réduit)"), U8 ("Gain (±)"), U8 ("Gain (− expandeur)") };
    addPos ("gain", gl[type], [] (double v) { return fmtGain (v); });

    auto addKnob = [&] (const char* id, const juce::String& label, std::function<juce::String (double)> f)
    {
        typeKnobs.push_back (std::make_unique<Knob> (ap, pp::pid (b, id), label, colour, std::move (f)));
        addAndMakeVisible (*typeKnobs.back());
    };
    auto addSeg = [&] (const char* id, const juce::String& title, const juce::StringArray& names)
    {
        typeSegs.push_back (std::make_unique<Seg> (ap, pp::pid (b, id), names, colour));
        typeSegTitles.push_back (title);
        addAndMakeVisible (*typeSegs.back());
    };
    if (type == 0)      { addSeg ("mode", "MODE", pp::modeNames()); addSeg ("source", "SOURCE", pp::sourceNames()); }
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
        U8 ("Ajoute des harmoniques dans la zone. Un gain négatif retire de la couleur (à renommer)."),
        U8 ("Atténue les résonances qui ressortent dans la zone (gain −) ou accentue les pics déjà forts (gain +). Largeur : de fin à large."),
        U8 ("Agit sur les transitoires ou sur le sustain de la bande, dans les deux sens. Durée : combien de temps dure l'effet après une attaque."),
        U8 ("Relève ce qui est faible dans la zone (gain +) ou l'abaisse (gain −). Amount : plus il monte, plus de matière est concernée. Protection du souffle automatique.") };
    note = notes[type];
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
    g.drawFittedText (note, noteRect, juce::Justification::topLeft, 3);
}

// ------------------------------------------------------------------ éditeur
PrismeEditor::PrismeEditor (PrismeProcessor& p)
    : AudioProcessorEditor (&p), proc (p),
      display (p, [this] { return sel; }, [this] (int b) { select (b); }),
      tabs (p, [this] { return sel; }, [this] (int b) { select (b); }),
      card (p)
{
    addAndMakeVisible (display);
    addAndMakeVisible (tabs);
    addAndMakeVisible (card);
    addAndMakeVisible (deltaBtn);
    addAndMakeVisible (specBtn);
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
    addAndMakeVisible (outSlider);
    outAttach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (p.apvts, "output", outSlider);

    card.rebuild (sel);
    setSize (1120, 780);
    setResizable (true, true);
    setResizeLimits (900, 700, 1800, 1200);
    startTimerHz (15);
}

PrismeEditor::~PrismeEditor()
{
    stopTimer();
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
    tabs.repaint();
}

void PrismeEditor::paint (juce::Graphics& g)
{
    g.fillAll (col::bg);
    g.setColour (col::txt);
    g.setFont (juce::Font (juce::FontOptions (22.0f, juce::Font::bold)));
    g.drawText ("P R I S M E", 16, 14, 240, 30, juce::Justification::left);
    const double fs = juce::jmax (8000.0, proc.getSampleRateHz());
    const auto pill = juce::Rectangle<float> (200.0f, 16.0f, 230.0f, 26.0f);
    g.setColour (col::panel);
    g.fillRoundedRectangle (pill, 13.0f);
    g.setColour (col::line);
    g.drawRoundedRectangle (pill.reduced (0.5f), 13.0f, 1.0f);
    g.setColour (col::mut);
    g.setFont (12.0f);
    g.drawText (U8 ("Latence ") + juce::String (prisme::Engine::latence) + U8 (" éch. · ") + juce::String (prisme::Engine::latence / fs * 1000.0, 2) + " ms",
                pill.toNearestInt(), juce::Justification::centred);
}

void PrismeEditor::resized()
{
    auto a = getLocalBounds().reduced (16);
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
