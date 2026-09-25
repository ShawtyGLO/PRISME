#define _CRT_SECURE_NO_WARNINGS
#include "../Source/Dsp/Engine.h"
#include <fstream>
#include <iostream>
using namespace prisme;
int main()
{
    std::ifstream f ("refs/music12.f64", std::ios::binary | std::ios::ate);
    std::vector<double> m ((size_t) f.tellg() / 8);
    f.seekg (0); f.read ((char*) m.data(), m.size() * 8);
    const size_t n = 48000 * 6;
    const ModeSat modes[5] = { ModeSat::Iron, ModeSat::Triode, ModeSat::Diode, ModeSat::ClassA, ModeSat::Rect };
    const char* nom[5] = { "Iron", "Triode", "Diode", "Class-A", "Rect" };
    std::vector<double> d[5];
    for (int k = 0; k < 5; ++k)
    {
        BandeSpec s; s.type = TypeBande::Exciter; s.forme = Forme::Cloche; s.f0 = 3000; s.q = 0.71; s.gainDb = 2.4; s.mode = modes[k]; s.drive = 1.5;
        BandeProc b; b.prepare (48000, s);
        double dl, dr;
        for (size_t i = 0; i < n; ++i) { b.process (m[2 * i], m[2 * i + 1], dl, dr); d[k].push_back (dl); }
    }
    auto rms = [&] (const std::vector<double>& a, const std::vector<double>* b2) { double s = 0; for (size_t i = 48000; i < n; ++i) { const double v = a[i] - (b2 ? (*b2)[i] : 0.0); s += v * v; } return std::sqrt (s / (n - 48000)); };
    for (int a = 0; a < 5; ++a)
    {
        std::cout << nom[a] << " niveau " << 20 * std::log10 (rms (d[a], nullptr)) << " dB | écart relatif aux autres (dB) :";
        for (int c = 0; c < 5; ++c) if (c != a) std::cout << " " << nom[c] << " " << 20 * std::log10 (rms (d[a], &d[c]) / rms (d[a], nullptr));
        std::cout << "\n";
    }
}
