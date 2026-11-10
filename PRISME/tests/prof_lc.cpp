#include <cmath>
#include <chrono>
#include <iostream>
#include <vector>
using C = std::chrono::steady_clock;
// logcosh(u) = |u| + log1p(exp(-2|u|)) - ln2.  Variante exacte en flottant ? On mesure l'ecart max sur une grille dense + le cout.
static double lc0 (double u) { const double a = std::abs (u); return a + std::log1p (std::exp (-2.0 * a)) - 0.69314718055994530942; }
static double lc1 (double u) { const double a = std::abs (u); const double e = std::exp (-2.0 * a); return a + std::log1p (e) - 0.69314718055994530942; }   // identique (test du compilateur)
static double lc2 (double u) { return std::log (std::cosh (u)); }                                                  // forme naive (deborde pour |u| > 710)
int main()
{
    double e1 = 0, e2 = 0; size_t n = 0;
    for (double u = -40; u <= 40; u += 1e-4) { const double r = lc0 (u); e1 = std::max (e1, std::abs (lc1 (u) - r)); e2 = std::max (e2, std::abs (lc2 (u) - r)); ++n; }
    std::cout << "ecart abs max : lc1 " << e1 << "  lc2 (log cosh) " << e2 << "\n";
    std::vector<double> x (48000 * 20); unsigned s = 1; for (auto& v : x) { s = s * 1664525u + 1013904223u; v = ((s >> 8) / 8388608.0 - 1.0) * 3.0; }
    double acc = 0; auto t = [&] (auto f) { auto t0 = C::now(); for (double v : x) acc += f (v); return std::chrono::duration<double> (C::now() - t0).count() / 20 * 100; };
    std::cout << "cout par appel : lc0 " << t (lc0) << " %  lc2 " << t (lc2) << " %  tanh " << t ([] (double u) { return std::tanh (u); }) << " %\n" << acc * 0 << "\n";
}
