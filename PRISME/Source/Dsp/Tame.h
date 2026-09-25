// PRISME — type de bande « Tame » v3 (port de _proto/prisme_tame.py) : atténue (gain −) ou accentue (gain +) les résonances de la zone.
//   analyse 24 bandes/octave (Q 14) → niveaux → excès sur les voisines → réduction bornée, plateau, normalisation locale
//   → synthèse par bandes simples (Q 20) ; détection ET gains décimés à fs/16 (le coefficient c = (g−1)/S monte linéairement d'une cible à la suivante) ; causal, latence propre nulle, état conservé entre blocs.
//
// ⚠️ Fidélité au prototype : le prototype Python fait la chaîne spectrale (niveaux, filtres, plateau, seuil) en float32 ; ce port en
// reproduit les arrondis (type `float` aux mêmes endroits, sommation de scipy.ndimage.uniform_filter1d) pour que les décisions à seuil
// (bande active ou non) tombent au même instant. Ne pas « simplifier » ces `float`.
//
// Coût : une allocation dans prepare() (pas dans process()), aucune dépendance JUCE.
#pragma once
#include "Biquad.h"
#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstring>
#include <vector>

#if defined(_MSC_VER)
 #pragma fp_contract (off)
#endif

namespace prisme
{
class Tame
{
public:
    static constexpr int RA = 24, JK = 18, DEC = 16;
    static constexpr double QA = 14.0, QS = 20.0, threshDb = 4.5, ctx = 1.0;

    void prepare (double fs_, Forme forme, double f0, double q, double gainDb, double width)
    {
        fs = fs_;
        sign = gainDb > 0 ? 1.0 : -1.0;
        depth = std::abs (gainDb);
        buildGrid (forme, f0, q);
        N = (int) f.size();
        // pondération de la zone : |H(f_k)| ; bandes actives : w ≥ 0.02
        const auto zc = zoneFilter (forme, fs, f0, q);
        w.assign ((size_t) N, 0.0);
        for (int k = 0; k < N; ++k) w[(size_t) k] = std::abs (response (zc, 2.0 * kPi * f[(size_t) k] / fs));
        act.clear();
        for (int k = 0; k < N; ++k) if (w[(size_t) k] >= 0.02) act.push_back (k);
        ratio = (float) std::clamp (depth / 4.5, 1.0, 3.0);
        seuil = (float) (threshDb - 1.0 * (1.0 - width));
        const double p = 0.08 + 0.42 * std::pow (1.0 - width, 1.5);
        nP = (int) std::nearbyint (RA * p);
        const double sm = width >= 0.999 ? 0.0 : 0.6 * p;
        sizeSm = std::max (3, 2 * (int) std::nearbyint (RA * sm) + 1);
        sizeO = 2 * (int) std::nearbyint (RA * (0.5 + (1.0 - width))) + 1;
        sizeI = 2 * (int) std::nearbyint (RA * (p + 0.05)) + 1;
        sizeO = std::max (sizeO, sizeI + 2);
        sizeS = std::max (3, 2 * (nP / 2) + 1);
        // filtres d'analyse (toutes les bandes) et de synthèse (bandes actives)
        for (auto* v : { &aB0, &aB1, &aB2, &aA1, &aA2, &aZ1, &aZ2, &aOmCf, &aOmCs }) v->assign ((size_t) N, 0.0);
        for (int k = 0; k < N; ++k)
        {
            const auto c = rbjBandpass0dB (fs, f[(size_t) k], QA);
            aB0[(size_t) k] = c.b0; aB1[(size_t) k] = c.b1; aB2[(size_t) k] = c.b2; aA1[(size_t) k] = c.a1; aA2[(size_t) k] = c.a2;
        }
        for (auto* v : { &sB0, &sB1, &sB2, &sA1, &sA2, &sZ1, &sZ2, &term, &cPrev, &cCur }) v->assign (act.size(), 0.0);
        for (size_t j = 0; j < act.size(); ++j)
        {
            const auto c = rbjBandpass0dB (fs, f[(size_t) act[j]], QS);
            sB0[j] = c.b0; sB1[j] = c.b1; sB2[j] = c.b2; sA1[j] = c.a1; sA2[j] = c.a2;
        }
        cf.resize ((size_t) N); cse.resize ((size_t) N);
        for (int k = 0; k < N; ++k)
        {
            const double fk = f[(size_t) k];
            const double tf = std::max ({ 0.004, 3.0 / fk, QA / (kPi * fk) });
            const double ts = std::max (0.10, 10.0 / fk);
            cf[(size_t) k] = std::exp (-1.0 / (tf * fs));
            cse[(size_t) k] = std::exp (-1.0 / (ts * fs));
            aOmCf[(size_t) k] = 1.0 - cf[(size_t) k];
            aOmCs[(size_t) k] = 1.0 - cse[(size_t) k];
        }
        cAtt = std::exp (-(double) DEC / (0.004 * fs));
        cRel = std::exp (-(double) DEC / (0.08 * fs));
                // noyau de normalisation K[m] = Re H_{fc[m]}(3 kHz), arrondi en float32 comme le prototype
        K.assign (2 * JK + 1, 0.0);
        const double pts = 2.0 * kPi * 3000.0 / fs;
        for (int m = -JK; m <= JK; ++m)
            K[(size_t) (m + JK)] = (double) (float) response (rbjBandpass0dB (fs, 3000.0 * std::pow (2.0, (double) m / RA), QS), pts).real();
        for (auto* v : { &Lf, &Lp, &Ls, &mo, &mi, &refv, &epv, &redf, &redm, &redu, &tmpf }) v->assign ((size_t) N, 0.0f);
        for (auto* v : { &redD, &SD, &lastRed, &lastS, &ef, &es, &zra, &zrr }) v->assign ((size_t) N, 0.0);
        line.assign ((size_t) N + 400, 0.0);
        reset();
    }

    void reset()
    {
        for (auto* v : { &aZ1, &aZ2, &sZ1, &sZ2 }) std::fill (v->begin(), v->end(), 0.0);
        for (auto* v : { &ef, &es, &zra, &zrr }) std::fill (v->begin(), v->end(), 0.0);
        std::fill (lastRed.begin(), lastRed.end(), 0.0);
        std::fill (lastS.begin(), lastS.end(), 1.0);
        std::fill (cPrev.begin(), cPrev.end(), 0.0);
        std::fill (cCur.begin(), cCur.end(), 0.0);
        count = 0;
    }

    inline double process (double x)
    {
        const bool point = (count % DEC) == 0;
        const int n = N;
        double* z1 = aZ1.data(); double* z2 = aZ2.data(); double* pef = ef.data(); double* pes = es.data();
        const double *b0 = aB0.data(), *b1 = aB1.data(), *b2 = aB2.data(), *a1 = aA1.data(), *a2 = aA2.data();
        const double *pcf = cf.data(), *pcs = cse.data(), *ocf = aOmCf.data(), *ocs = aOmCs.data();
        for (int k = 0; k < n; ++k)                            // analyse : N biquads indépendants + 2 enveloppes (sans dépendance entre bandes)
        {
            const double yk = b0[k] * x + z1[k];
            z1[k] = b1[k] * x - a1[k] * yk + z2[k];
            z2[k] = b2[k] * x - a2[k] * yk;
            const double ab = std::abs (yk);
            pef[k] = ocf[k] * ab + pcf[k] * pef[k];
            pes[k] = ocs[k] * ab + pcs[k] * pes[k];
        }
        if (point) decimatedStep();
        const int na = (int) act.size();
        double *cp = cPrev.data(), *cc = cCur.data(), *tm = term.data(), *sz1 = sZ1.data(), *sz2 = sZ2.data();
        const double *sb0 = sB0.data(), *sb1 = sB1.data(), *sb2 = sB2.data(), *sa1 = sA1.data(), *sa2 = sA2.data();
        if (point)                                            // nouvelle cible c = (g − 1)/S aux points décimés seulement : exp et division 1 fois sur 16
        {
            const double kExp = sign * 0.11512925464970229;   // ln(10)/20
            for (int j = 0; j < na; ++j)
            {
                const size_t k = (size_t) act[(size_t) j];
                cp[j] = cc[j];
                cc[j] = (expFast (kExp * redD[k]) - 1.0) / SD[k];
            }
        }
        const double ph = (double) (count % DEC) / (double) DEC;      // rampe linéaire de l'ancienne cible vers la nouvelle (retard 16 échantillons, causal)
        const double omph = 1.0 - ph;
        for (int j = 0; j < na; ++j)
        {
            const double bs = sb0[j] * x + sz1[j];
            sz1[j] = sb1[j] * x - sa1[j] * bs + sz2[j];
            sz2[j] = sb2[j] * x - sa2[j] * bs;
            tm[j] = (cp[j] * omph + cc[j] * ph) * bs;
        }
        double y = x;
        for (int j = 0; j < na; ++j) y += tm[j];
        ++count;
        return y;
    }

private:
    // exp(x) pour |x| ≤ ~4, sans branche : n = round(x/ln2) par l'astuce du nombre magique, Taylor de degré 12 sur |r| ≤ 0,35 (erreur < 1e-15), ×2^n
    // par construction directe de l'exposant. Environ 3× plus rapide que std::exp ; identique à 1e-15 près.
    static inline double expFast (double x)
    {
        constexpr double magic = 6755399441055744.0;            // 1,5 · 2^52
        double t = x * 1.4426950408889634 + magic;
        std::int64_t bits;
        std::memcpy (&bits, &t, sizeof bits);
        const std::int64_t n = (std::int32_t) (bits & 0xffffffff);          // entier arrondi (complément à deux dans les bits bas)
        const double nD = t - magic;
        const double r = x - nD * 0.6931471805599453;
        double p = 1.0 / 479001600.0;                            // 1/12!
        p = p * r + 1.0 / 39916800.0;
        p = p * r + 1.0 / 3628800.0;
        p = p * r + 1.0 / 362880.0;
        p = p * r + 1.0 / 40320.0;
        p = p * r + 1.0 / 5040.0;
        p = p * r + 1.0 / 720.0;
        p = p * r + 1.0 / 120.0;
        p = p * r + 1.0 / 24.0;
        p = p * r + 1.0 / 6.0;
        p = p * r + 0.5;
        p = p * r + 1.0;
        p = p * r + 1.0;
        const std::int64_t e = (n + 1023) << 52;
        double scale;
        std::memcpy (&scale, &e, sizeof scale);
        return p * scale;
    }

    static std::complex<double> response (const BiquadCoefs& c, double w0)          // H(e^{jw}) comme scipy.signal.freqz
    {
        const std::complex<double> zm1 = std::polar (1.0, -w0), zm2 = zm1 * zm1;
        return (c.b0 + c.b1 * zm1 + c.b2 * zm2) / (1.0 + c.a1 * zm1 + c.a2 * zm2);
    }

    void buildGrid (Forme forme, double f0, double q)
    {
        double lo, hi;
        if (forme == Forme::Cloche)
        {
            const double sq3 = std::sqrt (3.0) / q, demi = std::log2 ((sq3 + std::sqrt (sq3 * sq3 + 4.0)) / 2.0);
            lo = f0 / std::pow (2.0, demi + ctx);
            hi = f0 * std::pow (2.0, demi + ctx);
        }
        else if (forme == Forme::ShelfAigu) { lo = f0 / std::pow (2.0, ctx); hi = 0.45 * fs; }
        else                                { lo = 25.0; hi = f0 * std::pow (2.0, ctx); }
        lo = std::max (lo, 20.0);
        hi = std::min (hi, 0.45 * fs);
        const int n = std::max ((int) std::ceil (std::log2 (hi / lo) * RA) + 1, 8);
        f.clear();
        for (int i = 0; i < n; ++i)
        {
            const double fk = lo * std::pow (2.0, (double) i / RA);
            if (fk < 0.45 * fs) f.push_back (fk);
        }
    }

    // scipy.ndimage.maximum_filter1d, mode='nearest', fenêtre centrée impaire
    void maxFilter (const std::vector<float>& in, std::vector<float>& out, int size) const
    {
        const int h = size / 2;
        for (int k = 0; k < N; ++k)
        {
            float m = in[(size_t) std::clamp (k - h, 0, N - 1)];
            for (int d = -h + 1; d <= h; ++d) m = std::max (m, in[(size_t) std::clamp (k + d, 0, N - 1)]);
            out[(size_t) k] = m;
        }
    }

    // scipy.ndimage.uniform_filter1d, mode='nearest' : somme glissante en double, sortie arrondie en float32
    void uniformFilter (const std::vector<float>& in, std::vector<float>& out, int size)
    {
        const int size1 = size / 2, size2 = size - size1 - 1;
        double* l = line.data();
        for (int i = 0; i < size1; ++i) l[i] = in[0];
        for (int i = 0; i < N; ++i) l[size1 + i] = in[(size_t) i];
        for (int i = 0; i < size2; ++i) l[size1 + N + i] = in[(size_t) N - 1];
        double tmp = 0.0;
        for (int i = 0; i < size; ++i) tmp += l[i];
        tmp /= (double) size;
        out[0] = (float) tmp;
        for (int i = 1; i < N; ++i)
        {
            tmp += (l[i + size - 1] - l[i - 1]) / (double) size;
            out[(size_t) i] = (float) tmp;
        }
    }

    void decimatedStep()
    {
        for (int k = 0; k < N; ++k)
            Lf[(size_t) k] = (float) (20.0 * std::log10 (std::max (es[(size_t) k], 0.5 * ef[(size_t) k]) * (kPi / 2.0) + 1e-12));
        maxFilter (Lf, Lp, 3);
        uniformFilter (Lp, Ls, sizeSm);
        uniformFilter (Ls, mo, sizeO);
        uniformFilter (Ls, mi, sizeI);
        const float fo = (float) sizeO, fi = (float) sizeI, fd = (float) (sizeO - sizeI);
        for (int k = 0; k < N; ++k)
        {
            const size_t i = (size_t) k;
            const float a = mo[i] * fo, b = mi[i] * fi, num = a - b;
            refv[i] = num / fd;
            const float e = (Ls[i] - refv[i]) - seuil;
            float ep;
            if (e >= 1.0f) ep = e;
            else if (e <= -1.0f) ep = 0.0f;
            else { const float u = e + 1.0f; ep = 0.25f * (u * u); }
            const float gate = std::clamp ((Lp[i] + 95.0f) / 10.0f, 0.0f, 1.0f);
            const float r = (ratio * ep) * gate;
            redf[i] = std::min (r, (float) depth);
        }
        maxFilter (redf, redm, 2 * nP + 1);                       // plateau
        uniformFilter (redm, redu, sizeS);
        for (int k = 0; k < N; ++k) redu[(size_t) k] = (float) ((double) redu[(size_t) k] * w[(size_t) k]);
        // lissage temporel attaque / relâchement à cadence décimée, puis normalisation locale
        for (int k = 0; k < N; ++k)
        {
            const size_t i = (size_t) k;
            const double x = (double) redu[i];
            const double ra = (1.0 - cAtt) * x + cAtt * zra[i];
            const double rr = (1.0 - cRel) * x + cRel * zrr[i];
            zra[i] = ra; zrr[i] = rr;
            redD[i] = std::max (ra, rr);
            tmpf[i] = redD[i] > 0.25 ? 1.0f : 0.0f;
        }
        for (int k = 0; k < N; ++k)
        {
            double s = 0.0;
            for (int d = -JK; d <= JK; ++d)
            {
                const int j = k - d;
                if (j >= 0 && j < N) s += K[(size_t) (JK + d)] * (double) tmpf[(size_t) j];
            }
            SD[(size_t) k] = std::max ((double) (float) s, 1.0);
        }
        lastRed = redD;
        lastS = SD;
    }

    double fs = 48000, sign = -1, depth = 9, cAtt = 0, cRel = 0;
    float ratio = 1, seuil = 4.5f;
    int N = 0, nP = 0, sizeSm = 3, sizeO = 3, sizeI = 3, sizeS = 3;
    long count = 0;
    std::vector<double> f, w, K, cf, cse, ef, es, zra, zrr, redD, SD, lastRed, lastS, cPrev, cCur, line;
    std::vector<int> act;
    std::vector<double> aB0, aB1, aB2, aA1, aA2, aZ1, aZ2, aOmCf, aOmCs;          // analyse : N biquads + enveloppes (tableaux séparés → vectorisable)
    std::vector<double> sB0, sB1, sB2, sA1, sA2, sZ1, sZ2, term;                    // synthèse : bandes actives
    std::vector<float> Lf, Lp, Ls, mo, mi, refv, epv, redf, redm, redu, tmpf;
};
}
