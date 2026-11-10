// Usage intensif : 5 bandes stereo (3 Tame + Shape + Exciter) dans l'Engine complet, 20 s de musique.
#include "../Source/Dsp/Engine.h"
#include <chrono>
#include <fstream>
#include <iostream>
#include <vector>
using namespace prisme;
static std::vector<double> lire (const std::string& p) { std::ifstream f (p, std::ios::binary); std::vector<double> v; if (! f) return v; f.seekg (0, std::ios::end); v.resize ((size_t) f.tellg() / 8); f.seekg (0); f.read ((char*) v.data(), (std::streamsize) v.size() * 8); return v; }
int main()
{
    auto xs = lire ("refs/music12.f64");                  // 12 s stereo entrelacees a fs0
    if (xs.empty()) { std::cout << "pas de music12\n"; return 1; }
    const double fs = 48000; const size_t n = xs.size() / 2;
    std::vector<double> L (n), R (n), oL (n), oR (n);
    for (size_t i = 0; i < n; ++i) { L[i] = xs[2 * i]; R[i] = xs[2 * i + 1]; }
    auto mk = [] (TypeBande t, Forme f, double f0, double q, double g) { BandeSpec b; b.type = t; b.forme = f; b.f0 = f0; b.q = q; b.gainDb = g; b.canal = Canal::Stereo; return b; };
    std::vector<BandeSpec> specs = { mk (TypeBande::Tame, Forme::ShelfGrave, 80, 0.71, -6), mk (TypeBande::Tame, Forme::Cloche, 250, 1.0, -6), mk (TypeBande::Shape, Forme::Cloche, 2500, 0.7, 6),
                                     mk (TypeBande::Tame, Forme::ShelfAigu, 8000, 0.71, -4), mk (TypeBande::Exciter, Forme::ShelfAigu, 9600, 0.71, 5) };
    Engine eng; eng.prepare (fs, specs);
    auto t0 = std::chrono::steady_clock::now();
    for (size_t i = 0; i < n; i += 512) { const int m = (int) std::min<size_t> (512, n - i); eng.process (L.data() + i, R.data() + i, oL.data() + i, oR.data() + i, m); }
    const double dt = std::chrono::duration<double> (std::chrono::steady_clock::now() - t0).count();
    std::cout << "5 bandes stereo (3 Tame + Shape + Exciter) : " << dt / (n / fs) * 100.0 << " % d'un coeur\n";
}
