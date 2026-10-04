// PRISME — compensation de sonie (port de _proto/prisme_sonie.py) : le signal TRAITÉ est recalé sur la sonie (pondérée K, ITU-R BS.1770) du signal SEC.
//   puissance = somme des carrés pondérés K des deux canaux : cumulative pendant la 1re seconde, puis lissée (τ = 1 s) ;
//   écart = sonie(sec) − sonie(traité) borné à ±12 dB, évalué toutes les 16 échantillons, GELÉ si l'un des deux est sous −70 dB (silence) ;
//   gain = écart lissé (τ = 0,3 s). Sec et traité doivent être ALIGNÉS. Aucune dépendance JUCE ; aucune allocation dans process().
#pragma once
#include "Biquad.h"
#include <algorithm>
#include <cmath>

namespace prisme
{
class Sonie
{
public:
    static constexpr int dec = 16;
    static constexpr double tauMesure = 1.0, tauGain = 0.3, borneDb = 12.0, gateDb = -70.0;

    void prepare (double fs)
    {
        // pondération K : mêmes formules que le prototype (étage 1 shelf aigu, étage 2 passe-haut RLB)
        const double G = 3.999843853973347, Q = 0.7071752369554196, fc = 1681.974450955533;
        double K = std::tan (kPi * fc / fs);
        const double Vh = std::pow (10.0, G / 20.0), Vb = std::pow (Vh, 0.4996667741545416), a0 = 1.0 + K / Q + K * K;
        BiquadCoefs c1 { (Vh + Vb * K / Q + K * K) / a0, 2.0 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0, 2.0 * (K * K - 1.0) / a0, (1.0 - K / Q + K * K) / a0 };
        const double Q2 = 0.5003270373238773, fc2 = 38.13547087602444;
        K = std::tan (kPi * fc2 / fs);
        const double d = 1.0 + K / Q2 + K * K;
        BiquadCoefs c2 { 1.0, -2.0, 1.0, 2.0 * (K * K - 1.0) / d, (1.0 - K / Q2 + K * K) / d };
        for (auto* m : { &sec, &trt })
            for (int c = 0; c < 2; ++c) { m->f1[c].set (c1); m->f2[c].set (c2); }
        cM = std::exp (-1.0 / (tauMesure * fs));
        cG = std::exp (-1.0 / (tauGain * fs));
        kRef = (long long) (tauMesure * fs);
        reset();
    }

    void reset()
    {
        for (auto* m : { &sec, &trt })
        {
            for (int c = 0; c < 2; ++c) { m->f1[c].reset(); m->f2[c].reset(); }
            m->n = 0; m->somme = 0.0; m->p = 0.0;
        }
        cible = g = 0.0;
        cnt = 0;
    }

    // Un échantillon stéréo : renvoie le gain linéaire à appliquer au traité (gainDb : même valeur en dB, pour l'affichage).
    inline double process (double secL, double secR, double trtL, double trtR, double& gainDb)
    {
        const double ps = sec.puissance (secL, secR, cM, kRef), pt = trt.puissance (trtL, trtR, cM, kRef);
        if (cnt % dec == 0)
        {
            const double Ls = 10.0 * std::log10 (ps + 1e-20), Lt = 10.0 * std::log10 (pt + 1e-20);
            if (Ls > gateDb && Lt > gateDb) cible = std::clamp (Ls - Lt, -borneDb, borneDb);
        }
        ++cnt;
        g = (1.0 - cG) * cible + cG * g;
        gainDb = g;
        return std::pow (10.0, g / 20.0);
    }

private:
    struct Mesure
    {
        Biquad f1[2], f2[2];
        long long n = 0;
        double somme = 0.0, p = 0.0;

        inline double puissance (double l, double r, double c, long long kRef)
        {
            const double yl = f2[0].process (f1[0].process (l)), yr = f2[1].process (f1[1].process (r));
            const double e = yl * yl + yr * yr;
            if (n < kRef) { somme += e; p = somme / (double) (n + 1); }          // moyenne cumulative
            else p = (1.0 - c) * e + c * p;
            ++n;
            return p;
        }
    };

    Mesure sec, trt;
    double cM = 0, cG = 0, cible = 0, g = 0;
    long long kRef = 48000, cnt = 0;
};
}
