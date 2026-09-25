#include "PluginProcessor.h"
#include "PluginEditor.h"

// ------------------------------------------------------------------ thread de construction
// Bâtit une bande, la préchauffe avec l'historique d'entrée, la dépose dans son emplacement. Une seule demande en attente par bande (la plus récente).
struct PrismeProcessor::Builder : public juce::Thread
{
    struct Request { bool valid = false; prisme::BandeSpec spec; int gen = 0; };

    explicit Builder (PrismeProcessor& p) : juce::Thread ("PRISME builder"), owner (p) {}

    void request (int band, const prisme::BandeSpec& s)
    {
        {
            const juce::ScopedLock l (cs);
            req[(size_t) band] = { true, s, ++gen[(size_t) band] };
        }
        wake.signal();
    }

    void cancel (int band)
    {
        const juce::ScopedLock l (cs);
        req[(size_t) band].valid = false;
        ++gen[(size_t) band];                                                   // tout travail en cours pour cette bande devient périmé
    }

    void run() override
    {
        while (! threadShouldExit())
        {
            wake.wait (200);
            for (int b = 0; b < prismeParams::nBands && ! threadShouldExit(); ++b)
            {
                Request r;
                {
                    const juce::ScopedLock l (cs);
                    r = req[(size_t) b];
                    req[(size_t) b].valid = false;
                }
                if (r.valid) build (b, r.spec, r.gen);
            }
        }
    }

    void build (int band, const prisme::BandeSpec& spec, int myGen)
    {
        const double fs = owner.fsHz.load();
        if (fs <= 0.0) return;
        auto nb = std::make_unique<prisme::BandeProc>();
        nb->prepare (fs, spec);

        // préchauffage : on rejoue l'historique, puis on rattrape ce qui est arrivé pendant ce temps (par tours, jusqu'à un petit reste)
        std::int64_t consumed = 0;
        std::vector<double> L, R;
        const int hist = (int) (histSeconds * fs);
        bool first = true;
        for (int round = 0; round < 8 && ! threadShouldExit(); ++round)
        {
            const std::int64_t now = owner.counter.load (std::memory_order_acquire);
            std::int64_t from = first ? juce::jmax<std::int64_t> (0, now - hist) : consumed;
            const std::int64_t n = now - from;
            if (n <= 0) break;
            if (n > owner.ringCap - 4096) { first = true; continue; }                // en retard sur l'anneau : on repart de l'historique
            L.resize ((size_t) n);
            R.resize ((size_t) n);
            if (! owner.readRing (from, (int) n, L.data(), R.data())) continue;
            double dl, dr;
            for (std::int64_t i = 0; i < n; ++i) nb->process (L[(size_t) i], R[(size_t) i], dl, dr);
            consumed = now;
            first = false;
            if (owner.counter.load() - consumed < 2048) break;
        }
        auto& s = owner.slots[(size_t) band];
        const juce::SpinLock::ScopedLockType l (s.lock);
        {
            const juce::ScopedLock lg (cs);                                           // demande plus récente ou bande libérée entre-temps : travail périmé
            if (gen[(size_t) band] != myGen) return;
        }
        s.pending = std::move (nb);
        s.pendingConsumed = consumed;
        s.pendingIsOff = false;
        s.hasPending = true;
    }

    PrismeProcessor& owner;
    juce::CriticalSection cs;
    std::array<Request, prismeParams::nBands> req;
    std::array<int, prismeParams::nBands> gen {};
    juce::WaitableEvent wake;
};

// ------------------------------------------------------------------ processeur
PrismeProcessor::PrismeProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput  ("Input",  juce::AudioChannelSet::stereo(), true)
                          .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "PRISME", prismeParams::createLayout())
{
    setLatencySamples (prisme::Engine::latence);
    builder = std::make_unique<Builder> (*this);
    builder->startThread (juce::Thread::Priority::normal);
    startTimerHz (30);
}

PrismeProcessor::~PrismeProcessor()
{
    stopTimer();
    builder->stopThread (2000);
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
    for (auto& s : slots) { builder->cancel (int (&s - slots.data())); }
    fsHz.store (sampleRate);
    const int cap = juce::jmax (samplesPerBlock, 4096);
    bufL.assign ((size_t) cap, 0.0);
    bufR.assign ((size_t) cap, 0.0);
    ringCap = (std::int64_t) ((histSeconds + 2.5) * sampleRate);
    ringL.assign ((size_t) ringCap, 0.0);
    ringR.assign ((size_t) ringCap, 0.0);
    counter.store (0);
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

bool PrismeProcessor::readRing (std::int64_t from, int count, double* L, double* R) const
{
    const std::int64_t c1 = counter.load (std::memory_order_acquire);
    if (from < 0 || from + count > c1 || ringCap <= 0) return false;
    for (int i = 0; i < count; ++i)
    {
        const size_t k = (size_t) ((from + i) % ringCap);
        L[i] = ringL[k];
        R[i] = ringR[k];
    }
    const std::int64_t c2 = counter.load (std::memory_order_acquire);       // l'anneau a-t-il été réécrit sous nos pieds ?
    return (c2 - from) <= ringCap - 1024;
}

void PrismeProcessor::deactivate (Slot& s)
{
    builder->cancel (int (&s - slots.data()));
    {
        const juce::SpinLock::ScopedLockType l (s.lock);
        s.pending.reset();
        s.pendingIsOff = true;
        s.hasPending = true;
    }
    s.msgAlive = false;
    s.zeroSince = 0;
}

// Thread message : décide, bande par bande, de ne rien faire, de changer le gain en direct, de construire une nouvelle bande ou de libérer.
void PrismeProcessor::syncBands (bool immediate)
{
    const double fs = fsHz.load();
    for (int b = 0; b < prismeParams::nBands; ++b)
    {
        auto& s = slots[(size_t) b];
        const auto spec = prismeParams::readSpec (apvts, b);
        auto structure = spec;
        structure.gainDb = 0.0;

        if (immediate)
        {
            const juce::SpinLock::ScopedLockType l (s.lock);
            s.cur.reset(); s.old.reset(); s.warm.reset(); s.pending.reset(); s.trash.reset();
            s.hasPending = false;
            s.fadePos = fadeLen;
            if (spec.actif())
            {
                s.cur = std::make_unique<prisme::BandeProc>();
                s.cur->prepare (fs, spec);
            }
            s.lastGain = (float) spec.gainDb;
            s.gainTarget.store ((float) spec.gainDb);
            s.msgStruct = structure;
            s.msgAlive = spec.actif();
            s.zeroSince = 0;
            s.needRebuild.store (false);
            continue;
        }

        {
            const juce::SpinLock::ScopedLockType l (s.lock);                  // libère ce que le thread audio a rendu
            s.trash.reset();
        }

        if (! spec.on) { if (s.msgAlive) deactivate (s); continue; }

        if (spec.gainDb == 0.0)
        {
            if (! s.msgAlive) continue;
            const auto now = juce::Time::getMillisecondCounter();
            if (s.zeroSince == 0) s.zeroSince = now;
            if (now - s.zeroSince > 3000) { deactivate (s); continue; }
        }
        else
            s.zeroSince = 0;

        s.gainTarget.store ((float) spec.gainDb);
        if (! s.msgAlive || structure != s.msgStruct || s.needRebuild.exchange (false))
        {
            builder->request (b, spec);
            s.msgStruct = structure;
            s.msgAlive = true;
        }
    }
}

void PrismeProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    const int nCh = buffer.getNumChannels();
    const int total = buffer.getNumSamples();
    if (nCh < 1 || fsHz.load() <= 0.0 || bufL.empty()) return;

    float* chL = buffer.getWritePointer (0);
    float* chR = nCh > 1 ? buffer.getWritePointer (1) : nullptr;
    const int cap = (int) bufL.size();
    const bool delta = prismeParams::raw (apvts, "delta") > 0.5f;
    outGain.setTargetValue (juce::Decibels::decibelsToGain (prismeParams::raw (apvts, "output")));

    for (int start = 0; start < total; start += cap)
    {
        const int n = juce::jmin (cap, total - start);
        const std::int64_t c0 = counter.load (std::memory_order_relaxed);

        // ---- gestion des bandes (au début du bloc, l'état DSP de chaque bande est « à c0 ») ----
        for (size_t si = 0; si < slots.size(); ++si)
        {
            auto& s = slots[si];
            {
                const juce::SpinLock::ScopedTryLockType l (s.lock);
                if (l.isLocked())
                {
                    if (s.old && s.fadePos >= fadeLen && ! s.trash) s.trash = std::move (s.old);
                    if (s.hasPending)
                    {
                        if (s.pendingIsOff)
                        {
                            if (! s.old && ! s.trash) { s.old = std::move (s.cur); s.trash = std::move (s.warm); s.fadePos = 0; s.hasPending = false; s.pendingIsOff = false; }
                        }
                        else if (! s.warm || ! s.trash)
                        {
                            if (s.warm) s.trash = std::move (s.warm);
                            s.warm = std::move (s.pending);
                            s.warmConsumed = s.pendingConsumed;
                            s.hasPending = false;
                        }
                    }
                }
            }
            if (s.warm)                                                       // rattrapage : au plus 2 blocs d'entrée rejoués par bloc
            {
                const std::int64_t missing = c0 - s.warmConsumed;
                if (missing < 0 || missing > ringCap - 2048)
                {
                    if (! s.trash) { s.trash = std::move (s.warm); s.needRebuild.store (true); }
                }
                else
                {
                    const int feed = (int) juce::jmin<std::int64_t> (missing, 2 * (std::int64_t) n);
                    double dl, dr;
                    for (int i = 0; i < feed; ++i)
                    {
                        const size_t k = (size_t) ((s.warmConsumed + i) % ringCap);
                        s.warm->process (ringL[k], ringR[k], dl, dr);
                    }
                    s.warmConsumed += feed;
                    if (s.warmConsumed == c0 && ! s.old)
                    {
                        s.warm->setGain (s.gainTarget.load());
                        s.old = std::move (s.cur);
                        s.cur = std::move (s.warm);
                        s.fadePos = 0;
                        s.lastGain = s.gainTarget.load();
                    }
                }
            }
            const float g = s.gainTarget.load();                              // gain en direct
            if (s.cur && g != s.lastGain) { s.cur->setGain (g); s.lastGain = g; }
        }

        // ---- entrée : anneau d'historique + conversion en double ----
        for (int i = 0; i < n; ++i)
        {
            const double L = chL[start + i], R = chR ? chR[start + i] : chL[start + i];
            bufL[(size_t) i] = L;
            bufR[(size_t) i] = R;
            const size_t k = (size_t) ((c0 + i) % ringCap);
            ringL[k] = L;
            ringR[k] = R;
        }
        counter.store (c0 + n, std::memory_order_release);

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
