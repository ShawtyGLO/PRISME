#include "PluginProcessor.h"
#include "PluginEditor.h"

PrismeProcessor::PrismeProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput  ("Input",  juce::AudioChannelSet::stereo(), true)
                          .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "PRISME", prismeParams::createLayout())
{
    setLatencySamples (prisme::Engine::latence);
    startTimerHz (30);
}

PrismeProcessor::~PrismeProcessor()
{
    stopTimer();
}

bool PrismeProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    const auto& out = layouts.getMainOutputChannelSet();
    if (out != juce::AudioChannelSet::mono() && out != juce::AudioChannelSet::stereo())
        return false;
    return layouts.getMainInputChannelSet() == out;
}

void PrismeProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    fsHz.store (sampleRate);
    const int cap = juce::jmax (samplesPerBlock, 4096);
    bufL.assign ((size_t) cap, 0.0);
    bufR.assign ((size_t) cap, 0.0);
    secL.init (0.0);
    secR.init (0.0);
    outGain.reset (sampleRate, 0.02);
    outGain.setCurrentAndTargetValue (juce::Decibels::decibelsToGain (prismeParams::raw (apvts, "output")));
    fifo.reset();
    setLatencySamples (prisme::Engine::latence);
    syncBands (true);
}

void PrismeProcessor::timerCallback()
{
    if (fsHz.load() > 0.0)
        syncBands (false);
}

// Thread message : construit les bandes dont un réglage a changé et les dépose dans leur emplacement.
void PrismeProcessor::syncBands (bool immediate)
{
    const double fs = fsHz.load();
    for (int b = 0; b < prismeParams::nBands; ++b)
    {
        auto& s = slots[(size_t) b];
        const auto spec = prismeParams::readSpec (apvts, b);
        const bool active = spec.actif();

        if (immediate)
        {
            s.cur.reset(); s.old.reset(); s.pending.reset(); s.trash.reset();
            s.hasPending = false;
            if (active) { s.cur = std::make_unique<prisme::BandeProc>(); s.cur->prepare (fs, spec); }
            s.fadePos = fadeLen;
            s.msgSpec = spec;
            s.msgActive = active;
            continue;
        }

        {
            const juce::SpinLock::ScopedLockType l (s.lock);                  // libère ce que le thread audio a rendu
            s.trash.reset();
        }
        if (! active && ! s.msgActive) { s.msgSpec = spec; continue; }
        if (active && s.msgActive && spec == s.msgSpec) continue;

        std::unique_ptr<prisme::BandeProc> nb;
        if (active) { nb = std::make_unique<prisme::BandeProc>(); nb->prepare (fs, spec); }
        {
            const juce::SpinLock::ScopedLockType l (s.lock);
            s.pending = std::move (nb);
            s.hasPending = true;
        }
        s.msgSpec = spec;
        s.msgActive = active;
    }
}

void PrismeProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    const int nCh = buffer.getNumChannels();
    const int total = buffer.getNumSamples();
    if (nCh < 1 || fsHz.load() <= 0.0 || bufL.empty()) return;

    // prise en compte des nouvelles bandes (sans bloquer : si le verrou est pris, ce sera pour le bloc suivant)
    for (auto& s : slots)
    {
        const juce::SpinLock::ScopedTryLockType l (s.lock);
        if (! l.isLocked()) continue;
        if (s.old && s.fadePos >= fadeLen && ! s.trash) s.trash = std::move (s.old);
        if (s.hasPending && ! s.old)
        {
            s.old = std::move (s.cur);
            s.cur = std::move (s.pending);
            s.hasPending = false;
            s.fadePos = 0;
        }
    }

    const bool delta = prismeParams::raw (apvts, "delta") > 0.5f;
    outGain.setTargetValue (juce::Decibels::decibelsToGain (prismeParams::raw (apvts, "output")));

    float* chL = buffer.getWritePointer (0);
    float* chR = nCh > 1 ? buffer.getWritePointer (1) : nullptr;
    const int cap = (int) bufL.size();

    for (int start = 0; start < total; start += cap)
    {
        const int n = juce::jmin (cap, total - start);
        for (int i = 0; i < n; ++i)
        {
            bufL[(size_t) i] = chL[start + i];
            bufR[(size_t) i] = chR ? chR[start + i] : chL[start + i];
        }

        for (int i = 0; i < n; ++i)
        {
            const double L = bufL[(size_t) i], R = bufR[(size_t) i];
            const double dryL = secL.push (L), dryR = secR.push (R);
            double sumL = 0.0, sumR = 0.0;
            for (auto& s : slots)
            {
                if (! s.cur && ! s.old) continue;
                double cL = 0, cR = 0, oL = 0, oR = 0;
                if (s.cur) s.cur->process (L, R, cL, cR);
                if (s.fadePos < fadeLen)
                {
                    if (s.old) s.old->process (L, R, oL, oR);
                    const double a = (double) s.fadePos / (double) fadeLen;
                    sumL += oL * (1.0 - a) + cL * a;
                    sumR += oR * (1.0 - a) + cR * a;
                    ++s.fadePos;
                }
                else
                {
                    sumL += cL;
                    sumR += cR;
                }
            }
            const double g = (double) outGain.getNextValue();
            bufL[(size_t) i] = (delta ? sumL : dryL + sumL) * g;
            bufR[(size_t) i] = (delta ? sumR : dryR + sumR) * g;
        }

        for (int i = 0; i < n; ++i)
        {
            chL[start + i] = (float) bufL[(size_t) i];
            if (chR) chR[start + i] = (float) bufR[(size_t) i];
        }

        // spectre : moyenne des deux canaux vers l'éditeur
        const int w = juce::jmin (n, fifo.getFreeSpace());
        if (w > 0)
        {
            int s1, n1, s2, n2;
            fifo.prepareToWrite (w, s1, n1, s2, n2);
            for (int i = 0; i < n1; ++i) fifoBuf[(size_t) (s1 + i)] = (float) (0.5 * (bufL[(size_t) i] + bufR[(size_t) i]));
            for (int i = 0; i < n2; ++i) fifoBuf[(size_t) (s2 + i)] = (float) (0.5 * (bufL[(size_t) (n1 + i)] + bufR[(size_t) (n1 + i)]));
            fifo.finishedWrite (w);
        }
    }
}

int PrismeProcessor::readAnalyser (float* dest, int maxCount)
{
    const int r = juce::jmin (maxCount, fifo.getNumReady());
    if (r <= 0) return 0;
    int s1, n1, s2, n2;
    fifo.prepareToRead (r, s1, n1, s2, n2);
    for (int i = 0; i < n1; ++i) dest[i] = fifoBuf[(size_t) (s1 + i)];
    for (int i = 0; i < n2; ++i) dest[n1 + i] = fifoBuf[(size_t) (s2 + i)];
    fifo.finishedRead (r);
    return r;
}

juce::AudioProcessorEditor* PrismeProcessor::createEditor()
{
    return new PrismeEditor (*this);
}

void PrismeProcessor::getStateInformation (juce::MemoryBlock& dest)
{
    if (auto xml = apvts.copyState().createXml())
        copyXmlToBinary (*xml, dest);
}

void PrismeProcessor::setStateInformation (const void* data, int size)
{
    if (auto xml = getXmlFromBinary (data, size))
        if (xml->hasTagName (apvts.state.getType()))
            apvts.replaceState (juce::ValueTree::fromXml (*xml));
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new PrismeProcessor();
}
