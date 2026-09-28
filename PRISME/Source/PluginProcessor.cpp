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
    for (auto& w : wetTmp) w.assign ((size_t) cap, 0.0f);
    for (auto& w : wet) w.f.reset();
    filtres.prepare (sampleRate, true);
    bypassMix.reset (sampleRate, 0.01);
    bypassMix.setCurrentAndTargetValue (prismeParams::raw (apvts, "bypass") > 0.5f ? 0.0f : 1.0f);
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
        auto spec = prismeParams::readSpec (apvts, b);
        if (spec.type == prisme::TypeBande::Exciter && spec.gainDb < 0.0)      // V1 : pas d'Exciter négatif (décision de llg53) → le gain revient à 0
        {
            if (auto* gp = apvts.getParameter (prismeParams::pid (b, "gain"))) gp->setValueNotifyingHost (gp->convertTo0to1 (0.0f));
            spec.gainDb = 0.0;
        }
        auto structure = spec;
        structure.gainDb = 0.0;
        structure.drive = 0.0;
        structure.tilt = 0.0;
        structure.link = 0.0;
        structure.dens = 0.0;                                                 // gain et saturation se règlent en direct : pas de reconstruction

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
            s.driveTarget.store (spec.drive);
            s.lastDrive = spec.drive;
            s.tiltTarget.store (spec.tilt);
            s.lastTilt = spec.tilt;
            s.linkTarget.store (spec.link);
            s.lastLink = spec.link;
            s.densTarget.store (spec.dens);
            s.lastDens = spec.dens;
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
        s.driveTarget.store (spec.drive);
        s.tiltTarget.store (spec.tilt);
        s.linkTarget.store (spec.link);
        s.densTarget.store (spec.dens);
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
    bool solo[prismeParams::nBands];
    bool anySolo = false;
    for (int b = 0; b < prismeParams::nBands; ++b) { solo[b] = prismeParams::raw (apvts, prismeParams::pid (b, "solo")) > 0.5f; anySolo |= solo[b]; }
    bypassMix.setTargetValue (prismeParams::raw (apvts, "bypass") > 0.5f ? 0.0f : 1.0f);
    const bool wetOn = analyserOn.load();
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
                        s.warm->setDrive (s.driveTarget.load());
                        s.lastDrive = s.driveTarget.load();
                        s.warm->setTilt (s.tiltTarget.load());
                        s.lastTilt = s.tiltTarget.load();
                        s.warm->setLink (s.linkTarget.load());
                        s.lastLink = s.linkTarget.load();
                        s.warm->setDens (s.densTarget.load());
                        s.lastDens = s.densTarget.load();
                        s.old = std::move (s.cur);
                        s.cur = std::move (s.warm);
                        s.fadePos = 0;
                        s.lastGain = s.gainTarget.load();
                    }
                }
            }
            const float g = s.gainTarget.load();                              // gain en direct
            if (s.cur && g != s.lastGain) { s.cur->setGain (g); s.lastGain = g; }
            const double dv = s.driveTarget.load();
            if (s.cur && dv != s.lastDrive) { s.cur->setDrive (dv); s.lastDrive = dv; }
            const double tv = s.tiltTarget.load();
            if (s.cur && tv != s.lastTilt) { s.cur->setTilt (tv); s.lastTilt = tv; }
            const double lk = s.linkTarget.load();
            if (s.cur && lk != s.lastLink) { s.cur->setLink (lk); s.lastLink = lk; }
            const double dn = s.densTarget.load();
            if (s.cur && dn != s.lastDens) { s.cur->setDens (dn); s.lastDens = dn; }
        }

        // ---- filtres de bande : réglages du bloc (bande active = présente et non coupée) ----
        for (int b = 0; b < prismeParams::nBands; ++b)
        {
            const auto sp = prismeParams::readSpec (apvts, b);
            const bool actif = slots[(size_t) b].cur != nullptr && sp.on;
            filtres.regle (b, false, { sp.lcOn, sp.lcF, sp.lcPente }, actif);
            filtres.regle (b, true, { sp.hcOn, sp.hcF, sp.hcPente }, actif);
        }
        filtres.miseAJourBloc (n);

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
            double apL = dryL, apR = dryR;
            filtres.sec (apL, apR);                            // sec passé par les passe-tout des filtres actifs
            double sumL = 0.0, sumR = 0.0, soloL = 0.0, soloR = 0.0;
            for (size_t si = 0; si < slots.size(); ++si)
            {
                auto& s = slots[si];
                if (! s.cur && ! s.old) { if (wetOn) wetTmp[si][(size_t) i] = 0.0f; continue; }
                double cL = 0, cR = 0, oL = 0, oR = 0, dL, dR;
                if (s.cur) s.cur->process (L, R, cL, cR);
                if (s.fadePos < fadeLen)
                {
                    if (s.old) s.old->process (L, R, oL, oR);
                    const double a = (double) s.fadePos / (double) fadeLen;
                    dL = oL * (1.0 - a) + cL * a;
                    dR = oR * (1.0 - a) + cR * a;
                    ++s.fadePos;
                }
                else { dL = cL; dR = cR; }
                filtres.delta ((int) si, dL, dR);
                sumL += dL; sumR += dR;
                if (solo[si]) { soloL += dL; soloR += dR; }
                if (wetOn) wetTmp[si][(size_t) i] = (float) (0.5 * ((s.cur && s.cur->getSpec().canal == prisme::Canal::Side) ? dL - dR : dL + dR));   // Side : d à gauche, −d à droite
            }
            filtres.avance();
            const double g = (double) outGain.getNextValue();
            const double bm = (double) bypassMix.getNextValue();
            const double wL = anySolo ? soloL : (delta ? sumL : apL + sumL), wR = anySolo ? soloR : (delta ? sumR : apR + sumR);
            bufL[(size_t) i] = (bm * wL + (1.0 - bm) * dryL) * g;
            bufR[(size_t) i] = (bm * wR + (1.0 - bm) * dryR) * g;
        }

        if (wetOn)
            for (size_t b = 0; b < slots.size(); ++b)
            {
                const int w = juce::jmin (n, wet[b].f.getFreeSpace());
                if (w <= 0) continue;
                int s1, n1, s2, n2;
                wet[b].f.prepareToWrite (w, s1, n1, s2, n2);
                for (int i = 0; i < n1; ++i) wet[b].buf[(size_t) (s1 + i)] = wetTmp[b][(size_t) i];
                for (int i = 0; i < n2; ++i) wet[b].buf[(size_t) (s2 + i)] = wetTmp[b][(size_t) (n1 + i)];
                wet[b].f.finishedWrite (w);
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

int PrismeProcessor::readWet (int band, float* dest, int maxCount)
{
    auto& w = wet[(size_t) band];
    const int r = juce::jmin (maxCount, w.f.getNumReady());
    if (r <= 0) return 0;
    int s1, n1, s2, n2;
    w.f.prepareToRead (r, s1, n1, s2, n2);
    for (int i = 0; i < n1; ++i) dest[i] = w.buf[(size_t) (s1 + i)];
    for (int i = 0; i < n2; ++i) dest[n1 + i] = w.buf[(size_t) (s2 + i)];
    w.f.finishedRead (r);
    return r;
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
