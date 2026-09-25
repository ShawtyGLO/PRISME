// PRISME — assemblage des 5 bandes en flux (port de _proto/prisme_engine_stream.py).
//   sortie = entrée retardée + Σ deltas des bandes (parallèle : l'ordre n'a pas d'importance) ; modes de canal Stéréo / Mid / Side / L / R.
// LATENCE FIXE de 20 échantillons (Exciter.latence) : le sec ET les deltas du Tame / Shape / Lift (latence propre nulle) sont retardés d'autant,
// avec ou sans Exciter actif (les hôtes n'aiment pas une latence qui change). À déclarer avec setLatencySamples (20).
// Aucune dépendance JUCE. prepare() alloue ; process() n'alloue pas.
#pragma once
#include "Exciter.h"
#include "Lift.h"
#include "Shape.h"
#include "Tame.h"
#include <array>
#include <memory>
#include <vector>

namespace prisme
{
enum class TypeBande { Exciter, Tame, Shape, Lift };
enum class Canal { Stereo, Mid, Side, Left, Right };

struct BandeSpec
{
    bool on = true;
    TypeBande type = TypeBande::Exciter;
    Forme forme = Forme::Cloche;
    double f0 = 1000.0, q = 0.71, gainDb = 0.0;
    Canal canal = Canal::Stereo;
    // Exciter
    ModeSat mode = ModeSat::Iron;
    SourceExc source = SourceExc::Auto;
    // Tame
    double width = 0.5;
    // Shape
    Shape::Cible cible = Shape::Cible::Transitoires;
    double timeMs = 0.0, sens = 0.85;                       // timeMs <= 0 : durée par défaut
    // Lift
    double amount = 50.0, releaseMs = 150.0;
};

class Engine
{
public:
    static constexpr int latence = Exciter::latence;

    void prepare (double fs_, const std::vector<BandeSpec>& specs)
    {
        fs = fs_;
        secL.init (0.0);
        secR.init (0.0);
        bandes.clear();
        for (const auto& s : specs)
        {
            if (! s.on || s.gainDb == 0.0) continue;         // gain 0 : sortie = entrée retardée exactement
            Bande b;
            b.spec = s;
            b.n = s.canal == Canal::Stereo ? 2 : 1;
            for (int i = 0; i < b.n; ++i) creer (b, i);
            bandes.push_back (std::move (b));
        }
    }

    // Traite n échantillons stéréo (in et out peuvent être identiques).
    void process (const double* inL, const double* inR, double* outL, double* outR, int n)
    {
        for (int i = 0; i < n; ++i)
        {
            const double L = inL[i], R = inR[i];
            double oL = secL.push (L), oR = secR.push (R);
            for (auto& b : bandes)
            {
                switch (b.spec.canal)
                {
                    case Canal::Stereo: oL += delta (b, 0, L); oR += delta (b, 1, R); break;
                    case Canal::Mid:   { const double d = delta (b, 0, 0.5 * (L + R)); oL += d; oR += d; break; }
                    case Canal::Side:  { const double d = delta (b, 0, 0.5 * (L - R)); oL += d; oR -= d; break; }
                    case Canal::Left:  oL += delta (b, 0, L); break;
                    case Canal::Right: oR += delta (b, 0, R); break;
                }
            }
            outL[i] = oL;
            outR[i] = oR;
        }
    }

private:
    struct Bande
    {
        BandeSpec spec;
        int n = 1;
        std::array<std::unique_ptr<Exciter>, 2> exc;
        std::array<std::unique_ptr<Tame>, 2> tame;
        std::array<std::unique_ptr<Shape>, 2> shape;
        std::array<std::unique_ptr<Lift>, 2> lift;
        std::array<Retard<Exciter::latence>, 2> retard;
    };

    void creer (Bande& b, int i) const
    {
        const auto& s = b.spec;
        b.retard[(size_t) i].init (0.0);
        switch (s.type)
        {
            case TypeBande::Exciter: b.exc[(size_t) i] = std::make_unique<Exciter>();   b.exc[(size_t) i]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.mode, s.source); break;
            case TypeBande::Tame:    b.tame[(size_t) i] = std::make_unique<Tame>();     b.tame[(size_t) i]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.width); break;
            case TypeBande::Shape:   b.shape[(size_t) i] = std::make_unique<Shape>();   b.shape[(size_t) i]->prepare (fs, s.cible, s.forme, s.f0, s.q, s.gainDb, s.timeMs, s.sens); break;
            case TypeBande::Lift:    b.lift[(size_t) i] = std::make_unique<Lift>();     b.lift[(size_t) i]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.amount, s.releaseMs); break;
        }
    }

    // Delta de la bande sur le signal z, aligné sur l'entrée retardée de `latence`.
    static inline double delta (Bande& b, int i, double z)
    {
        const size_t k = (size_t) i;
        switch (b.spec.type)
        {
            case TypeBande::Exciter: return b.exc[k]->process (z);                                   // porte déjà la latence
            case TypeBande::Tame:    return b.retard[k].push (b.tame[k]->process (z) - z);          // latence propre nulle : on retarde le delta
            case TypeBande::Shape:   return b.retard[k].push (b.shape[k]->process (z) - z);
            case TypeBande::Lift:    return b.retard[k].push (b.lift[k]->process (z) - z);
        }
        return 0.0;
    }

    double fs = 48000;
    Retard<Exciter::latence> secL, secR;
    std::vector<Bande> bandes;
};
}
