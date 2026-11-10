"""Optimisation CPU 2 (2026-11-09), SANS changement de son : percentile glissant du Tame par fenetre TRIEE maintenue (insertion/suppression a chaque pas) :
meme valeur exacte (le 15e plus petit de la fenetre) que nth_element, en O(size) par position au lieu de O(size log size)."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")
p = os.path.join(SRC, "Dsp", "Tame.h"); s = open(p, encoding="utf-8").read()
a = '''        for (int k = 0; k < N; ++k)
        {
            if (recalc)
            {
                for (int d = -h; d <= h; ++d) tri[(size_t) (d + h)] = detr[(size_t) std::clamp (k + d, 0, N - 1)];
                std::nth_element (tri.begin(), tri.begin() + rang, tri.begin() + sizeV4);
                courbeC[(size_t) k] = tri[(size_t) rang] + lgc[(size_t) k] * pente;
            }
            courbe[(size_t) k]'''
b = '''        if (recalc)                                              // percentile glissant : fenetre triee maintenue (meme resultat exact que nth_element sur chaque fenetre)
        {
            auto src = [&] (int i) { return detr[(size_t) std::clamp (i, 0, N - 1)]; };
            for (int d = -h; d <= h; ++d) tri[(size_t) (d + h)] = src (d);          // fenetre de k = 0
            std::sort (tri.begin(), tri.begin() + sizeV4);
            for (int k = 0; k < N; ++k)
            {
                if (k > 0)
                {
                    const double out = src (k - 1 - h), in = src (k + h);        // sort la valeur la plus ancienne, entre la nouvelle
                    if (out != in)
                    {
                        auto it = std::lower_bound (tri.begin(), tri.begin() + sizeV4, out);
                        std::move (it + 1, tri.begin() + sizeV4, it);              // retire `out` (present : la fenetre est exactement celle de k-1)
                        auto pos = std::lower_bound (tri.begin(), tri.begin() + sizeV4 - 1, in);
                        std::move_backward (pos, tri.begin() + sizeV4 - 1, tri.begin() + sizeV4);
                        *pos = in;
                    }
                }
                courbeC[(size_t) k] = tri[(size_t) rang] + lgc[(size_t) k] * pente;
            }
        }
        for (int k = 0; k < N; ++k)
        {
            courbe[(size_t) k]'''
assert a in s; s = s.replace(a, b, 1); open(p, "w", encoding="utf-8").write(s); print("ok")
