// PRISME — filtres coupe-bas / coupe-haut PAR BANDE, à phase compensée (port de _proto/prisme_filtres.py).
//   y = Π AP · (x + Σ m_i · delta_i) : filtre Linkwitz-Riley sur le delta de la bande + passe-tout correspondant sur le sec et sur les deltas des AUTRES bandes
//   → l'effet réel = l'effet affiché (un filtre ordinaire sur le delta faussait l'effet de 5 à 16 dB), latence nulle.
//   24 dB/oct : Butterworth ordre 2 (RBJ, Q √½) au carré, passe-tout RBJ Q √½.  12 dB/oct : Butterworth ordre 1 au carré (coupe-bas en polarité inversée), passe-tout ordre 1.
// Transitions : chaque filtre a une présence p (0 … 1, rampe 30 ms) : étage = p·F(s) + (1 − p)·s ; changement de pente = fondu vers 0, bascule, fondu vers 1 ;
// la fréquence glisse (lissage par bloc). Filtre inactif et présence nulle : non calculé (états remis à zéro).
// Aucune dépendance JUCE ; aucune allocation dans le traitement.
#pragma once
#include "Biquad.h"
#include <algorithm>
#include <array>
#include <cmath>

namespace prisme
{
class FiltresBandes
{
public:
    static constexpr int nBandes = 5, nFiltres = 2 * nBandes, nChemins = nBandes + 1;      // chemin 0 = sec, 1 … 5 = deltas des bandes

    struct Reglage { bool on = false; double f = 1000.0; int pente = 12; };

    void prepare (double fs_, bool immediat = true)
    {
        fs = fs_;
        rampe = 1.0 / (0.03 * fs);
        for (auto& f : filt) { f.p = 0.0; f.pente = f.cible.pente; f.fCour = f.cible.f; reset (f); }
        immediatProchain = immediat;
    }

    // Réglage voulu d'un filtre (bande 0 … 4, coupeHaut false = coupe-bas). `actif` = la bande elle-même est active (sinon : filtre éteint).
    void regle (int bande, bool coupeHaut, Reglage r, bool actif)
    {
        auto& f = filt[(size_t) (2 * bande + (coupeHaut ? 1 : 0))];
        f.cible = r;
        f.cible.on = r.on && actif;
        f.haut = coupeHaut;
    }

    // À appeler une fois par bloc (après les réglages) : pentes, glissement de fréquence, coefficients.
    void miseAJourBloc (int nEchantillons)
    {
        for (auto& f : filt)
        {
            if (immediatProchain) { f.pente = f.cible.pente; f.fCour = f.cible.f; f.p = f.cible.on ? 1.0 : 0.0; calcule (f); continue; }
            if (f.cible.pente != f.pente)
            {
                if (f.p <= 0.0) { f.pente = f.cible.pente; reset (f); calcule (f); }
            }
            const double a = std::exp (-(double) nEchantillons / (0.03 * fs));
            const double fNouv = std::exp (a * std::log (f.fCour) + (1.0 - a) * std::log (f.cible.f));
            if (std::abs (fNouv - f.fCour) > 1e-9 * f.fCour || ! f.calcule) { f.fCour = fNouv; calcule (f); }
        }
        immediatProchain = false;
    }

    // Sec (chemin 0), à appeler une fois par échantillon AVANT les deltas.
    inline void sec (double& L, double& R)
    {
        for (int k = 0; k < nFiltres; ++k)
        {
            auto& f = filt[(size_t) k];
            if (f.p <= 0.0 && ! f.cible.on) continue;
            L = f.p * f.ap[0][0].process (L) + (1.0 - f.p) * L;
            R = f.p * f.ap[0][1].process (R) + (1.0 - f.p) * R;
        }
    }

    // Delta de la bande (0 … 4).
    inline void delta (int bande, double& L, double& R)
    {
        for (int k = 0; k < nFiltres; ++k)
        {
            auto& f = filt[(size_t) k];
            if (f.p <= 0.0 && ! f.cible.on) continue;
            if (k / 2 == bande)
            {
                const double fl = f.signe * f.lr[1][0].process (f.lr[0][0].process (L));
                const double fr = f.signe * f.lr[1][1].process (f.lr[0][1].process (R));
                L = f.p * fl + (1.0 - f.p) * L;
                R = f.p * fr + (1.0 - f.p) * R;
            }
            else
            {
                L = f.p * f.ap[(size_t) bande + 1][0].process (L) + (1.0 - f.p) * L;
                R = f.p * f.ap[(size_t) bande + 1][1].process (R) + (1.0 - f.p) * R;
            }
        }
    }

    // Fin d'échantillon : avance les présences.
    inline void avance()
    {
        for (auto& f : filt)
        {
            const bool veut = f.cible.on && f.cible.pente == f.pente;
            if (veut && f.p < 1.0) f.p = std::min (1.0, f.p + rampe);
            else if (! veut && f.p > 0.0) { f.p = std::max (0.0, f.p - rampe); if (f.p <= 0.0) reset (f); }
        }
    }

private:
    struct Filtre
    {
        Reglage cible;
        bool haut = false, calcule = false;
        int pente = 12;
        double fCour = 1000.0, p = 0.0, signe = 1.0;
        std::array<std::array<Biquad, 2>, 2> lr;                 // [étage][canal]
        std::array<std::array<Biquad, 2>, nChemins> ap;          // [chemin][canal]
    };

    void reset (Filtre& f)
    {
        for (auto& e : f.lr) for (auto& b : e) b.reset();
        for (auto& c : f.ap) for (auto& b : c) b.reset();
    }

    void calcule (Filtre& f)
    {
        const double fc = std::clamp (f.fCour, 10.0, 0.45 * fs);
        BiquadCoefs e, a;
        if (f.pente == 24)
        {
            const double w0 = 2.0 * kPi * fc / fs, al = std::sin (w0) / (2.0 * 0.70710678118654752), c = std::cos (w0), a0 = 1.0 + al;
            e = f.haut ? rbjLowpass (fs, fc, 0.70710678118654752) : rbjHighpass (fs, fc, 0.70710678118654752);
            a = { (1.0 - al) / a0, -2.0 * c / a0, (1.0 + al) / a0, -2.0 * c / a0, (1.0 - al) / a0 };
            f.signe = 1.0;
        }
        else
        {
            const double K = std::tan (kPi * fc / fs), cc = (K - 1.0) / (K + 1.0);
            e = f.haut ? BiquadCoefs { K / (K + 1.0), K / (K + 1.0), 0.0, cc, 0.0 } : BiquadCoefs { 1.0 / (K + 1.0), -1.0 / (K + 1.0), 0.0, cc, 0.0 };
            a = { cc, 1.0, 0.0, cc, 0.0 };
            f.signe = f.haut ? 1.0 : -1.0;
        }
        for (auto& et : f.lr) for (auto& b : et) b.set (e);
        for (auto& c : f.ap) for (auto& b : c) b.set (a);
        f.calcule = true;
    }

    double fs = 48000.0, rampe = 0.001;
    bool immediatProchain = true;
    std::array<Filtre, nFiltres> filt;
};
}
