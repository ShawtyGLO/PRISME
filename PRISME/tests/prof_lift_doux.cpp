#include "../Source/Dsp/ExciterV3.h"
#include "../Source/Dsp/Lift.h"
#include <chrono>
#include <iostream>
#include <vector>
using namespace prisme; using C = std::chrono::steady_clock;
int main()
{
    const double fs = 48000; const size_t n = (size_t) fs * 20;
    std::vector<double> x (n); unsigned s = 1; for (auto& v : x) { s = s * 1664525u + 1013904223u; v = ((s >> 8) / 8388608.0 - 1.0) * 0.1; }
    // Lift : combien coute chaque transcendante par echantillon ?
    double acc = 0; auto a0 = C::now();
    for (double v : x) acc += 20.0 * std::log10 (std::abs (v) + 1e-12);
    const double tLog10 = std::chrono::duration<double> (C::now() - a0).count();
    a0 = C::now(); for (double v : x) acc += std::pow (10.0, v * 0.6);
    const double tPow = std::chrono::duration<double> (C::now() - a0).count();
    a0 = C::now(); for (double v : x) acc += std::exp (v * 1.38);
    const double tExp = std::chrono::duration<double> (C::now() - a0).count();
    a0 = C::now(); for (double v : x) acc += std::log (std::abs (v) + 1e-12);
    const double tLog = std::chrono::duration<double> (C::now() - a0).count();
    const double k = 100.0 / 20.0;
    std::cout << "par appel/echantillon : log10 " << tLog10 * k << " %  log " << tLog * k << " %  pow10 " << tPow * k << " %  exp " << tExp * k << " %\n";
    // Exciter Doux : logcosh = |x| + log1p(exp(-2|x|)) - ln2  vs  variante
    a0 = C::now(); for (double v : x) { const double a = std::abs (v * 3); acc += a + std::log1p (std::exp (-2.0 * a)) - std::log (2.0); }
    const double tLc = std::chrono::duration<double> (C::now() - a0).count();
    a0 = C::now(); for (double v : x) acc += std::tanh (v * 3);
    const double tTanh = std::chrono::duration<double> (C::now() - a0).count();
    std::cout << "Doux : logcosh " << tLc * k << " %  tanh " << tTanh * k << " %  (x2 par sur-echantillonnage)\n";
    // ecart max de la variante logcosh sans le log(2) recalcule (constante)
    double e = 0; const double LN2 = 0.69314718055994530942;
    for (int i = 0; i < 200000; ++i) { const double a = i * 1e-4; const double r1 = a + std::log1p (std::exp (-2.0 * a)) - std::log (2.0), r2 = a + std::log1p (std::exp (-2.0 * a)) - LN2; e = std::max (e, std::abs (r1 - r2)); }
    std::cout << "logcosh : ecart abs max avec ln2 constant : " << e << "\n" << acc * 0 << "\n";
}
