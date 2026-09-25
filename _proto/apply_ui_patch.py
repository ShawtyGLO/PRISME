"""Patch ponctuel de l'interface PRISME v0.3 (retours de test) — appliqué une fois ; conservé pour mémoire."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def rd(n):
    return open(os.path.join(SRC, n), encoding="utf-8").read()


def wr(n, s):
    open(os.path.join(SRC, n), "w", encoding="utf-8").write(s)


h = rd("PluginEditor.h")
h = h.replace("    int ringPos = 0, sinceFft = 0;\n};",
              "    int ringPos = 0, sinceFft = 0;\n\n    struct Ana { std::vector<float> ring = std::vector<float> (2048, 0.0f), spec = std::vector<float> (1024, -120.0f); int pos = 0, since = 0; };\n    std::array<Ana, prismeParams::nBands> wetAna;              // spectre du delta de chaque bande (le wet à la couleur du traitement)\n    void runFft (Ana& a);\n};", 1)
h = h.replace("    ~CurveDisplay() override { stopTimer(); }", "    ~CurveDisplay() override { stopTimer(); proc.setAnalyserActive (false); }", 1)
h = h.replace("    void mouseDown (const juce::MouseEvent&) override;\n\nprivate:\n    juce::Rectangle<int> cell",
              "    void mouseDown (const juce::MouseEvent&) override;\n    void mouseDoubleClick (const juce::MouseEvent&) override;\n\nprivate:\n    juce::Rectangle<int> cell", 1)
a = h.index("class PrismeEditor")
h = h[:a] + '''// Contenu de l'editeur, dessine a une taille de base fixe puis mis a l'echelle (le redimensionnement garde les proportions de tous les elements).
class EditorContent : public juce::Component
{
public:
    std::function<void (juce::Graphics&)> onPaint;
    std::function<void (const juce::MouseEvent&)> onMouseDown;
    void paint (juce::Graphics& g) override { if (onPaint) onPaint (g); }
    void mouseDown (const juce::MouseEvent& e) override { if (onMouseDown) onMouseDown (e); }
};

class PrismeEditor : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit PrismeEditor (PrismeProcessor&);
    ~PrismeEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

    static constexpr int baseW = 1120, baseH = 780;

private:
    void timerCallback() override;
    void select (int b);
    void layoutContent();

    PrismeProcessor& proc;
    int sel = 2;
    EditorContent content;
    CurveDisplay display;
    BandTabs tabs;
    BandCard card;
    prismeUi::PillButton deltaBtn { U8 ("Écouter le delta"), U8 ("Écouter le delta") }, specBtn { "Spectre", "Spectre" };
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> deltaAttach;
    juce::Slider outSlider;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> outAttach;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (PrismeEditor)
};
'''
wr("PluginEditor.h", h)

c = rd("PluginEditor.cpp")
c = c.replace("    startTimerHz (30);\n}\n\nfloat CurveDisplay::xOf", "    proc.setAnalyserActive (true);\n    startTimerHz (30);\n}\n\nfloat CurveDisplay::xOf", 1)
c = c.replace("// Allure indicative de la correction (0 cloche, 1 shelf grave, 2 shelf aigu)", "// Allure indicative de la correction (0 shelf grave, 1 cloche, 2 shelf aigu)")
c = c.replace("    if (shape == 0) { const float u = oct", "    if (shape == 1) { const float u = oct")

i0 = c.index("    if (sinceFft >= 1024)\n    {")
i1 = c.index("void CurveDisplay::paint")
new = '''    if (sinceFft >= 1024)
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

'''
c = c[:i0] + new + c[i1:]

marker = "    const int sel = selGet();\n    struct B { bool on;"
wet = '''    {   // signal WET de chaque bande, a la couleur du traitement (le rendu bouge dans la courbe : pas la courbe)
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

'''
assert marker in c
c = c.replace(marker, wet + marker, 1)

c = c.replace("void BandTabs::mouseDown (const juce::MouseEvent& e)", '''void BandTabs::mouseDoubleClick (const juce::MouseEvent& e)
{
    for (int i = 0; i < pp::nBands; ++i)
        if (cell (i).contains (e.getPosition()))
            if (auto* p = proc.apvts.getParameter (pp::pid (i, "on")))
            {
                p->beginChangeGesture();
                p->setValueNotifyingHost (p->getValue() > 0.5f ? 0.0f : 1.0f);
                p->endChangeGesture();
            }
}

void BandTabs::mouseDown (const juce::MouseEvent& e)''', 1)

c = c.replace('onButton = std::make_unique<PillButton> (U8 ("Bande coupée"), U8 ("Bande active"));', 'onButton = std::make_unique<PillButton> ("Delta", "Delta");')
c = c.replace('ButtonAttachment> (ap, pp::pid (b, "on"), *onButton);', 'ButtonAttachment> (ap, pp::pid (b, "solo"), *onButton);')
c = c.replace('if (type == 0)      { addSeg ("mode", "MODE", pp::modeNames()); addSeg ("source", "SOURCE", pp::sourceNames()); }',
              'if (type == 0)      { addSeg ("mode", "MODE", pp::modeNames()); addSeg ("source", "SOURCE", pp::sourceNames()); addKnob ("drive", "Saturation", [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; }); }')
c = c.replace("            cy += 56;\n        }\n    }",
              "            cy += 56;\n        }\n        int maxW = 0;\n        for (auto& sg : typeSegs) maxW = juce::jmax (maxW, juce::jmin (w3, sg->preferredWidth()));\n        for (auto& k : typeKnobs) k->setBounds (x3 + maxW + 24, yTop + 24, Knob::preferredWidth(), Knob::preferredHeight());\n    }", 1)

i = c.index("// ------------------------------------------------------------------ éditeur")
c = c[:i] + '''// ------------------------------------------------------------------ éditeur
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
    setSize (baseW, baseH);
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
}
'''
wr("PluginEditor.cpp", c)
print("ok")
