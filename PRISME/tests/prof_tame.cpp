#include "../Source/Dsp/Tame.h"
#include <chrono>
#include <iostream>
using namespace prisme;
int main()
{
    Tame t; t.prepare (48000, Forme::Cloche, 3000, 0.7, -9, 0.5);
    std::vector<double> x (48000 * 20);
    unsigned s = 1; for (double& v : x) { s = s * 1664525u + 1013904223u; v = ((s >> 8) / 8388608.0 - 1.0) * 0.1; }
    double ta = 0, t1 = 0, t2 = 0, ts = 0, acc = 0;
    using C = std::chrono::steady_clock;
    for (size_t i = 0; i < x.size(); ++i)
    {
        auto a0 = C::now(); t.analyse (x[i]); auto a1 = C::now(); ta += std::chrono::duration<double> (a1 - a0).count();
        if (t.isPoint())
        {
            auto b0 = C::now(); t.stage1(); auto b1 = C::now(); t.stage2(); auto b2 = C::now();
            t1 += std::chrono::duration<double> (b1 - b0).count(); t2 += std::chrono::duration<double> (b2 - b1).count();
        }
        auto c0 = C::now(); acc += t.synth (x[i]); auto c1 = C::now(); ts += std::chrono::duration<double> (c1 - c0).count();
    }
    std::cout << "N=" << t.bandCount() << "  analyse " << ta / 20 * 100 << " %  stage1 " << t1 / 20 * 100 << " %  stage2 " << t2 / 20 * 100 << " %  synth " << ts / 20 * 100 << " % (inclut ~overhead chrono) " << acc * 0 << "\n";
}
