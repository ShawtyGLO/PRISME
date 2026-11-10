// PRISME — type de bande « Shape » v5 (port de _proto/prisme_shape5.py) : gain sur les TRANSITOIRES ou le SUSTAIN de la bande, bipolaire.
//   sortie = entrée + (g(t) − 1) · b(t − look),   b = signal de la zone ; look = 192 échantillons (LATENCE de l'assemblage).
// Détecteur de PERCUSSION validé à l'écoute (point de sauvegarde du 2026-10-01) : flux léger (banc 3 bandes/octave, SuperFlux) × veto tonal (résidu d'un prédicteur NLMS),
// seuil ADAPTATIF (quantile de la force sur 2 s), tenue, attaque lissée ; le poids calculé à l'instant n s'applique à b(n − look) : le gain arrive AVANT l'attaque.
// Causal en entrée, état conservé entre blocs, aucune allocation dans process(). Aucune dépendance JUCE.
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
    static constexpr int lookahead = 192;                    // = Engine::latence

    // timeMs <= 0 : durée par défaut (30 ms). sens : 0…1.
    void prepare (double fs, Cible cible_, Forme forme, double f0, double q, double gainDb, double timeMs, double sens)
    {
        cible = cible_;
        A = std::pow (10.0, gainDb / 20.0);
        band.set (zoneFilter (forme, fs, f0, q));
        // banc léger
        fb.clear(); ce.clear();
        for (int k = 0; k < 100; ++k)
        {
            const double f = 30.0 * std::pow (2.0, (double) k / (double) perOct);
            if (! (f < 0.45 * fs)) break;
            fb.push_back (f);
        }
        K = (int) fb.size();
        const double qb = 1.0 / (std::pow (2.0, 1.0 / (2.0 * perOct)) - std::pow (2.0, -1.0 / (2.0 * perOct)));
        for (auto* v : { &bB0, &bB1, &bB2, &bA1, &bA2, &bZ1, &bZ2, &omCe }) v->assign ((size_t) K, 0.0);
        ce.assign ((size_t) K, 0.0);
        ef.assign ((size_t) K, 0.0);
        for (int k = 0; k < K; ++k)
        {
            const auto c = rbjBandpass0dB (fs, fb[(size_t) k], qb);
            bB0[(size_t) k] = c.b0; bB1[(size_t) k] = c.b1; bB2[(size_t) k] = c.b2; bA1[(size_t) k] = c.a1; bA2[(size_t) k] = c.a2;
            ce[(size_t) k] = std::exp (-1.0 / (std::max (0.002, 2.0 / fb[(size_t) k]) * fs));
            omCe[(size_t) k] = 1.0 - ce[(size_t) k];
        }
        double lo, hi;
        zoneLoHi (forme, f0, q, fs, 1.5, lo, hi);
        ctx.clear();
        for (int k = 0; k < K; ++k)
            if (fb[(size_t) k] >= lo && fb[(size_t) k] <= hi) ctx.push_back (k);
        if (ctx.size() < 3)                                  // les 3 bandes les plus proches de f0 (ordre stable)
        {
            std::vector<int> id ((size_t) K);
            for (int k = 0; k < K; ++k) id[(size_t) k] = k;
            std::stable_sort (id.begin(), id.end(), [&] (int a, int b) { return std::abs (std::log2 (fb[(size_t) a] / f0)) < std::abs (std::log2 (fb[(size_t) b] / f0)); });
            ctx.assign (id.begin(), id.begin() + std::min (3, K));
            std::sort (ctx.begin(), ctx.end());
        }
        g0 = (int) (std::lower_bound (fb.begin(), fb.end(), 60.0) - fb.begin());
        const double tf = std::clamp (3.0 / f0, 0.005, 0.03);
        lag = std::max (2, (int) std::nearbyint (tf * fs / dec));
        Lc.assign ((size_t) K, 0.0);
        Hbuf.assign ((size_t) lag * (size_t) K, 0.0);
        // NLMS
        const double te = std::clamp (2.0 / f0, 0.002, 0.01);
        cef = std::exp (-1.0 / (te * fs));
        ces = std::exp (-1.0 / (0.05 * fs));
        // seuil, tenue, attaque
        m0 = (10.0 - 9.0 * sens) * (1.0 / 2.35);
        P = 99.0 - 12.0 * sens;
        R = (int) std::nearbyint (2.0 * fs / (double) (dec * pasAnneau));
        anneau.assign ((size_t) R, 0.0);
        tri.assign ((size_t) R, 0.0);
        const double tr = (timeMs > 0.0 ? timeMs : 30.0) / 1000.0 / 3.0;
        cRel = std::exp (-(double) dec / (tr * fs));
        const double attPeriods = std::clamp (0.45 + 0.35 * std::log2 (f0 / 60.0) / std::log2 (250.0 / 60.0), 0.45, 0.8);
        cAtt = std::exp (-1.0 / (std::max (attPeriods / f0, 1.0 / fs) * fs));
        bd.assign ((size_t) lookahead, 0.0);
        reset();
    }

    void setGain (double gainDb) { A = std::pow (10.0, gainDb / 20.0); }        // en direct, sans réinitialiser

    void reset()
    {
        band.reset();
        std::fill (bZ1.begin(), bZ1.end(), 0.0);
        std::fill (bZ2.begin(), bZ2.end(), 0.0);
        std::fill (ef.begin(), ef.end(), 0.0);
        std::fill (w, w + ordre, 0.0);
        std::fill (buf, buf + ordre, 0.0);
        zef = zes = zAtt = yH = 0.0;
        hInit = false; hPos = 0;
        nAnneau = 0; posAnneau = 0; pousses = 0; qhold = 0.0; fc = 0; cnt = 0;
        std::fill (bd.begin(), bd.end(), 0.0);
        bdPos = 0;
    }

    inline double process (double x, double* gOut = nullptr)
    {
        double b;
        const double Tl = detect (x, b);
        return apply (x, b, Tl, gOut);
    }

    // Détection : renvoie le poids « transitoire » lissé Tl (avant le choix transitoires / sustain) et le signal de la zone b RETARDÉ de `lookahead` ; la liaison stéréo agit sur Tl.
    inline double detect (double x, double& bOut)
    {
        const double b = band.process (x);
        {   // banc de K biquads en tableaux separes (meme arithmetique que Biquad::process, forme transposee II) : la boucle se vectorise
            double* z1 = bZ1.data(); double* z2 = bZ2.data(); double* pef = ef.data();
            const double *b0 = bB0.data(), *b1 = bB1.data(), *b2 = bB2.data(), *a1 = bA1.data(), *a2 = bA2.data(), *pce = ce.data(), *poc = omCe.data();
            for (int k = 0; k < K; ++k)
            {
                const double y = b0[k] * x + z1[k];
                z1[k] = b1[k] * x - a1[k] * y + z2[k];
                z2[k] = b2[k] * x - a2[k] * y;
                pef[k] = poc[k] * std::abs (y) + pce[k] * pef[k];
            }
        }
        // prédicteur NLMS du signal de zone
        double pred = 0.0, bb = 0.0;
        for (int i = 0; i < ordre; ++i) { pred += w[i] * buf[i]; bb += buf[i] * buf[i]; }
        const double err = b - pred, mu = muNlms / (bb + 1e-9) * err;
        for (int i = 0; i < ordre; ++i) w[i] += mu * buf[i];
        for (int i = ordre - 1; i > 0; --i) buf[i] = buf[i - 1];
        buf[0] = b;
        zef = (1.0 - cef) * std::abs (err) + cef * zef;
        zes = (1.0 - ces) * std::abs (err) + ces * zes;
        if (cnt % dec == 0) trame();
        ++cnt;
        zAtt = (1.0 - cAtt) * yH + cAtt * zAtt;                // attaque du gain bornée
        bOut = bd[(size_t) bdPos];                              // b retardé de `lookahead`
        bd[(size_t) bdPos] = b;
        bdPos = (bdPos + 1 == lookahead) ? 0 : bdPos + 1;
        return zAtt;
    }

    inline double apply (double x, double b, double Tl, double* gOut = nullptr) const
    {
        const double poids = cible == Cible::Transitoires ? Tl : 1.0 - Tl;
        const double g = 1.0 + (A - 1.0) * poids;
        if (gOut) *gOut = g;
        return x + (g - 1.0) * b;
    }

private:
    static constexpr int dec = 16, perOct = 3, ordre = 16, pasAnneau = 4, recalc = 16;
    static constexpr double muNlms = 0.2, largeur = 2.0;

    static void zoneLoHi (Forme forme, double f0, double q, double fs, double ctxOct, double& lo, double& hi)
    {
        if (forme == Forme::Cloche)
        {
            const double sq3 = std::sqrt (3.0) / q, demi = std::log2 ((sq3 + std::sqrt (sq3 * sq3 + 4.0)) / 2.0);
            lo = f0 / std::pow (2.0, demi + ctxOct);
            hi = f0 * std::pow (2.0, demi + ctxOct);
        }
        else if (forme == Forme::ShelfAigu) { lo = f0 / std::pow (2.0, ctxOct); hi = 0.45 * fs; }
        else { lo = 25.0; hi = f0 * std::pow (2.0, ctxOct); }
        lo = std::max (lo, 20.0);
        hi = std::min (hi, 0.45 * fs);
    }

    // Une trame décimée (tous les 16 échantillons) : niveaux des bandes → force B ; veto tonal C ; D ; seuil adaptatif ; poids tenu.
    void trame()
    {
        for (int k = 0; k < K; ++k) Lc[(size_t) k] = 20.0 * std::log10 (ef[(size_t) k] * (kPi / 2.0) + 1e-12);
        const double sC = 20.0 * std::log10 ((zef + 1e-12) / (zes + 1e-12)) * std::clamp ((20.0 * std::log10 (zef * (kPi / 2.0) + 1e-12) + 95.0) / 10.0, 0.0, 1.0);
        if (! hInit)
        {
            for (int j = 0; j < lag; ++j) std::copy (Lc.begin(), Lc.end(), Hbuf.begin() + (size_t) j * (size_t) K);
            hInit = true; hPos = 0;
        }
        const double* ref = &Hbuf[(size_t) hPos * (size_t) K];
        auto up = [&] (int k)
        {
            const double a = ref[k], l = ref[std::max (k - 1, 0)], r = ref[std::min (k + 1, K - 1)];
            return std::max (Lc[(size_t) k] - std::max (a, std::max (l, r)), 0.0);
        };
        double sc = 0.0, mx = -1e300;
        for (int k : ctx) { sc += up (k); mx = std::max (mx, Lc[(size_t) k]); }
        sc /= (double) ctx.size();
        double sg = 0.0;
        for (int k = g0; k < K; ++k) sg += up (k);
        sg /= (double) (K - g0);
        const double sB = std::max (sc, sg) * std::clamp ((mx + 95.0) / 10.0, 0.0, 1.0);
        std::copy (Lc.begin(), Lc.end(), Hbuf.begin() + (size_t) hPos * (size_t) K);     // remplace la plus ancienne
        hPos = (hPos + 1 == lag) ? 0 : hPos + 1;
        const double sD = std::sqrt (std::max (sB, 0.0) * std::max (sC, 0.0) / 3.0);
        if (fc % pasAnneau == 0)
        {
            anneau[(size_t) posAnneau] = sD;
            posAnneau = (posAnneau + 1 == R) ? 0 : posAnneau + 1;
            nAnneau = std::min (nAnneau + 1, R);
            if (pousses % recalc == 0)
            {
                std::copy (anneau.begin(), anneau.begin() + nAnneau, tri.begin());       // l'ordre n'a pas d'importance pour un quantile
                const int idx = std::min (nAnneau - 1, (int) ((double) nAnneau * P / 100.0));
                std::nth_element (tri.begin(), tri.begin() + idx, tri.begin() + nAnneau);
                qhold = tri[(size_t) idx];
            }
            ++pousses;
        }
        ++fc;
        const double T = std::clamp ((sD - std::max (m0, qhold)) / largeur, 0.0, 1.0);
        yH = std::max (T, cRel * yH);
    }

    Biquad band;
    Cible cible = Cible::Transitoires;
    std::vector<double> bB0, bB1, bB2, bA1, bA2, bZ1, bZ2, omCe;      // banc d'analyse en tableaux separes (SoA)
    std::vector<double> fb, ce, ef, Lc, Hbuf, anneau, tri, bd;
    std::vector<int> ctx;
    int K = 0, g0 = 0, lag = 2, R = 1, hPos = 0, nAnneau = 0, posAnneau = 0, pousses = 0, bdPos = 0;
    long long fc = 0, cnt = 0;
    bool hInit = false;
    double A = 1, cef = 0, ces = 0, cAtt = 0, cRel = 0, m0 = 1, P = 90, qhold = 0, zef = 0, zes = 0, zAtt = 0, yH = 0;
    double w[ordre] = {}, buf[ordre] = {};
};
}
