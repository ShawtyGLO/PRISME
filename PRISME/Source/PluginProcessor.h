#pragma once

#include <JuceHeader.h>
#include "Params.h"

/**
    PRISME — EQ dont chaque bande est un TYPE de traitement (Exciter, Tame, Shape, Lift), posée n'importe où sur le spectre.

    Architecture additive : sortie = entrée retardée + Σ deltas des bandes. Latence FIXE de 20 échantillons (déclarée à l'hôte).

    Changement de réglage en cours de lecture : le thread message (Timer 30 Hz) construit une NOUVELLE bande (les états DSP repartent de zéro)
    et la dépose dans son emplacement ; le thread audio la prend sans verrou bloquant et fond l'ancienne vers la nouvelle en 1024 échantillons.
    Aucune allocation ni destruction sur le thread audio (les anciennes bandes sont détruites par le thread message).
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

private:
    struct Slot
    {
        juce::SpinLock lock;
        std::unique_ptr<prisme::BandeProc> pending;    // déposée par le thread message
        bool hasPending = false;
        std::unique_ptr<prisme::BandeProc> cur, old;   // thread audio
        std::unique_ptr<prisme::BandeProc> trash;      // rendue au thread message pour destruction
        int fadePos = 0;
        prisme::BandeSpec msgSpec;                     // thread message : dernière spec construite
        bool msgActive = false;
    };

    void timerCallback() override;
    void syncBands (bool immediate);
    static constexpr int fadeLen = 1024;

    std::array<Slot, prismeParams::nBands> slots;
    std::atomic<double> fsHz { 0.0 };
    prisme::Retard<prisme::Engine::latence> secL, secR;
    juce::SmoothedValue<float> outGain;
    juce::AbstractFifo fifo { 8192 };
    std::vector<float> fifoBuf = std::vector<float> (8192, 0.0f);
    std::vector<double> bufL, bufR;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (PrismeProcessor)
};
