#include "../Source/Dsp/ExciterV3.h"
#include "../Source/Dsp/Lift.h"
#include "../Source/Dsp/Shape.h"
#include "../Source/Dsp/Tame.h"
#include <chrono>
#include <iostream>
#include <vector>
using namespace prisme;
using C = std::chrono::steady_clock;
static std::vector<double> sig (size_t n, unsigned s, double a) { std::vector<double> x (n); for (auto& v : x) { s = s * 1664525u + 1013904223u; v = ((s >> 8) / 8388608.0 - 1.0) * a; } return x; }
template <class F> static double mesure (F&& f, size_t n, double fs) { auto t0 = C::now(); f(); return std::chrono::duration<double> (C::now() - t0).count() / (n / fs) * 100.0; }
int main()
{
    const double fs = 48000; const size_t n = (size_t) fs * 20;
    auto x = sig (n, 1, 0.1);
    double acc = 0;
    { ExciterV3 e; e.prepare (fs, Forme::Cloche, 3000, 1.0, 5, ProfilExc::MordantChaud, 2.5, 0.0, 0.0);
      std::cout << "Exciter v3 complet   : " << mesure ([&] { for (double v : x) acc += e.process (v); }, n, fs) << " %\n"; }
    { ExciterV3 e; e.prepare (fs, Forme::Cloche, 3000, 1.0, 5, ProfilExc::Doux, 2.5, 0.0, 0.0);
      std::cout << "Exciter v3 Doux(tanh): " << mesure ([&] { for (double v : x) acc += e.process (v); }, n, fs) << " %\n"; }
    { Lift l; l.prepare (fs, Forme::Cloche, 1000, 1.0, 12, 60, 150);
      std::cout << "Lift                 : " << mesure ([&] { for (double v : x) acc += l.process (v); }, n, fs) << " %\n"; }
    { Shape s; s.prepare (fs, Shape::Cible::Transitoires, Forme::Cloche, 200, 0.7, 9, 0.0, 0.85);
      std::cout << "Shape v5             : " << mesure ([&] { for (double v : x) acc += s.process (v); }, n, fs) << " %\n"; }
    { Tame t; t.prepare (fs, Forme::Cloche, 3000, 0.7, -9, 0.5);
      double ta = 0, t1 = 0, t2 = 0, ts = 0;
      for (size_t i = 0; i < n; ++i)
      { auto a0 = C::now(); t.analyse (x[i]); auto a1 = C::now(); ta += std::chrono::duration<double> (a1 - a0).count();
        if (t.isPoint()) { auto b0 = C::now(); t.stage1(); auto b1 = C::now(); t.stage2(); auto b2 = C::now(); t1 += std::chrono::duration<double> (b1 - b0).count(); t2 += std::chrono::duration<double> (b2 - b1).count(); }
        auto c0 = C::now(); acc += t.synth (x[i]); ts += std::chrono::duration<double> (C::now() - c0).count(); }
      const double k = 100.0 / (n / fs);
      std::cout << "Tame N=" << t.bandCount() << " analyse " << ta * k << " % | stage1 " << t1 * k << " % | stage2 " << t2 * k << " % | synth " << ts * k << " % (chrono inclus)\n"; }
    std::cout << (acc * 0) << "\n";
}
