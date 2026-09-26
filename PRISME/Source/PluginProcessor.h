#pragma once

#include <JuceHeader.h>
#include "Params.h"

/**
    PRISME — EQ dont chaque bande est un TYPE de traitement (Exciter, Tame, Shape, Lift), posée n'importe où sur le spectre.

    Architecture additive : sortie = entrée retardée + Σ deltas des bandes. Latence FIXE de 20 échantillons (déclarée à l'hôte).

    CHANGEMENT DE RÉGLAGE EN COURS DE LECTURE
      · GAIN : appliqué en direct à la bande vivante (aucune reconstruction, aucun état perdu) ;
      · autre réglage (fréquence, Q, forme, type, mode, canal…) : un thread de construction bâtit une NOUVELLE bande puis la « chauffe » en lui rejouant
        les 2,5 dernières secondes d entrée (sinon ses détecteurs et normalisations repartent de zéro et le delta explose pendant 100 ms à 1 s : constaté
        sur l'Exciter, +11 à +15 dB) ; le thread audio la rattrape sur les derniers échantillons (répartis sur plusieurs blocs), puis fond l'ancienne vers
        la nouvelle en 1024 échantillons.
      · aucune allocation ni destruction sur le thread audio (les bandes remplacées sont rendues au thread message).
      · une bande à gain 0 reste vivante 3 s (pour qu'un passage par zéro pendant un glissement ne la détruise pas), puis est libérée.
*/
class PrismeProcessor : public juce::AudioProcessor,
                        private juce::Timer
{
public:
    PrismeProcessor();
    ~PrismeProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "PRISME"; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock&) override;
    void setStateInformation (const void*, int) override;

    juce::AudioProcessorValueTreeState apvts;

    // Analyseur de spectre : le thread audio écrit la sortie (mono), l'éditeur lit.
    int readAnalyser (float* dest, int maxCount);
    double getSampleRateHz() const { return fsHz.load(); }
    // Spectres des deltas de chaque bande (signal « wet » de la couleur du traitement) : lecture par l'éditeur ; `setAnalyserActive` évite le travail éditeur fermé.
    int readWet (int band, float* dest, int maxCount);
    void setAnalyserActive (bool b) { analyserOn.store (b); }
    juce::AudioProcessorParameter* getBypassParameter() const override { return apvts.getParameter ("bypass"); }

private:
    struct Slot
    {
        juce::SpinLock lock;
        // déposé par le thread de construction / message, repris par le thread audio
        std::unique_ptr<prisme::BandeProc> pending;
        bool hasPending = false, pendingIsOff = false;
        std::int64_t pendingConsumed = 0;
        std::unique_ptr<prisme::BandeProc> trash;          // rendue au thread message pour destruction
        // thread audio
        std::unique_ptr<prisme::BandeProc> cur, old, warm;
        std::int64_t warmConsumed = 0;
        int fadePos = 0;
        float lastGain = 0.0f;
        std::atomic<float> gainTarget { 0.0f };
        std::atomic<double> driveTarget { 1.5 };
        double lastDrive = 1.5;
        std::atomic<double> tiltTarget { 0.0 };
        double lastTilt = 0.0;
        std::atomic<double> linkTarget { 0.5 };
        double lastLink = 0.5;
        std::atomic<bool> needRebuild { false };
        // thread message
        prisme::BandeSpec msgStruct;
        bool msgAlive = false;
        juce::uint32 zeroSince = 0;
    };

    struct Builder;                                        // thread de construction + préchauffage
    friend struct Builder;

    void timerCallback() override;
    void syncBands (bool immediate);
    void deactivate (Slot& s);
    bool readRing (std::int64_t from, int count, double* L, double* R) const;

    static constexpr int fadeLen = 1024;
    static constexpr double histSeconds = 2.5;                  // l'Exciter v2 a un niveau lent de 400 ms : 2,5 s = 6 constantes de temps

    std::array<Slot, prismeParams::nBands> slots;
    std::atomic<double> fsHz { 0.0 };
    prisme::Retard<prisme::Engine::latence> secL, secR;
    juce::SmoothedValue<float> outGain;
    juce::AbstractFifo fifo { 8192 };
    std::vector<float> fifoBuf = std::vector<float> (8192, 0.0f);
    std::vector<double> bufL, bufR;
    struct WetFifo { juce::AbstractFifo f { 8192 }; std::vector<float> buf = std::vector<float> (8192, 0.0f); };
    std::array<WetFifo, prismeParams::nBands> wet;
    std::array<std::vector<float>, prismeParams::nBands> wetTmp;
    std::atomic<bool> analyserOn { false };
    juce::SmoothedValue<float> bypassMix;

    // Historique de l'entrée (anneau) : préchauffage des nouvelles bandes.
    std::vector<double> ringL, ringR;
    std::int64_t ringCap = 0;
    std::atomic<std::int64_t> counter { 0 };               // nombre d'échantillons écrits

    std::unique_ptr<Builder> builder;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (PrismeProcessor)
};
