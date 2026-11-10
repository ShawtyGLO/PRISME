"""Optimisation CPU 1 (2026-11-09), SANS changement de son : (a) Tame::maxFilter en O(N) (van Herk / Gil-Werman : max exact, aucun arrondi) ; (b) Shape : banc de biquads en tableaux separes (SoA, vectorisable), meme arithmetique."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")
def edit(path, pairs):
    p = os.path.join(SRC, path); s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:80]); s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)

# ---- (a) Tame : maxFilter O(N)
edit("Dsp/Tame.h", [(
'''    void maxFilter (const std::vector<float>& in, std::vector<float>& out, int size) const
    {
        const int h = size / 2;
        for (int k = 0; k < N; ++k)
        {
            float m = in[(size_t) std::clamp (k - h, 0, N - 1)];
            for (int d = -h + 1; d <= h; ++d) m = std::max (m, in[(size_t) std::clamp (k + d, 0, N - 1)]);
            out[(size_t) k] = m;
        }
    }''',
'''    // Fenetre glissante centree (mode 'nearest') en O(N) par l'algorithme de van Herk / Gil-Werman : prefixe et suffixe de max par blocs de `size`.
    // Resultat identique a la version naive (le max de flottants n'arrondit pas). Le signal est etendu de h valeurs a chaque bord (= 'nearest').
    void maxFilter (const std::vector<float>& in, std::vector<float>& out, int size)
    {
        const int h = size / 2, M = N + 2 * h;
        float* e = vhExt.data(); float* g = vhG.data(); float* d = vhD.data();
        for (int i = 0; i < M; ++i) e[i] = in[(size_t) std::clamp (i - h, 0, N - 1)];
        for (int i = 0; i < M; ++i) g[i] = (i % size == 0) ? e[i] : std::max (g[i - 1], e[i]);
        for (int i = M - 1; i >= 0; --i) d[i] = (i == M - 1 || (i + 1) % size == 0) ? e[i] : std::max (d[i + 1], e[i]);
        for (int k = 0; k < N; ++k)                                     // fenetre [k, k + size - 1] dans e  (= [k - h, k + h] dans in)
            out[(size_t) k] = std::max (d[k], g[k + size - 1]);
    }'''),
("        line.assign ((size_t) N + 400, 0.0);", "        line.assign ((size_t) N + 400, 0.0);\n        for (auto* v : { &vhExt, &vhG, &vhD }) v->assign ((size_t) N + 2 * (2 * RA + 4), 0.0f);      // tampons du maxFilter O(N) (taille max : 2*nP+3 <= 2*RA+3)"),
("    std::vector<float> Lf, Lp, Ls, mo, mi, refv, epv, redf, redm, redu, tmpf;", "    std::vector<float> Lf, Lp, Ls, mo, mi, refv, epv, redf, redm, redu, tmpf, vhExt, vhG, vhD;"),
])

# ---- (b) Shape : banc en SoA
edit("Dsp/Shape.h", [
("        bp.assign ((size_t) K, Biquad());\n        ce.assign ((size_t) K, 0.0);\n        ef.assign ((size_t) K, 0.0);",
 "        for (auto* v : { &bB0, &bB1, &bB2, &bA1, &bA2, &bZ1, &bZ2, &omCe }) v->assign ((size_t) K, 0.0);\n        ce.assign ((size_t) K, 0.0);\n        ef.assign ((size_t) K, 0.0);"),
("            bp[(size_t) k].set (rbjBandpass0dB (fs, fb[(size_t) k], qb));\n            ce[(size_t) k] = std::exp (-1.0 / (std::max (0.002, 2.0 / fb[(size_t) k]) * fs));",
 "            const auto c = rbjBandpass0dB (fs, fb[(size_t) k], qb);\n            bB0[(size_t) k] = c.b0; bB1[(size_t) k] = c.b1; bB2[(size_t) k] = c.b2; bA1[(size_t) k] = c.a1; bA2[(size_t) k] = c.a2;\n            ce[(size_t) k] = std::exp (-1.0 / (std::max (0.002, 2.0 / fb[(size_t) k]) * fs));\n            omCe[(size_t) k] = 1.0 - ce[(size_t) k];"),
("        for (auto& b : bp) b.reset();", "        std::fill (bZ1.begin(), bZ1.end(), 0.0);\n        std::fill (bZ2.begin(), bZ2.end(), 0.0);"),
('''        for (int k = 0; k < K; ++k)
        {
            const double bk = bp[(size_t) k].process (x);
            ef[(size_t) k] = (1.0 - ce[(size_t) k]) * std::abs (bk) + ce[(size_t) k] * ef[(size_t) k];
        }''',
'''        {   // banc de K biquads en tableaux separes (meme arithmetique que Biquad::process, forme transposee II) : la boucle se vectorise
            double* z1 = bZ1.data(); double* z2 = bZ2.data(); double* pef = ef.data();
            const double *b0 = bB0.data(), *b1 = bB1.data(), *b2 = bB2.data(), *a1 = bA1.data(), *a2 = bA2.data(), *pce = ce.data(), *poc = omCe.data();
            for (int k = 0; k < K; ++k)
            {
                const double y = b0[k] * x + z1[k];
                z1[k] = b1[k] * x - a1[k] * y + z2[k];
                z2[k] = b2[k] * x - a2[k] * y;
                pef[k] = poc[k] * std::abs (y) + pce[k] * pef[k];
            }
        }'''),
("    std::vector<Biquad> bp;", "    std::vector<double> bB0, bB1, bB2, bA1, bA2, bZ1, bZ2, omCe;      // banc d'analyse en tableaux separes (SoA)"),
])
print("ok")
