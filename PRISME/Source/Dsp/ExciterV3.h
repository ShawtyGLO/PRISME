// PRISME — Exciter v3 « Aural » (port de _proto/prisme_exciter_v3_stream.py ; prototype jugé « précis et naturel » par llg53, 2026-09-28).
//   source = zone de la bande [+ Tilt] → niveau lent S (τ 400 ms) → u = drive·b/S → ×2 (FIR 41) → courbe ADAA ordre 1 → ×1 ; y0 = y − f(0)
//   → wet = (y0 − pureté·c1·u)·S/(drive·c1) → filtre de la zone (1 section) → coupe-continu 20 Hz → × k, k = 10^(g/20) − 1.
//   c1 : gain du fondamental de la courbe pour un sinus d'amplitude drive (le fondamental du wet ≈ la zone : « +g dB » ≈ renfort de g dB).
// Entrée MONO (milieu : non-linéarité liée). LATENCE 20 échantillons. Aucune dépendance JUCE ; aucune allocation dans process().
#pragma once
#include "Biquad.h"
#include "Exciter.h"
#include "ExciterV2.h"      // ProfilExc
#include <algorithm>
#include <cmath>

namespace prisme
{
class ExciterV3
{
public:
    static constexpr int latence = 20;

    void prepare (double fs, Forme forme_, double f0_, double q, double gainDb, ProfilExc profil_, double drive_ = 2.5, double tilt = 0.0, double purete_ = 0.0)
    {
        profil = profil_;
        forme = forme_;
        f0 = f0_;
        fsHz = fs;
        purete = purete_;
        setGain (gainDb);
        src.set (zoneFilter (forme, fs, f0, q));
        out.set (zoneFilter (forme, fs, f0, q));
        cS = std::exp (-1.0 / (0.4 * fs));
        rDc = 1.0 - 2.0 * kPi * 20.0 / fs;
        setDrive (drive_);
        reset();
        setTilt (tilt);
    }

    void setGain (double gainDb) { k = std::pow (10.0, gainDb / 20.0) - 1.0; }        // en direct
    void setPurete (double p) { purete = p; }                                            // en direct

    void setDrive (double d)                                                             // en direct (recalcule c1)
    {
        drive = d;
        fz = curveF (0.0);
        double acc = 0.0;
        for (int i = 0; i < 256; ++i)
        {
            const double th = 2.0 * kPi * (double) i / 256.0, s = std::sin (th);
            acc += (curveF (drive * s) - fz) * s;
        }
        c1 = std::max (2.0 * acc / 256.0 / drive, 1e-6);
    }

    void setTilt (double t)                                                              // en direct
    {
        if (std::abs (t) <= 1e-9 && ! tiltOn) return;
        const double pv = forme == Forme::ShelfAigu ? std::min (0.4 * fsHz, f0 * 2.5) : forme == Forme::ShelfGrave ? std::max (40.0, f0 / 2.5) : f0;
        tiltLo.set (rbjShelf (fsHz, pv, -0.5 * 9.0 * t, false));
        tiltHi.set (rbjShelf (fsHz, pv, +0.5 * 9.0 * t, true));
        tiltOn = true;
    }

    void reset()
    {
        src.reset(); out.reset(); tiltLo.reset(); tiltHi.reset();
        zS = 0.0; x1 = 0.0;
        hUp.reset(); hY.reset();
        du.init (0.0); dS.init (1e-7);
        dcX = dcY = 0.0;
    }

    inline double process (double x)
    {
        double b = src.process (x);
        if (tiltOn) b = tiltHi.process (tiltLo.process (b));
        zS = (1.0 - cS) * std::abs (b) + cS * zS;
        const double S = zS * (kPi / 2.0) + 1e-7;
        const double u = drive * b / S;
        hUp.push (u);
        double v0 = 0, v1 = 0;
        { const double* hu = hUp.data();                                              // lecture contigue (tampon miroir), memes produits, meme ordre
          for (int i = 0; i < 21; ++i) v0 += tables::hUp[2 * i] * hu[i];
          for (int i = 0; i < 20; ++i) v1 += tables::hUp[2 * i + 1] * hu[i]; }
        hY.push (adaa (v0));
        double y = 0;
        { const double* hy = hY.data();
          for (int i = 0; i < 41; ++i) y += tables::h0[i] * hy[i]; }
        hY.push (adaa (v1));
        const double ud = du.push (u), Sd = dS.push (S);
        double res = (y - fz - purete * c1 * ud) * Sd / (drive * c1);
        res = out.process (res);
        const double rdc = res - dcX + rDc * dcY;
        dcX = res;
        dcY = rdc;
        return k * rdc;
    }

private:
    static double logcosh (double u) { const double a = std::abs (u); return a + std::log1p (std::exp (-2.0 * a)) - 0.69314718055994530942; }   // ln 2 constant (etait recalcule)

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

    inline double adaa (double v)
    {
        const double dxv = v - x1;
        const double r = std::abs (dxv) < 1e-6 ? curveF (0.5 * (v + x1)) : (curvePrim (v) - curvePrim (x1)) / dxv;
        x1 = v;
        return r;
    }

    ProfilExc profil = ProfilExc::MordantChaud;
    Forme forme = Forme::Cloche;
    double f0 = 1000.0, fsHz = 48000.0, drive = 2.5, purete = 0.0, k = 0.0, c1 = 1.0, fz = 0.0;
    Biquad src, out, tiltLo, tiltHi;
    bool tiltOn = false;
    double cS = 0, rDc = 0, zS = 0, x1 = 0, dcX = 0, dcY = 0;
    Historique<21> hUp;
    Historique<41> hY;
    Retard<latence> du, dS;
};
}
