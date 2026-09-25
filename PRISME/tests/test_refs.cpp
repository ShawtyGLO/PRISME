#define _CRT_SECURE_NO_WARNINGS
// Tests de non-régression C++ contre le prototype Python : lit refs/manifest.txt et compare bit-près (tolérance relative).
//   test_refs.exe [dossier_refs]        code de sortie ≠ 0 si un test échoue.
#include "../Source/Dsp/Lift.h"
#include "../Source/Dsp/Shape.h"
#include "../Source/Dsp/Exciter.h"
#include "../Source/Dsp/Tame.h"
#include <cstdlib>
#include <xmmintrin.h>
#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

using namespace prisme;

static std::vector<double> lire (const std::string& chemin)
{
    std::ifstream f (chemin, std::ios::binary | std::ios::ate);
    if (! f) return {};
    const auto n = (size_t) f.tellg() / sizeof (double);
    std::vector<double> v (n);
    f.seekg (0);
    f.read ((char*) v.data(), n * sizeof (double));
    return v;
}

static Forme forme (const std::string& s) { return s == "bell" ? Forme::Cloche : s == "highshelf" ? Forme::ShelfAigu : Forme::ShelfGrave; }

int main (int argc, char** argv)
{
    _mm_setcsr (_mm_getcsr() | 0x8040);                  // FTZ + DAZ, comme juce::ScopedNoDenormals dans processBlock
    const std::string dir = argc > 1 ? argv[1] : "refs";
    std::ifstream man (dir + "/manifest.txt");
    if (! man) { std::cout << "manifest introuvable dans " << dir << "\n"; return 2; }
    int total = 0, echecs = 0;
    double pireZone = 0, pireLift = 0, pireShape = 0, pireExc = 0, pireTame = 0;
    const double tolTame = 1e-7;                         // −140 dB ; le prototype calcule sa chaîne spectrale en float32 (voir Tame.h)
    std::string ligne;
    while (std::getline (man, ligne))
    {
        std::istringstream is (ligne);
        std::string type, nom, sh;
        double fs, f0, q;
        is >> type >> nom >> fs >> sh >> f0 >> q;
        if (type == "zone")
        {
            double r[5];
            for (double& v : r) is >> v;
            const auto c = zoneFilter (forme (sh), fs, f0, q);
            const double e[5] = { c.b0 - r[0], c.b1 - r[1], c.b2 - r[2], c.a1 - r[3], c.a2 - r[4] };
            double m = 0;
            for (double v : e) m = std::max (m, std::abs (v));
            pireZone = std::max (pireZone, m);
            ++total;
            if (m > 1e-12) { ++echecs; std::cout << "  FAIL zone " << nom << " écart " << m << "\n"; }
        }
        else if (type == "shape")
        {
            double g, tm, sens;
            std::string cb;
            is >> g >> cb >> tm >> sens;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            const auto& x = xs;
            ++total;
            if (x.empty() || x.size() != ref.size()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            Shape s;
            s.prepare (fs, cb == "sustain" ? Shape::Cible::Sustain : Shape::Cible::Transitoires, forme (sh), f0, q, g, tm, sens);
            for (size_t i = 0; i < x.size(); ++i) e = std::max (e, std::abs (s.process (x[i]) - ref[i]));
            e /= std::max (crete, 1e-30);
            pireShape = std::max (pireShape, e);
            if (e > 1e-9) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\n"; }
        }
        else if (type == "exciter")
        {
            double g;
            std::string mo, so;
            is >> g >> mo >> so;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;
            if (xs.empty() || xs.size() != ref.size()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            const ModeSat m = mo == "iron" ? ModeSat::Iron : mo == "triode" ? ModeSat::Triode : mo == "diode" ? ModeSat::Diode : mo == "classa" ? ModeSat::ClassA : ModeSat::Rect;
            Exciter ex;
            ex.prepare (fs, forme (sh), f0, q, g, m, so == "auto" ? SourceExc::Auto : SourceExc::Bande);
            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (ex.process (xs[i]) - ref[i]));
            e /= std::max (crete, 1e-30);
            pireExc = std::max (pireExc, e);                 // tolérance −140 dB : la projection divise par une énergie proche de 1e-12 sur les passages quasi silencieux
            if (e > 1e-7) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\n"; }
        }
        else if (type == "tame")
        {
            double g, wd;
            is >> g >> wd;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;
            if (xs.empty() || xs.size() != ref.size()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            Tame t;
            t.prepare (fs, forme (sh), f0, q, g, wd);
            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (t.process (xs[i]) - ref[i]));
            e /= std::max (crete, 1e-30);
            pireTame = std::max (pireTame, e);
            if (e > tolTame) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\n"; }
            else if (std::getenv ("PRISME_VERBOSE")) std::cout << "  ok   " << nom << " " << e << "\n";
        }
        else if (type == "lift")
        {
            double g, am, rel;
            is >> g >> am >> rel;
            const auto x = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            if (x.empty() || x.size() != ref.size()) { ++total; ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            double crete = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            auto passe = [&] (size_t bloc)                       // même résultat quelle que soit la taille des blocs
            {
                Lift l;
                l.prepare (fs, forme (sh), f0, q, g, am, rel);
                std::vector<double> y (x.size());
                for (size_t i = 0; i < x.size(); i += bloc)
                    for (size_t j = i; j < std::min (i + bloc, x.size()); ++j) y[j] = l.process (x[j]);
                return y;
            };
            const auto y = passe (x.size());
            double e = 0;
            for (size_t i = 0; i < x.size(); ++i) e = std::max (e, std::abs (y[i] - ref[i]));
            e /= std::max (crete, 1e-30);
            pireLift = std::max (pireLift, e);
            ++total;
            if (e > 1e-9) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\n"; }
        }
    }
    std::cout << "zone : écart max " << pireZone << " ; lift : " << pireLift << " ; shape : " << pireShape << " ; exciter : " << pireExc << " ; tame : " << pireTame << " (écarts relatifs max)\n";
    // coût : 60 s de mono à 48 kHz, configuration type
    {
        Lift l; l.prepare (48000, Forme::Cloche, 1000, 1.0, 12, 60, 150);
        std::vector<double> x (48000 * 60);
        unsigned s = 1; for (double& v : x) { s = s * 1664525u + 1013904223u; v = ((s >> 8) / 8388608.0 - 1.0) * 0.05; }
        const auto t0 = std::chrono::steady_clock::now();
        double acc = 0; for (double v : x) acc += l.process (v);
        const double dt = std::chrono::duration<double> (std::chrono::steady_clock::now() - t0).count();
        std::cout << "coût Lift : " << dt / 60.0 * 100.0 << " % d'un cœur par bande mono (" << acc * 0 << ")\n";
    }
    {
        Exciter ex; ex.prepare (48000, Forme::Cloche, 3000, 1.0, 5, ModeSat::Iron, SourceExc::Auto);
        std::vector<double> x (48000 * 30);
        unsigned s = 7; for (double& v : x) { s = s * 1664525u + 1013904223u; v = ((s >> 8) / 8388608.0 - 1.0) * 0.2; }
        const auto t0 = std::chrono::steady_clock::now();
        double acc = 0; for (double v : x) acc += ex.process (v);
        const double dt = std::chrono::duration<double> (std::chrono::steady_clock::now() - t0).count();
        std::cout << "coût Exciter (Iron Auto) : " << dt / 30.0 * 100.0 << " % d'un cœur par bande mono (" << acc * 0 << ")\n";
    }
    for (auto cfg : { std::make_pair (Forme::Cloche, 0.7), std::make_pair (Forme::ShelfAigu, 0.71), std::make_pair (Forme::ShelfGrave, 0.71) })
    {
        Tame t; t.prepare (48000, cfg.first, cfg.first == Forme::ShelfGrave ? 120.0 : 3000.0, cfg.second, -9, 0.5);
        std::vector<double> x = lire (dir + "/tame_mus_0.in.f64");            // vraie musique (2 s) répétée 5 fois : le coût dépend du contenu
        if (x.empty()) x.assign (96000, 0.1);
        const auto un = x;
        for (int r = 0; r < 4; ++r) x.insert (x.end(), un.begin(), un.end());
        const auto t0 = std::chrono::steady_clock::now();
        double acc = 0; for (double v : x) acc += t.process (v);
        const double dt = std::chrono::duration<double> (std::chrono::steady_clock::now() - t0).count();
        std::cout << "coût Tame (" << (cfg.first == Forme::Cloche ? "cloche 3 k Q0,7" : cfg.first == Forme::ShelfAigu ? "shelf aigu 3 k" : "shelf grave 120") << ") : " << dt / (x.size() / 48000.0) * 100.0 << " % d'un cœur par bande mono (" << acc * 0 << ")\n";
    }
    std::cout << (total - echecs) << "/" << total << " réussis\n";
    return echecs ? 1 : 0;
}
