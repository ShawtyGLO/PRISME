"""Port C++ de la détection v4 du Tame (courbe de référence) dans PRISME/Source/Dsp/Tame.h."""
import os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source", "Dsp", "Tame.h")
s = open(P, encoding="utf-8").read()


def sub(old, new):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new, 1)


sub('''        seuil = (float) (threshDb - 1.0 * (1.0 - width));
        const double p = 0.08 + 0.42 * std::pow (1.0 - width, 1.5);''', '''        // v4 : la Largeur ne touche plus au seuil ; finesse 1/12 a 1,4 oct ; marge de coeur 1,5 dB (fin) a ~30 dB (large)
        seuil = (float) threshDb;
        const double p = 0.04 + 0.66 * std::pow (1.0 - width, 1.5);
        marge = (float) (1.5 + 30.0 * (1.0 - width) * (1.0 - width));''')
sub("        line.assign ((size_t) N + 400, 0.0);", '''        line.assign ((size_t) N + 400, 0.0);
        lgc.assign ((size_t) N, 0.0);                             // v4 : abscisse en octaves, centree
        double mlg = 0.0;
        for (int k = 0; k < N; ++k) { lgc[(size_t) k] = std::log2 (f[(size_t) k] / 1000.0); mlg += lgc[(size_t) k]; }
        mlg /= (double) N;
        xx = 0.0;
        for (auto& v : lgc) { v -= mlg; xx += v * v; }
        sizeV4 = 2 * (int) std::nearbyint (RA * 2.0) + 1;          // fenetre de la courbe : +-1 octave
        for (auto* v : { &lt, &Ltd, &detr, &courbe, &diffv }) v->assign ((size_t) N, 0.0);
        tri.assign ((size_t) std::max (sizeV4, N), 0.0);
        cLt = std::exp (-(double) DEC / (3.0 * fs));''')
sub("        count = 0;\n    }", "        count = 0;\n        nLt = 0;\n    }")
i0 = s.index("        uniformFilter (Ls, mo, sizeO);\n        uniformFilter (Ls, mi, sizeI);")
i1 = s.index("        maxFilter (redf, redm, 2 * nP + 1);")
s = s[:i0] + '''        // v4 : courbe de reference = spectre long terme, pente retiree, percentile bas 15 % sur +-1 oct ; plus le decalage de niveau d'ensemble
        ++nLt;
        const double c = ((double) nLt * DEC / fs < 3.0) ? std::max (1.0 - 1.0 / (double) nLt, 0.0) : cLt;
        double mlt = 0.0;
        for (int k = 0; k < N; ++k)
        {
            const size_t i = (size_t) k;
            Ltd[i] = (double) Ls[i];
            lt[i] = nLt == 1 ? Ltd[i] : c * lt[i] + (1.0 - c) * Ltd[i];
            mlt += lt[i];
        }
        mlt /= (double) N;
        double num = 0.0;
        for (int k = 0; k < N; ++k) num += lgc[(size_t) k] * (lt[(size_t) k] - mlt);
        const double pente = num / xx;
        for (int k = 0; k < N; ++k) detr[(size_t) k] = lt[(size_t) k] - lgc[(size_t) k] * pente;
        const int h = sizeV4 / 2, rang = (int) ((double) sizeV4 * 15.0 / 100.0);
        for (int k = 0; k < N; ++k)
        {
            for (int d = -h; d <= h; ++d) tri[(size_t) (d + h)] = detr[(size_t) std::clamp (k + d, 0, N - 1)];
            std::nth_element (tri.begin(), tri.begin() + rang, tri.begin() + sizeV4);
            courbe[(size_t) k] = tri[(size_t) rang] + lgc[(size_t) k] * pente;
            diffv[(size_t) k] = Ltd[(size_t) k] - lt[(size_t) k];
        }
        std::copy (diffv.begin(), diffv.begin() + N, tri.begin());
        const int mid = N / 2;
        std::nth_element (tri.begin(), tri.begin() + mid, tri.begin() + N);
        double decal = tri[(size_t) mid];
        if (N % 2 == 0) decal = 0.5 * (decal + *std::max_element (tri.begin(), tri.begin() + mid));
        for (int k = 0; k < N; ++k)
        {
            const size_t i = (size_t) k;
            const float e = (float) (Ltd[i] - (courbe[i] + decal)) - seuil;
            float ep;
            if (e >= 1.0f) ep = e;
            else if (e <= -1.0f) ep = 0.0f;
            else { const float u = e + 1.0f; ep = 0.25f * (u * u); }
            epv[i] = ep;
        }
        maxFilter (epv, refv, 2 * nP + 3);                       // cime locale : on ne garde que le coeur des exces
        for (int k = 0; k < N; ++k)
        {
            const size_t i = (size_t) k;
            const float ep = epv[i] >= refv[i] - marge ? epv[i] : 0.0f;
            const float gate = std::clamp ((Lp[i] + 95.0f) / 10.0f, 0.0f, 1.0f);
            const float r = (ratio * ep) * gate;
            redf[i] = std::min (r, (float) depth);
        }
''' + s[i1:]
sub("    float ratio = 1, seuil = 4.5f;", "    float ratio = 1, seuil = 4.5f, marge = 1.5f;\n    int sizeV4 = 97, nLt = 0;\n    double xx = 1.0, cLt = 0.0;\n    std::vector<double> lgc, lt, Ltd, detr, courbe, diffv, tri;")
open(P, "w", encoding="utf-8").write(s)
print("ok")
