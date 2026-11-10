// PRISME — type de bande « Exciter » (port de _proto/prisme_exciter_stream.py) : la recette « Iron Auto flanc raide » en flux.
//   source (Auto : passe-bande à f0/h, 2 sections ; Bande : la zone) → gain adaptatif → ×2 (FIR 41, Kaiser 5) → saturation ADAA ordre 1
//   → de-emphasis exact (soustraction de la réponse linéaire de la même chaîne, projection glissante τ 30 ms) → coupe-continu 20 Hz
//   → filtre de sortie (3 sections de la zone, source Auto) → normalisation par la zone (τ 200 ms) → signe du gain.
// LATENCE : 20 échantillons de base (FIR ×2). process() renvoie le DELTA aligné sur l'entrée retardée de 20 échantillons.
// Causal, état conservé entre blocs, aucune allocation dans process(). Aucune dépendance JUCE.
#pragma once
#include "Biquad.h"
#include "Tables.h"
#include <algorithm>
#include <array>
#include <cmath>

namespace prisme
{
enum class ModeSat { Triode, Diode, Iron, ClassA, Rect };
enum class SourceExc { Auto, Bande };

namespace courbes
{
constexpr double B = 0.18, EPS_R = 0.05;               // EPS_R : coude du Rectifier à drive 1,5 (varie avec « Saturation » : eps = 0,05 · (1,5 / drive)²)
inline double logcosh (double u) { const double a = std::abs (u); return a + std::log1p (std::exp (-2.0 * a)) - 0.69314718055994530942; }
inline double SL() { const double t = std::tanh (B); return 1.0 - t * t; }

inline double f (ModeSat m, double x, double eps = EPS_R)
{
    switch (m)
    {
        case ModeSat::Triode: return (std::tanh (x + B) - std::tanh (B)) / SL();
        case ModeSat::Diode:  return x >= 0 ? 1.0 - std::exp (-std::abs (x)) : -(1.0 - std::exp (-1.5 * std::abs (x))) / 1.5;
        case ModeSat::Iron:   return x / std::sqrt (1.0 + x * x);
        case ModeSat::ClassA: { const double c = std::clamp (x, -1.0, 1.0); return c - c * c * c / 3.0; }
        case ModeSat::Rect:   return std::sqrt (x * x + eps * eps) - eps;
    }
    return x;
}

inline double F (ModeSat m, double x, double eps = EPS_R)         // primitive (ADAA d'ordre 1)
{
    switch (m)
    {
        case ModeSat::Triode: return (logcosh (x + B) - x * std::tanh (B)) / SL();
        case ModeSat::Diode:
        {
            const double ax = std::abs (x);
            return x >= 0 ? ax + std::exp (-ax) - 1.0 : -(-ax - std::exp (-1.5 * ax) / 1.5) / 1.5 - 1.0 / 2.25;
        }
        case ModeSat::Iron:   return std::sqrt (1.0 + x * x);
        case ModeSat::ClassA:
        {
            const double a = std::abs (x);
            return a <= 1.0 ? a * a / 2.0 - a * a * a * a / 12.0 : 5.0 / 12.0 + (2.0 / 3.0) * (a - 1.0);
        }
        case ModeSat::Rect:   return 0.5 * (x * std::sqrt (x * x + eps * eps) + eps * eps * std::asinh (x / eps)) - eps * x;
    }
    return 0.5 * x * x;
}

inline int harmoniqueDominant (ModeSat m) { return (m == ModeSat::Iron || m == ModeSat::ClassA) ? 3 : 2; }
}

// Ligne à retard de N échantillons (N fixe), valeur initiale donnée.
template <int N>
class Retard
{
public:
    void init (double v) { buf.fill (v); pos = 0; }
    inline double push (double x) { const double y = buf[(size_t) pos]; buf[(size_t) pos] = x; pos = (pos + 1 == N) ? 0 : pos + 1; return y; }

private:
    std::array<double, N> buf {};
    int pos = 0;
};

// Historique circulaire de N valeurs (at(0) = la plus récente).
template <int N>
class Historique
{
public:
    void reset() { buf.fill (0.0); pos = N; }
    // tampon miroir : la valeur est ecrite en pos et en pos + N, donc buf[pos .. pos + N - 1] est toujours l'historique contigu (at(0) = la plus recente)
    inline void push (double x) { pos = (pos == 0) ? N - 1 : pos - 1; buf[(size_t) pos] = x; buf[(size_t) pos + N] = x; }
    inline double at (int k) const { return buf[(size_t) (pos + k)]; }
    inline const double* data() const { return buf.data() + pos; }                    // pointeur contigu sur les N dernieres valeurs

private:
    std::array<double, 2 * N> buf {};
    int pos = N;
};

class Exciter
{
public:
    static constexpr int latence = 20;                       // échantillons de base, à déclarer à l'hôte

    void prepare (double fs, Forme forme_, double f0_, double q, double gainDb, ModeSat mode_, SourceExc source_)
    {
        mode = mode_;
        source = source_;
        forme = forme_;
        f0 = f0_;
        fsHz = fs;
        tiltOn = false;
        tiltLo.reset(); tiltHi.reset();
        sign = gainDb >= 0 ? 1.0 : -1.0;
        amount = std::pow (10.0, std::abs (gainDb) / 20.0) - 1.0;
        focus = source != SourceExc::Bande;
        const double fsrc = std::max (f0_ / courbes::harmoniqueDominant (mode), 60.0), qsrc = std::max (q, 2.0);
        if (source == SourceExc::Auto) { nSrc = 2; src.set (zoneFilter (forme_, fs, fsrc, qsrc)); src2.set (zoneFilter (forme_, fs, fsrc, qsrc)); }
        else                           { nSrc = 1; src.set (zoneFilter (forme_, fs, f0_, q)); }
        ref1.set (zoneFilter (forme_, fs, fsrc, qsrc));
        ref2.set (zoneFilter (forme_, fs, fsrc, qsrc));
        const auto zc = zoneFilter (forme_, fs, f0_, q);
        for (auto& o : out) o.set (zc);
        zb.set (zc);
        aEnv = std::exp (-1.0 / (agcTau * fs));
        aNull = std::exp (-1.0 / (0.03 * fs));
        aNorm = std::exp (-1.0 / (0.2 * fs));
        rDc = 1.0 - 2.0 * kPi * 20.0 / fs;
        reset();
    }

    void setDrive (double d)                                  // en direct, sans réinitialiser
    {
        drive = d;
        epsR = courbes::EPS_R * (1.5 / d) * (1.5 / d);       // Rectifier : « Saturation » règle le coude (homogène en amplitude, le niveau n'y change rien)
    }

    // Tilt −1 … +1 (mode Bande seulement) : bascule de tonalité de la source avant la saturation ; en direct, l'état des filtres est conservé.
    void setTilt (double t)
    {
        if (source != SourceExc::Bande) return;
        if (std::abs (t) <= 1e-9 && ! tiltOn) return;
        const double pv = forme == Forme::ShelfAigu ? std::min (0.4 * fsHz, f0 * 2.5) : forme == Forme::ShelfGrave ? std::max (40.0, f0 / 2.5) : f0;
        tiltLo.set (rbjShelf (fsHz, pv, -0.5 * tiltDb * t, false));
        tiltHi.set (rbjShelf (fsHz, pv, +0.5 * tiltDb * t, true));
        tiltOn = true;
    }

    void setGain (double gainDb)                              // en direct, sans réinitialiser
    {
        sign = gainDb >= 0 ? 1.0 : -1.0;
        amount = std::pow (10.0, std::abs (gainDb) / 20.0) - 1.0;
    }

    void reset()
    {
        src.reset(); src2.reset(); ref1.reset(); ref2.reset(); zb.reset();
        for (auto& o : out) o.reset();
        count = 0;
        env = 0; x1 = x1l = 0;
        hUp.reset(); hY.reset(); hYl.reset();
        dg.init (1.0);                                       // le gain adaptatif vaut ≥ 1 : jamais de division par 0
        ds.init (0.0); dx.init (0.0);
        num = den = 0; dcX = dcY = 0; rs2 = rz2 = rr2 = 0;
    }

    inline double process (double x)
    {
        // source
        double s0 = src.process (x);
        if (nSrc == 2) s0 = src2.process (s0);
        if (tiltOn) s0 = tiltHi.process (tiltLo.process (s0));       // Tilt (mode Bande) avant l'AGC et la saturation
        // gain adaptatif (AGC : 0,05 … +40 dB)
        env = (1.0 - aEnv) * std::abs (s0) + aEnv * env;
        const double g = std::clamp (drive / std::max (env * (kPi / 2.0), 1e-9), agcGmin, agcGmax);
        // ×2 : v[2n] = Σ H_UP[2k]·sin[n−k], v[2n+1] = Σ H_UP[2k+1]·sin[n−k]
        hUp.push (s0 * g);
        double v0 = 0, v1 = 0;
        for (int k = 0; k < 21; ++k) v0 += tables::hUp[2 * k] * hUp.at (k);
        for (int k = 0; k < 20; ++k) v1 += tables::hUp[2 * k + 1] * hUp.at (k);
        const long i2 = 2L * count;                          // démarrage : la version hors ligne n'a jamais vu la montée en régime du FIR
        if (i2 < latence)     v0 = 0.0;
        if (i2 + 1 < latence) v1 = 0.0;
        // ADAA ordre 1 (courbe et courbe linéaire), retour ×1 par le FIR (sorties paires seulement)
        hY.push (adaa (v0, false));
        hYl.push (adaa (v0, true));
        double y = 0, yl = 0;
        for (int k = 0; k < 41; ++k) { y += tables::h0[k] * hY.at (k); yl += tables::h0[k] * hYl.at (k); }
        hY.push (adaa (v1, false));
        hYl.push (adaa (v1, true));
        if (count < latence) { y = 0.0; yl = 0.0; }
        // tout ce qui se combine avec y est retardé de 20
        const double gD = dg.push (g), s0D = ds.push (s0), xD = dx.push (x);
        // de-emphasis exact : projection sur la réponse linéaire de la même chaîne
        num = (1.0 - aNull) * (y * yl) + aNull * num;
        den = (1.0 - aNull) * (yl * yl) + aNull * den;
        double res = (y - (num / (den + 1e-12)) * yl) / gD;
        const double rdc = res - dcX + rDc * dcY;            // coupe-continu 20 Hz
        dcX = res;
        dcY = rdc;
        res = rdc;
        if (focus)
            for (auto& o : out) res = o.process (res);
        // normalisation par la zone
        const double sRef = source == SourceExc::Auto ? s0D : ref2.process (ref1.process (xD));
        const double zbv = zb.process (xD);
        rs2 = (1.0 - aNorm) * (sRef * sRef) + aNorm * rs2;
        rz2 = (1.0 - aNorm) * (zbv * zbv) + aNorm * rz2;
        rr2 = (1.0 - aNorm) * (res * res) + aNorm * rr2;
        const double cible = amount * std::max (std::sqrt (rz2), floorRatio * std::sqrt (rs2));
        res *= std::clamp (cible / std::max (std::sqrt (rr2), 1e-9), 0.0, 100.0);
        ++count;
        return sign * res;
    }

private:
    // ADAA d'ordre 1 sur v ; l'état (échantillon précédent) est mis à jour ici.
    inline double adaa (double v, bool lin)
    {
        double& xp = lin ? x1l : x1;
        const double dxv = v - xp;
        double r;
        if (std::abs (dxv) < 1e-6) r = lin ? 0.5 * (v + xp) : courbes::f (mode, 0.5 * (v + xp), epsR);
        else if (lin)              r = (0.5 * v * v - 0.5 * xp * xp) / dxv;
        else                       r = (courbes::F (mode, v, epsR) - courbes::F (mode, xp, epsR)) / dxv;
        xp = v;
        return r;
    }

    static constexpr double floorRatio = 0.05;
    // AGC d'entrée : enveloppe 10 ms, gain de 0,05 à +40 dB (l'ancien plafond de +24 dB était atteint presque tout le temps : « Saturation » sans effet, delta pointu)
    static constexpr double agcTau = 0.01, agcGmin = 0.05, agcGmax = 100.0, tiltDb = 9.0;
    double epsR = courbes::EPS_R;
    Forme forme = Forme::Cloche;
    double f0 = 1000.0, fsHz = 48000.0;
    bool tiltOn = false;
    Biquad tiltLo, tiltHi;
    double drive = 1.5;                                        // niveau visé à l'entrée de la courbe : plus haut = plus saturé (réglage « Saturation »)
    ModeSat mode = ModeSat::Iron;
    SourceExc source = SourceExc::Auto;
    Biquad src, src2, ref1, ref2, zb;
    std::array<Biquad, 3> out;
    Historique<21> hUp;
    Historique<41> hY, hYl;
    Retard<latence> dg, ds, dx;
    int nSrc = 2;
    bool focus = true;
    long count = 0;
    double sign = 1, amount = 0, aEnv = 0, aNull = 0, aNorm = 0, rDc = 0;
    double env = 0, x1 = 0, x1l = 0, num = 0, den = 0, dcX = 0, dcY = 0, rs2 = 0, rz2 = 0, rr2 = 0;
};
}
