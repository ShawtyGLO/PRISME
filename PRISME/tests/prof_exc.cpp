#include "../Source/Dsp/ExciterV3.h"
#include <chrono>
#include <iostream>
#include <vector>
using namespace prisme; using C = std::chrono::steady_clock;
template <class F> static double ms (F&& f, double secs) { auto t0 = C::now(); f(); return std::chrono::duration<double> (C::now() - t0).count() / secs * 100.0; }
int main()
{
    const double fs = 48000; const size_t n = (size_t) fs * 20; const double secs = 20;
    std::vector<double> x (n); unsigned s = 1; for (auto& v : x) { s = s * 1664525u + 1013904223u; v = ((s >> 8) / 8388608.0 - 1.0) * 0.1; }
    double acc = 0;
    for (auto pr : { ProfilExc::Doux, ProfilExc::Chaud, ProfilExc::Mordant, ProfilExc::MordantChaud })
    { ExciterV3 e; e.prepare (fs, Forme::Cloche, 3000, 1.0, 5, pr, 2.5, 0.0, 0.0);
      std::cout << "profil " << (int) pr << " : " << ms ([&] { for (double v : x) acc += e.process (v); }, secs) << " %\n"; }
    // composants isoles : 2 FIR (41+21 MAC) sur historiques circulaires
    Historique<21> hU; Historique<41> hY;
    std::cout << "FIR seuls (hUp 21+20, h0 41 x1 par ech.) : " << ms ([&] { for (double v : x) { hU.push (v); double v0 = 0, v1 = 0; for (int i = 0; i < 21; ++i) v0 += tables::hUp[2*i] * hU.at (i); for (int i = 0; i < 20; ++i) v1 += tables::hUp[2*i+1] * hU.at (i); hY.push (v0); double y = 0; for (int i = 0; i < 41; ++i) y += tables::h0[i] * hY.at (i); hY.push (v1); acc += y; } }, secs) << " %\n";
    std::cout << "ClassA f+F (ADAA MordantChaud, x2)       : " << ms ([&] { double x1 = 0; for (double v : x) { const double u = v * 25 + 0.25; const double d = u - x1; acc += std::abs (d) < 1e-6 ? courbes::f (ModeSat::ClassA, u) : (courbes::F (ModeSat::ClassA, u) - courbes::F (ModeSat::ClassA, x1)) / d; x1 = u; const double u2 = -v * 25 + 0.25; const double d2 = u2 - x1; acc += std::abs (d2) < 1e-6 ? courbes::f (ModeSat::ClassA, u2) : (courbes::F (ModeSat::ClassA, u2) - courbes::F (ModeSat::ClassA, x1)) / d2; x1 = u2; } }, secs) << " %\n";
    std::cout << acc * 0 << "\n";
}
