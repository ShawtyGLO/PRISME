// PRISME — type de bande « Shape » (port de _proto/prisme_shape.py v4) : gain sur les TRANSITOIRES ou le SUSTAIN de la bande, bipolaire.
//   sortie = entrée + (g(t) − 1) · b ; détecteur de MONTÉE d'enveloppe, sensibilité, durée, attaque du gain bornée, partition de l'unité.
// Causal, latence propre nulle, état conservé entre blocs. Aucune dépendance JUCE.
#pragma once
#include "Biquad.h"
#include <algorithm>
#include <cmath>
#include <vector>

namespace prisme
{
class Shape
{
public:
    enum class Cible { Transitoires, Sustain };

    // D arrondi « au pair » comme le round() de Python (tf·fs = 1102,5 à 44,1 kHz pour 120 Hz).
    // timeMs <= 0 : durée = 1 τ_f (défaut du prototype). sens : 0…1.
    void prepare (double fs, Cible cible_, Forme forme, double f0, double q, double gainDb, double timeMs, double sens)
    {
        cible = cible_;
        A = std::pow (10.0, gainDb / 20.0);
        band.set (zoneFilter (forme, fs, f0, q));
        const double tf = std::clamp (3.0 / f0, 0.002, 0.03);
        D = std::max (1, (int) std::nearbyint (tf * fs));
        cf = std::exp (-1.0 / (tf * fs));
        const double attPeriods = std::clamp (0.45 + 0.35 * std::log2 (f0 / 60.0) / std::log2 (250.0 / 60.0), 0.45, 0.8);
        cAtt = std::exp (-1.0 / (std::max (attPeriods / f0, 1.0 / fs) * fs));
        const double tauRel = timeMs > 0.0 ? (timeMs / 1000.0) / 3.0 : tf;
        cRel = std::exp (-1.0 / (tauRel * fs));
        m0 = 10.0 - 9.0 * sens;
        hist.assign ((size_t) D, 1e-12);
        reset();
    }

    void reset()
    {
        band.reset();
        zf = zAtt = yHold = 0.0;
        std::fill (hist.begin(), hist.end(), 1e-12);
        pos = 0;
    }

    inline double process (double x, double* gOut = nullptr)
    {
        const double b = band.process (x);
        zf = (1.0 - cf) * std::abs (b) + cf * zf;                  // enveloppe rapide
        const double Ef = zf, Efd = hist[(size_t) pos];            // E_f retardée de D échantillons
        hist[(size_t) pos] = Ef;
        pos = (pos + 1 == D) ? 0 : pos + 1;
        const double m = 20.0 * std::log10 ((Ef + 1e-12) / (Efd + 1e-12));
        double T = std::clamp ((m - m0) / 4.0, 0.0, 1.0);
        T *= std::clamp ((20.0 * std::log10 (Ef * (M_PI / 2.0) + 1e-12) + 95.0) / 10.0, 0.0, 1.0);   // porte absolue −95 dBFS
        yHold = std::max (T, cRel * yHold);                        // tient et relâche sur la durée choisie
        zAtt = (1.0 - cAtt) * yHold + cAtt * zAtt;                 // attaque du gain bornée
        const double poids = cible == Cible::Transitoires ? zAtt : 1.0 - zAtt;
        const double g = 1.0 + (A - 1.0) * poids;
        if (gOut) *gOut = g;
        return x + (g - 1.0) * b;
    }

private:
    Biquad band;
    Cible cible = Cible::Transitoires;
    std::vector<double> hist;
    int D = 1, pos = 0;
    double A = 1, cf = 0, cAtt = 0, cRel = 0, m0 = 1, zf = 0, zAtt = 0, yHold = 0;
};
}
