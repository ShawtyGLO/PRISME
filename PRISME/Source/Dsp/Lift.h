// PRISME — type de bande « Lift / Détail » (port de _proto/prisme_lift.py). Gain par bande dépendant du niveau, bipolaire, additif.
//   sortie = entrée + (g(L) − 1) · b, b = signal de la zone ; seuil ABSOLU (Amount 0…100 % → −60…−12 dBFS) ; protection du souffle automatique.
// Causal, latence propre nulle, état conservé entre blocs, aucune allocation. Aucune dépendance JUCE.
#pragma once
#include "Biquad.h"
#include <algorithm>
#include <cmath>

namespace prisme
{
class Lift
{
public:
    static constexpr double seuilMin = -60.0, seuilMax = -12.0, plancherMin = -75.0, plancherMax = -55.0, montee = 3.0, marge = 8.0;

    static double seuilDbfs (double amount) { return seuilMin + (seuilMax - seuilMin) * std::clamp (amount, 0.0, 100.0) / 100.0; }

    static double smoothstep (double u)
    {
        u = std::clamp (u, 0.0, 1.0);
        return u * u * (3.0 - 2.0 * u);
    }

    void prepare (double fs, Forme forme, double f0, double q, double gainDb, double amount, double releaseMs)
    {
        G = gainDb;
        W = std::max (1.667 * std::abs (G), 6.0);
        T = seuilDbfs (amount);
        band.set (zoneFilter (forme, fs, f0, q));
        const double ta = std::clamp (3.0 / f0, 0.002, 0.020);
        ca = std::exp (-1.0 / (ta * fs));
        cr = std::exp (-1.0 / ((releaseMs / 1000.0 / 3.0) * fs));
        cs = std::exp (-1.0 / (0.1 * fs));
        cn = std::exp (-1.0 / ((8.685889638 / montee) * fs));
        reset();
    }

    void reset()
    {
        band.reset();
        started = false;
        yHold = 0.0;
        invFloor = 0.0;
    }

    // Traite un échantillon ; renvoie la sortie. `gOut` (facultatif) reçoit le gain linéaire g appliqué à la zone.
    inline double process (double x, double* gOut = nullptr)
    {
        const double b = band.process (x), ab = std::abs (b);
        if (! started)                                         // démarrage à chaud : le plancher ne part pas de zéro
        {
            ea.warm (ab); es.warm (ab);
            ea.setCoef (ca); es.setCoef (cs);
            started = true;
            firstSample = true;
        }
        const double Ea = ea.process (ab);
        yHold = std::max (Ea, cr * yHold);                     // attaque rapide, relâchement exponentiel
        const double L = 20.0 * std::log10 (yHold * (kPi / 2.0) + 1e-12);
        double s = smoothstep ((T - L) / W);
        if (G > 0.0)
        {
            const double Es = es.process (ab);
            const double inv = std::min (1.0 / (Es * (kPi / 2.0) + 1e-9), std::pow (10.0, -plancherMin / 20.0));
            if (firstSample) { invFloor = inv; firstSample = false; }
            invFloor = std::max (inv, cn * invFloor);          // min-suiveur : 1/N = max(1/Es, c·1/N)
            const double N = std::clamp (-20.0 * std::log10 (invFloor), plancherMin, plancherMax);
            const double Ls = 20.0 * std::log10 (Es * (kPi / 2.0) + 1e-12);
            s *= smoothstep ((Ls - N - marge) / 6.0);
        }
        const double g = std::pow (10.0, G * s / 20.0);
        if (gOut) *gOut = g;
        return x + (g - 1.0) * b;
    }

private:
    Biquad band;
    OnePole ea, es;
    double G = 0, W = 6, T = -40, ca = 0, cr = 0, cs = 0, cn = 0, yHold = 0, invFloor = 0;
    bool started = false, firstSample = false;
};
}
