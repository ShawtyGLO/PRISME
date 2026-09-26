// PRISME — assemblage des 5 bandes en flux (port de _proto/prisme_engine_stream.py).
//   sortie = entrée retardée + Σ deltas des bandes (parallèle : l'ordre n'a pas d'importance) ; modes de canal Stéréo / Mid / Side / L / R.
// LATENCE FIXE de 20 échantillons (Exciter::latence) : le sec ET les deltas du Tame / Shape / Lift (latence propre nulle) sont retardés d'autant,
// avec ou sans Exciter actif (les hôtes n'aiment pas une latence qui change). À déclarer avec setLatencySamples (20).
// `BandeProc` = UNE bande (ses instances par canal + ses retards) : le plugin les remplace une à une avec un fondu quand un réglage change.
// Aucune dépendance JUCE. prepare() alloue ; process() n'alloue pas.
#pragma once
#include "Exciter.h"
#include "ExciterV2.h"
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
    ProfilExc profil = ProfilExc::MordantChaud;              // Exciter v2 : Doux / Chaud / Mordant / Mordant chaud
    SourceExc source = SourceExc::Auto;
    double tilt = 0.0;                                      // −1 … +1, mode Bande seulement
    double drive = 2.5;                                     // « Harmoniques » : niveau normalisé à l'entrée de la courbe (0,3 doux … 6 dur)
    // Tame
    double width = 0.5;
    // Shape
    Shape::Cible cible = Shape::Cible::Transitoires;
    double timeMs = 0.0, sens = 0.85;                       // timeMs <= 0 : durée par défaut
    // Lift
    double amount = 50.0, releaseMs = 150.0;

    bool actif() const { return on && gainDb != 0.0; }      // gain 0 : sortie = entrée retardée exactement
    bool operator== (const BandeSpec& o) const
    {
        return on == o.on && type == o.type && forme == o.forme && f0 == o.f0 && q == o.q && gainDb == o.gainDb && canal == o.canal && profil == o.profil
            && source == o.source && drive == o.drive && tilt == o.tilt && width == o.width && cible == o.cible && timeMs == o.timeMs && sens == o.sens && amount == o.amount && releaseMs == o.releaseMs;
    }
    bool operator!= (const BandeSpec& o) const { return ! (*this == o); }
};

// Une bande : renvoie son DELTA stéréo aligné sur l'entrée retardée de `latence`.
class BandeProc
{
public:
    void prepare (double fs, const BandeSpec& s)
    {
        spec = s;
        n = (s.canal == Canal::Stereo && s.type != TypeBande::Exciter) ? 2 : 1;      // Exciter v2 : une seule chaîne (non-linéarité LIÉE : source = milieu)
        for (int i = 0; i < n; ++i)
        {
            const size_t k = (size_t) i;
            retard[k].init (0.0);
            switch (s.type)
            {
                case TypeBande::Exciter: exc[k] = std::make_unique<ExciterV2>(); exc[k]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.profil, s.source, s.drive, s.tilt); break;
                case TypeBande::Tame:    tame[k] = std::make_unique<Tame>();   tame[k]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.width); break;
                case TypeBande::Shape:   shape[k] = std::make_unique<Shape>(); shape[k]->prepare (fs, s.cible, s.forme, s.f0, s.q, s.gainDb, s.timeMs, s.sens); break;
                case TypeBande::Lift:    lift[k] = std::make_unique<Lift>();   lift[k]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.amount, s.releaseMs); break;
            }
        }
    }

    const BandeSpec& getSpec() const { return spec; }

    // Gain en direct (aucune réinitialisation d'état) : glisser le gain d'une bande ne reconstruit rien.
    void setGain (double gainDb)
    {
        spec.gainDb = gainDb;
        for (int i = 0; i < n; ++i)
        {
            const size_t k = (size_t) i;
            if (exc[k]) exc[k]->setGain (gainDb);
            if (tame[k]) tame[k]->setGain (gainDb);
            if (shape[k]) shape[k]->setGain (gainDb);
            if (lift[k]) lift[k]->setGain (gainDb);
        }
    }

    void setTilt (double t)
    {
        spec.tilt = t;
        for (int i = 0; i < n; ++i)
            if (exc[(size_t) i]) exc[(size_t) i]->setTilt (t);
    }

    void setDrive (double d)
    {
        spec.drive = d;
        for (int i = 0; i < n; ++i)
            if (exc[(size_t) i]) exc[(size_t) i]->setDrive (d);
    }

    inline void process (double L, double R, double& dL, double& dR)
    {
        dL = dR = 0.0;
        switch (spec.canal)
        {
            case Canal::Stereo:
                if (spec.type == TypeBande::Exciter) { const double d = delta (0, 0.5 * (L + R)); dL = dR = d; }      // Exciter : lié (milieu)
                else { dL = delta (0, L); dR = delta (1, R); }
                break;
            case Canal::Mid:   { const double d = delta (0, 0.5 * (L + R)); dL = dR = d; break; }
            case Canal::Side:  { const double d = delta (0, 0.5 * (L - R)); dL = d; dR = -d; break; }
            case Canal::Left:  dL = delta (0, L); break;
            case Canal::Right: dR = delta (0, R); break;
        }
    }

private:
    inline double delta (int i, double z)
    {
        const size_t k = (size_t) i;
        switch (spec.type)
        {
            case TypeBande::Exciter: return exc[k]->process (z);                                   // porte déjà la latence
            case TypeBande::Tame:    return retard[k].push (tame[k]->process (z) - z);            // latence propre nulle : on retarde le delta
            case TypeBande::Shape:   return retard[k].push (shape[k]->process (z) - z);
            case TypeBande::Lift:    return retard[k].push (lift[k]->process (z) - z);
        }
        return 0.0;
    }

    BandeSpec spec;
    int n = 1;
    std::array<std::unique_ptr<ExciterV2>, 2> exc;
    std::array<std::unique_ptr<Tame>, 2> tame;
    std::array<std::unique_ptr<Shape>, 2> shape;
    std::array<std::unique_ptr<Lift>, 2> lift;
    std::array<Retard<Exciter::latence>, 2> retard;
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
            if (! s.actif()) continue;
            auto b = std::make_unique<BandeProc>();
            b->prepare (fs, s);
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
                double dL, dR;
                b->process (L, R, dL, dR);
                oL += dL;
                oR += dR;
            }
            outL[i] = oL;
            outR[i] = oR;
        }
    }

private:
    double fs = 48000;
    Retard<Exciter::latence> secL, secR;
    std::vector<std::unique_ptr<BandeProc>> bandes;
};
}
