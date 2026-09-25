#pragma once

#include <JuceHeader.h>
#include "Params.h"

// Éléments d'interface de PRISME (maquette v1 validée) : couleurs, bouton rotatif, sélecteur segmenté, boutons de type.
namespace prismeUi
{
using prismeParams::U8;
namespace col
{
const juce::Colour bg     { 0xff101215 };
const juce::Colour panel  { 0xff171a1f };
const juce::Colour panel2 { 0xff1d2127 };
const juce::Colour line   { 0xff2a2f37 };
const juce::Colour txt    { 0xffe6e9ee };
const juce::Colour mut    { 0xff8b93a1 };
const juce::Colour exc    { 0xffff8a3d };
const juce::Colour tam    { 0xff35d0c0 };
const juce::Colour sha    { 0xffa78bfa };
const juce::Colour lif    { 0xff7ddc6a };
inline juce::Colour forType (int t) { return t == 0 ? exc : t == 1 ? tam : t == 2 ? sha : lif; }
}

inline int textWidth (const juce::Font& f, const juce::String& t) { return juce::GlyphArrangement::getStringWidthInt (f, t); }

inline juce::String fmtFreq (double f) { return f >= 1000.0 ? juce::String (f / 1000.0, 2) + " k" : juce::String (juce::roundToInt (f)) + " Hz"; }
inline juce::String fmtGain (double g) { return (g > 0.0 ? "+" : "") + juce::String (g, 1) + " dB"; }

// Dessin des boutons rotatifs (arc de piste + arc de valeur + aiguille), comme la maquette.
class KnobLnF : public juce::LookAndFeel_V4
{
public:
    void drawRotarySlider (juce::Graphics& g, int x, int y, int w, int h, float pos, float a0, float a1, juce::Slider& s) override
    {
        const auto b = juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h).reduced (4.0f);
        const float r = juce::jmin (b.getWidth(), b.getHeight()) / 2.0f, cx = b.getCentreX(), cy = b.getCentreY();
        const float ang = a0 + pos * (a1 - a0);
        juce::Path track, val;
        track.addCentredArc (cx, cy, r, r, 0.0f, a0, a1, true);
        val.addCentredArc (cx, cy, r, r, 0.0f, a0, ang, true);
        g.setColour (juce::Colour (0xff2c323b));
        g.strokePath (track, juce::PathStrokeType (4.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
        g.setColour (s.findColour (juce::Slider::rotarySliderFillColourId));
        g.strokePath (val, juce::PathStrokeType (4.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
        g.setColour (col::txt);
        const float rr = r - 5.0f;
        g.drawLine (cx, cy, cx + rr * std::sin (ang), cy - rr * std::cos (ang), 2.0f);
    }
};

// Bouton à bascule en forme de pastille (Delta, Spectre, Bande active) ; le texte peut changer selon l'état.
class PillButton : public juce::ToggleButton
{
public:
    PillButton (const juce::String& textOff_, const juce::String& textOn_) : textOff (textOff_), textOn (textOn_) { setClickingTogglesState (true); }

    void paintButton (juce::Graphics& g, bool hover, bool) override
    {
        const auto r = getLocalBounds().toFloat().reduced (0.5f);
        const bool on = getToggleState();
        g.setColour (on ? juce::Colour (0xff2b3340) : (hover ? col::panel2 : col::panel));
        g.fillRoundedRectangle (r, 8.0f);
        g.setColour (on ? juce::Colour (0xff4a5568) : col::line);
        g.drawRoundedRectangle (r, 8.0f, 1.0f);
        g.setColour (col::txt);
        g.setFont (13.0f);
        g.drawText (on ? textOn : textOff, getLocalBounds(), juce::Justification::centred);
    }

private:
    juce::String textOff, textOn;
};

// Bouton rotatif lié à un paramètre : arc, valeur en dessous, nom sous la valeur.
class Knob : public juce::Component
{
public:
    Knob (juce::AudioProcessorValueTreeState& apvts, const juce::String& paramId, const juce::String& label_, juce::Colour c,
          std::function<juce::String (double)> fmt_)
        : label (label_), fmt (std::move (fmt_))
    {
        slider.setSliderStyle (juce::Slider::RotaryVerticalDrag);
        slider.setTextBoxStyle (juce::Slider::NoTextBox, true, 0, 0);
        slider.setRotaryParameters (juce::degreesToRadians (135.0f), juce::degreesToRadians (405.0f), true);
        slider.setColour (juce::Slider::rotarySliderFillColourId, c);
        slider.setLookAndFeel (&lnf);
        slider.setVelocityBasedMode (false);
        slider.setMouseDragSensitivity (150);
        slider.onValueChange = [this] { repaint(); };
        addAndMakeVisible (slider);
        attachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (apvts, paramId, slider);
    }
    ~Knob() override { slider.setLookAndFeel (nullptr); }

    void resized() override { slider.setBounds (getLocalBounds().withHeight (56).withSizeKeepingCentre (56, 56).withY (0)); }

    void paint (juce::Graphics& g) override
    {
        g.setColour (col::txt);
        g.setFont (13.0f);
        g.drawText (fmt (slider.getValue()), 0, 58, getWidth(), 16, juce::Justification::centred);
        g.setColour (col::mut);
        g.setFont (11.0f);
        g.drawText (label, 0, 74, getWidth(), 14, juce::Justification::centred);
    }

    static int preferredWidth() { return 84; }
    static int preferredHeight() { return 92; }

private:
    KnobLnF lnf;
    juce::Slider slider;
    juce::String label;
    std::function<juce::String (double)> fmt;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> attachment;
};

// Sélecteur segmenté pour un paramètre à choix (Cloche | Shelf grave | Shelf aigu, canaux, modes…).
class Seg : public juce::Component
{
public:
    Seg (juce::AudioProcessorValueTreeState& apvts, const juce::String& paramId, const juce::StringArray& names_, juce::Colour c)
        : names (names_), colour (c), param (apvts.getParameter (paramId))
    {
        attachment = std::make_unique<juce::ParameterAttachment> (*param, [this] (float v) { index = juce::roundToInt (v); repaint(); });
        attachment->sendInitialUpdate();
    }

    int preferredWidth (float fontH = 13.0f) const
    {
        int w = 0;
        juce::Font f { juce::FontOptions (fontH) };
        for (auto& n : names) w += prismeUi::textWidth (f, n) + 24;
        return w;
    }

    void paint (juce::Graphics& g) override
    {
        const auto b = getLocalBounds().toFloat().reduced (0.5f);
        g.setColour (col::line);
        g.drawRoundedRectangle (b, 8.0f, 1.0f);
        juce::Font f { juce::FontOptions (13.0f) };
        int total = 0;
        for (auto& n : names) total += prismeUi::textWidth (f, n) + 24;
        const float scale = (float) getWidth() / (float) juce::jmax (1, total);
        float x = 0.0f;
        for (int i = 0; i < names.size(); ++i)
        {
            const float w = (float) (prismeUi::textWidth (f, names[i]) + 24) * scale;
            const auto r = juce::Rectangle<float> (x, b.getY(), w, b.getHeight());
            if (i == index)
            {
                g.setColour (colour);
                juce::Path p;
                p.addRoundedRectangle (r.getX(), r.getY(), r.getWidth(), r.getHeight(), 8.0f, 8.0f, i == 0, i == names.size() - 1, i == 0, i == names.size() - 1);
                g.fillPath (p);
                g.setColour (juce::Colour (0xff0b0d10));
                g.setFont (juce::Font (juce::FontOptions (13.0f, juce::Font::bold)));
            }
            else
            {
                g.setColour (col::panel2);
                juce::Path p;
                p.addRoundedRectangle (r.getX(), r.getY(), r.getWidth(), r.getHeight(), 8.0f, 8.0f, i == 0, i == names.size() - 1, i == 0, i == names.size() - 1);
                g.fillPath (p);
                g.setColour (col::mut);
                g.setFont (13.0f);
            }
            g.drawText (names[i], r, juce::Justification::centred);
            if (i > 0) { g.setColour (col::line); g.drawVerticalLine ((int) x, b.getY(), b.getBottom()); }
            x += w;
        }
    }

    void mouseDown (const juce::MouseEvent& e) override
    {
        juce::Font f { juce::FontOptions (13.0f) };
        int total = 0;
        for (auto& n : names) total += prismeUi::textWidth (f, n) + 24;
        const float scale = (float) getWidth() / (float) juce::jmax (1, total);
        float x = 0.0f;
        for (int i = 0; i < names.size(); ++i)
        {
            x += (float) (prismeUi::textWidth (f, names[i]) + 24) * scale;
            if ((float) e.x < x) { attachment->setValueAsCompleteGesture ((float) i); return; }
        }
    }

private:
    juce::StringArray names;
    juce::Colour colour;
    juce::RangedAudioParameter* param;
    int index = 0;
    std::unique_ptr<juce::ParameterAttachment> attachment;
};

// Les 4 types de traitement (grille 2 × 2), liés au paramètre `type` de la bande.
class TypeButtons : public juce::Component
{
public:
    TypeButtons (juce::AudioProcessorValueTreeState& apvts, const juce::String& paramId, std::function<void()> onChange_)
        : param (apvts.getParameter (paramId)), onChange (std::move (onChange_))
    {
        index = juce::roundToInt (param->convertFrom0to1 (param->getValue()));          // état initial : ne pas déclencher de reconstruction au démarrage
        attachment = std::make_unique<juce::ParameterAttachment> (*param, [this] (float v)
        {
            const int nv = juce::roundToInt (v);
            const bool changed = nv != index;
            index = nv;
            repaint();
            if (changed && onChange) juce::MessageManager::callAsync ([fn = onChange] { fn(); });          // copie : la fonction survit à la destruction du bouton
        });
        attachment->sendInitialUpdate();
    }

    void paint (juce::Graphics& g) override
    {
        juce::String desc[4] = { "Harmoniques", U8 ("Résonances"), "Attaque / sustain", U8 ("Détail selon le niveau") };
        for (int i = 0; i < 4; ++i)
        {
            const auto r = cell (i).toFloat();
            const auto c = col::forType (i);
            g.setColour (i == index ? juce::Colour (0xff232830) : col::panel2);
            g.fillRoundedRectangle (r, 8.0f);
            g.setColour (i == index ? c : col::line);
            g.drawRoundedRectangle (r.reduced (0.5f), 8.0f, 1.0f);
            g.setColour (c);
            g.fillEllipse (r.getX() + 10.0f, r.getY() + 12.0f, 9.0f, 9.0f);
            g.setColour (col::txt);
            g.setFont (14.0f);
            g.drawText (prismeParams::typeNames()[i], (int) r.getX() + 26, (int) r.getY() + 7, (int) r.getWidth() - 30, 18, juce::Justification::centredLeft);
            g.setColour (col::mut);
            g.setFont (11.0f);
            g.drawFittedText (desc[i], (int) r.getX() + 10, (int) r.getY() + 28, (int) r.getWidth() - 14, 28, juce::Justification::topLeft, 2);
        }
    }

    void mouseDown (const juce::MouseEvent& e) override
    {
        for (int i = 0; i < 4; ++i)
            if (cell (i).contains (e.getPosition())) { attachment->setValueAsCompleteGesture ((float) i); return; }
    }

private:
    juce::Rectangle<int> cell (int i) const
    {
        const int gap = 6, w = (getWidth() - gap) / 2, h = (getHeight() - gap) / 2;
        return { (i % 2) * (w + gap), (i / 2) * (h + gap), w, h };
    }

    juce::RangedAudioParameter* param;
    std::function<void()> onChange;
    int index = 0;
    std::unique_ptr<juce::ParameterAttachment> attachment;
};
}
