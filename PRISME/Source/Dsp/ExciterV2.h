// PRISME — Exciter v2 (port de _proto/prisme_exciter_v2_stream.py) : à seuil relatif, entrée MONO (non-linéarité liée), wet sans normalisation.
//   source (Auto : bande f0/h sur 2 sections ; Bande : la zone, avec Tilt) → niveau lent S (τ 400 ms) et rapide e (τ 3 ms) → porte de seuil RELATIF
//   → u = drive·s/S → ×2 (FIR 41) → courbe ADAA ordre 1 → ×1 → résidu = y − pente·u → wet = résidu · S · porte · niveau → filtre de sortie (3 sections) → coupe-continu 20 Hz.
// Profils : Doux (tanh), Chaud (tanh décalé, paires), Mordant (cubique borné), Mordant chaud (cubique borné décalé).
// LATENCE : 20 échantillons de base. process() renvoie le wet aligné sur l'entrée retardée de 20. Aucune dépendance JUCE ; aucune allocation dans process().
#pragma once
#include "Biquad.h"
#include "Exciter.h"        // Retard, Historique, courbes::F / f (Class-A), tables
#include <algorithm>
#include <cmath>

namespace prisme
{
enum class ProfilExc { Doux, Chaud, Mordant, MordantChaud };

class ExciterV2
{
public:
    static constexpr int latence = 20;

    // gainDb : gain de bande (≥ 0) → niveau du wet = 10^((g − 3)/20) × niveau lent de la source.
    void prepare (double fs, Forme forme_, double f0_, double q, double gainDb, ProfilExc profil_, SourceExc source_, double drive_ = 2.5, double tilt = 0.0)
    {
        profil = profil_;
        source = source_;
        forme = forme_;
        f0 = f0_;
        fsHz = fs;
        drive = drive_;
        setGain (gainDb);
        const int h = (profil == ProfilExc::Chaud) ? 2 : 3;
        if (source == SourceExc::Auto)
        {
            nSrc = 2;
            const auto c = zoneFilter (forme, fs, std::max (f0 / h, 60.0), std::max (q, 2.0));
            src.set (c); src2.set (c);
        }
        else { nSrc = 1; src.set (zoneFilter (forme, fs, f0, q)); }
        const auto zc = zoneFilter (forme, fs, f0, q);
        for (auto& o : out) o.set (zc);
        cS = std::exp (-1.0 / (0.4 * fs));
        cE = std::exp (-1.0 / (0.003 * fs));
        rDc = 1.0 - 2.0 * kPi * 20.0 / fs;
        reset();
        setTilt (tilt);
    }

    void setGain (double gainDb) { niveau = std::pow (10.0, (gainDb - 3.0) / 20.0); }      // en direct
    void setDrive (double d) { drive = d; }                                                   // en direct

    // Tilt −1 … +1 (mode Bande seulement) ; en direct, l'état des filtres est conservé.
    void setTilt (double t)
    {
        if (source != SourceExc::Bande) return;
        if (std::abs (t) <= 1e-9 && ! tiltOn) return;
        const double pv = forme == Forme::ShelfAigu ? std::min (0.4 * fsHz, f0 * 2.5) : forme == Forme::ShelfGrave ? std::max (40.0, f0 / 2.5) : f0;
        tiltLo.set (rbjShelf (fsHz, pv, -0.5 * tiltDb * t, false));
        tiltHi.set (rbjShelf (fsHz, pv, +0.5 * tiltDb * t, true));
        tiltOn = true;
    }

    void reset()
    {
        src.reset(); src2.reset(); tiltLo.reset(); tiltHi.reset();
        for (auto& o : out) o.reset();
        zS = zE = 0.0;
        x1 = 0.0;
        hUp.reset(); hY.reset();
        du.init (0.0); dS.init (1e-7); dp.init (0.0);
        dcX = dcY = 0.0;
    }

    inline double process (double x)
    {
        double s = src.process (x);
        if (nSrc == 2) s = src2.process (s);
        if (tiltOn) s = tiltHi.process (tiltLo.process (s));
        const double a = std::abs (s);
        zS = (1.0 - cS) * a + cS * zS;
        zE = (1.0 - cE) * a + cE * zE;
        const double S = zS * (kPi / 2.0) + 1e-7, e = zE * (kPi / 2.0);
        const double rel = 20.0 * std::log10 ((e + 1e-12) / S);
        const double v = std::clamp ((rel - seuilDb) / 6.0, 0.0, 1.0);
        const double porte = v * v * (3.0 - 2.0 * v);
        const double u = drive * s / S;
        // ×2 : v0 = Σ H_UP[2k]·u[n−k], v1 = Σ H_UP[2k+1]·u[n−k]
        hUp.push (u);
        double v0 = 0, v1 = 0;
        for (int k = 0; k < 21; ++k) v0 += tables::hUp[2 * k] * hUp.at (k);
        for (int k = 0; k < 20; ++k) v1 += tables::hUp[2 * k + 1] * hUp.at (k);
        hY.push (adaa (v0));
        double y = 0;
        for (int k = 0; k < 41; ++k) y += tables::h0[k] * hY.at (k);
        hY.push (adaa (v1));
        const double ud = du.push (u), Sd = dS.push (S), pd = dp.push (porte);
        double res = (y - pente() * ud) * Sd * pd * niveau;
        for (auto& o : out) res = o.process (res);
        const double rdc = res - dcX + rDc * dcY;              // coupe-continu 20 Hz
        dcX = res;
        dcY = rdc;
        return rdc;
    }

private:
    static constexpr double seuilDb = 3.0, tiltDb = 9.0;

    inline double pente() const { return profil == ProfilExc::Chaud ? 1.0 - std::tanh (0.35) * std::tanh (0.35) : 1.0; }

    static double logcosh (double u) { const double a = std::abs (u); return a + std::log1p (std::exp (-2.0 * a)) - std::log (2.0); }

    inline double curveF (double x) const
    {
        switch (profil)
        {
            case ProfilExc::Doux:          return std::tanh (x);
            case ProfilExc::Chaud:         return std::tanh (x + 0.35);
            case ProfilExc::Mordant:       return courbes::f (ModeSat::ClassA, x);
            case ProfilExc::MordantChaud:  return courbes::f (ModeSat::ClassA, x + 0.25);
        }
        return x;
    }

    inline double curvePrim (double x) const
    {
        switch (profil)
        {
            case ProfilExc::Doux:          return logcosh (x);
            case ProfilExc::Chaud:         return logcosh (x + 0.35);
            case ProfilExc::Mordant:       return courbes::F (ModeSat::ClassA, x);
            case ProfilExc::MordantChaud:  return courbes::F (ModeSat::ClassA, x + 0.25);
        }
        return 0.5 * x * x;
    }

    // ADAA d'ordre 1 sur v (état = échantillon précédent)
    inline double adaa (double v)
    {
        const double dxv = v - x1;
        const double r = std::abs (dxv) < 1e-6 ? curveF (0.5 * (v + x1)) : (curvePrim (v) - curvePrim (x1)) / dxv;
        x1 = v;
        return r;
    }

    ProfilExc profil = ProfilExc::MordantChaud;
    SourceExc source = SourceExc::Auto;
    Forme forme = Forme::Cloche;
    double f0 = 1000.0, fsHz = 48000.0, drive = 2.5, niveau = 1.0;
    Biquad src, src2, tiltLo, tiltHi;
    std::array<Biquad, 3> out;
    int nSrc = 2;
    bool tiltOn = false;
    double cS = 0, cE = 0, rDc = 0, zS = 0, zE = 0, x1 = 0, dcX = 0, dcY = 0;
    Historique<21> hUp;
    Historique<41> hY;
    Retard<latence> du, dS, dp;
};
}
