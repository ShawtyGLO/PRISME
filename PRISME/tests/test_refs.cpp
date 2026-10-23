#define _CRT_SECURE_NO_WARNINGS
// Tests de non-régression C++ contre le prototype Python : lit refs/manifest.txt et compare bit-près (tolérance relative).
//   test_refs.exe [dossier_refs]        code de sortie ≠ 0 si un test échoue.
#include "../Source/Dsp/Lift.h"
#include "../Source/Dsp/Shape.h"
#include "../Source/Dsp/Sonie.h"
#include "../Source/Dsp/Exciter.h"
#include "../Source/Dsp/ExciterV2.h"
#include "../Source/Dsp/ExciterV3.h"
#include "../Source/Dsp/Tame.h"
#include "../Source/Dsp/Engine.h"
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
    double pireZone = 0, pireLift = 0, pireShape = 0, pireExc = 0, pireTame = 0, pireEngine = 0, pireExc2 = 0, pireExc3 = 0, pireSonie = 0;
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
            double dr = 1.5, tl = 0.0;
            is >> g >> mo >> so >> dr >> tl;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;
            if (xs.empty() || xs.size() != ref.size()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            const ModeSat m = mo == "iron" ? ModeSat::Iron : mo == "triode" ? ModeSat::Triode : mo == "diode" ? ModeSat::Diode : mo == "classa" ? ModeSat::ClassA : ModeSat::Rect;
            Exciter ex;
            ex.prepare (fs, forme (sh), f0, q, g, m, so == "auto" ? SourceExc::Auto : SourceExc::Bande);
            ex.setDrive (dr);
            ex.setTilt (tl);
            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (ex.process (xs[i]) - ref[i]));
            e /= std::max (crete, 1e-30);
            pireExc = std::max (pireExc, e);                 // tolérance −140 dB : la projection divise par une énergie proche de 1e-12 sur les passages quasi silencieux
            if (e > 1e-7) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\n"; }
        }
        else if (type == "exciter2")
        {
            double g, dr, tl, dn = 1.0;
            std::string pr, so;
            is >> g >> pr >> so >> dr >> tl >> dn;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;
            if (xs.empty() || xs.size() != ref.size()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            const ProfilExc p = pr == "doux" ? ProfilExc::Doux : pr == "chaud" ? ProfilExc::Chaud : pr == "mordant" ? ProfilExc::Mordant : ProfilExc::MordantChaud;
            ExciterV2 ex;
            ex.prepare (fs, forme (sh), f0, q, g, p, so == "auto" ? SourceExc::Auto : SourceExc::Bande, dr, tl, dn);
            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (ex.process (xs[i]) - ref[i]));
            e /= std::max (crete, 1e-30);
            pireExc2 = std::max (pireExc2, e);
            if (e > 1e-7) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\n"; }
        }
        else if (type == "exciter3")
        {
            double g, dr, tl, pu;
            std::string pr;
            is >> g >> pr >> dr >> tl >> pu;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;
            if (xs.empty() || xs.size() != ref.size()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            const ProfilExc p = pr == "doux" ? ProfilExc::Doux : pr == "chaud" ? ProfilExc::Chaud : pr == "mordant" ? ProfilExc::Mordant : ProfilExc::MordantChaud;
            ExciterV3 ex;
            ex.prepare (fs, forme (sh), f0, q, g, p, dr, tl, pu);
            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (ex.process (xs[i]) - ref[i]));
            e /= std::max (crete, 1e-30);
            pireExc3 = std::max (pireExc3, e);
            if (e > 1e-7) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\n"; }
        }
        else if (type == "tame")
        {
            double g, wd, zp = 1.0;
            is >> g >> wd >> zp;                                              // zp : exposant de zone (facultatif, 1 par défaut)
            if (! is) zp = 1.0;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;
            if (xs.empty() || xs.size() != ref.size()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            Tame t;
            t.prepare (fs, forme (sh), f0, q, g, wd, zp);
            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (t.process (xs[i]) - ref[i]));
            e /= std::max (crete, 1e-30);
            pireTame = std::max (pireTame, e);
            if (e > tolTame) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\n"; }
            else if (std::getenv ("PRISME_VERBOSE")) std::cout << "  ok   " << nom << " " << e << "\n";
        }
        else if (type == "engine")
        {
            std::ifstream cfg (dir + "/" + nom + ".cfg");
            std::vector<BandeSpec> specs;
            std::string ltype, lforme, lcanal, lmode, lsource, lcible;
            int on;
            double lf0, lq, lg, lw, ltime, lsens, lam, lrel, llink, lpur, llcf, lhcf, lstw;
            int llc, llcp, lhc, lhcp;
            while (cfg >> on >> ltype >> lforme >> lf0 >> lq >> lg >> lcanal >> lmode >> lsource >> lw >> lcible >> ltime >> lsens >> lam >> lrel >> llink >> lpur >> llc >> llcf >> llcp >> lhc >> lhcf >> lhcp >> lstw)
            {
                BandeSpec b;
                b.on = on != 0;
                b.type = ltype == "exciter" ? TypeBande::Exciter : ltype == "tame" ? TypeBande::Tame : ltype == "shape" ? TypeBande::Shape : TypeBande::Lift;
                b.forme = forme (lforme); b.f0 = lf0; b.q = lq; b.gainDb = lg;
                b.canal = lcanal == "mid" ? Canal::Mid : lcanal == "side" ? Canal::Side : lcanal == "left" ? Canal::Left : lcanal == "right" ? Canal::Right : Canal::Stereo;
                b.profil = lmode == "doux" ? ProfilExc::Doux : lmode == "chaud" ? ProfilExc::Chaud : lmode == "mordant" ? ProfilExc::Mordant : ProfilExc::MordantChaud;
                b.source = lsource == "auto" ? SourceExc::Auto : SourceExc::Bande;
                b.width = lw; b.cible = lcible == "sustain" ? Shape::Cible::Sustain : Shape::Cible::Transitoires;
                b.timeMs = ltime; b.sens = lsens; b.amount = lam; b.releaseMs = lrel; b.link = llink; b.dens = lpur;
                b.lcOn = llc != 0; b.lcF = llcf; b.lcPente = llcp; b.hcOn = lhc != 0; b.hcF = lhcf; b.hcPente = lhcp; b.stWidth = lstw;
                specs.push_back (b);
            }
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;
            if (xs.empty() || xs.size() != ref.size() || specs.empty()) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            const size_t n = xs.size() / 2;
            std::vector<double> L (n), R (n), oL (n), oR (n);
            for (size_t i = 0; i < n; ++i) { L[i] = xs[2 * i]; R[i] = xs[2 * i + 1]; }
            Engine eng;
            eng.prepare (fs, specs);
            for (size_t i = 0; i < n; i += 500)                                  // blocs de 500 : l'état doit passer d'un bloc à l'autre
            {
                const int m = (int) std::min<size_t> (500, n - i);
                eng.process (L.data() + i, R.data() + i, oL.data() + i, oR.data() + i, m);
            }
            double crete = 0, e = 0;
            for (double v : ref) crete = std::max (crete, std::abs (v));
            for (size_t i = 0; i < n; ++i) e = std::max ({ e, std::abs (oL[i] - ref[2 * i]), std::abs (oR[i] - ref[2 * i + 1]) });
            e /= std::max (crete, 1e-30);
            pireEngine = std::max (pireEngine, e);
            if (e > 1e-7) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << "\n"; }
        }
        else if (type == "sonie")
        {
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");     // entrée : [secL, secR, trtL, trtR] ; sortie : [outL, outR, gain dB]
            ++total;
            if (xs.empty() || xs.size() / 4 != ref.size() / 3) { ++echecs; std::cout << "  FAIL " << nom << " fichiers illisibles\n"; continue; }
            const size_t n = xs.size() / 4;
            Sonie so;
            so.prepare (fs);
            double crete = 0, e = 0, eg = 0;
            for (size_t i = 0; i < n; ++i) crete = std::max (crete, std::max (std::abs (ref[3 * i]), std::abs (ref[3 * i + 1])));
            for (size_t i = 0; i < n; ++i)
            {
                double gdb;
                const double f = so.process (xs[4 * i], xs[4 * i + 1], xs[4 * i + 2], xs[4 * i + 3], gdb);
                e = std::max ({ e, std::abs (xs[4 * i + 2] * f - ref[3 * i]), std::abs (xs[4 * i + 3] * f - ref[3 * i + 1]) });
                eg = std::max (eg, std::abs (gdb - ref[3 * i + 2]));
            }
            e /= std::max (crete, 1e-30);
            pireSonie = std::max (pireSonie, std::max (e, eg));
            if (e > 1e-9 || eg > 1e-8) { ++echecs; std::cout << "  FAIL " << nom << " écart relatif " << e << " ; gain " << eg << " dB\n"; }
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
    std::cout << "zone : écart max " << pireZone << " ; lift : " << pireLift << " ; shape : " << pireShape << " ; exciter : " << pireExc << " ; exciter v2 : " << pireExc2 << " ; exciter v3 : " << pireExc3 << " ; tame : " << pireTame << " ; engine : " << pireEngine << " ; sonie : " << pireSonie << " (écarts relatifs max)\n";
    // W01 : une bande NEUVE, préchauffée avec 2,5 s d historique, doit avoir le niveau de delta d'une bande vivante depuis le début
    {
        const auto m = lire (dir + "/music12.f64");
        if (! m.empty())
        {
            const size_t n = m.size() / 2;
            const double fs = 48000.0;
            const size_t t0 = (size_t) (8.0 * fs), hist = (size_t) (6.0 * fs);
            struct Cfg { TypeBande t; Forme f; double f0, q, g; ProfilExc mo; const char* nom; };
            const Cfg cfgs[] = { { TypeBande::Exciter, Forme::Cloche, 3000, 0.71, 2, ProfilExc::MordantChaud, "Exciter cloche 3 k +2" },
                                 { TypeBande::Exciter, Forme::ShelfGrave, 42, 0.71, 3, ProfilExc::MordantChaud, "Exciter shelf grave 42 +3" },
                                 { TypeBande::Exciter, Forme::ShelfAigu, 9600, 0.71, 5, ProfilExc::MordantChaud, "Exciter shelf aigu 9,6 k +5" },
                                 { TypeBande::Tame, Forme::Cloche, 3000, 0.7, -9, ProfilExc::MordantChaud, "Tame cloche 3 k -9" },
                                 { TypeBande::Shape, Forme::Cloche, 250, 1.0, 6, ProfilExc::MordantChaud, "Shape cloche 250 +6" },
                                 { TypeBande::Lift, Forme::Cloche, 3000, 0.7, 6, ProfilExc::MordantChaud, "Lift cloche 3 k +6" } };
            for (const auto& c : cfgs)
            {
                BandeSpec sp; sp.type = c.t; sp.forme = c.f; sp.f0 = c.f0; sp.q = c.q; sp.gainDb = c.g; sp.profil = c.mo; sp.amount = 70.0;
                BandeProc vivant, neuve, neuveFroide;
                vivant.prepare (fs, sp); neuve.prepare (fs, sp); neuveFroide.prepare (fs, sp);
                std::vector<double> dv, dn, dc;
                double dl, dr;
                for (size_t i = 0; i < n; ++i)
                {
                    vivant.process (m[2 * i], m[2 * i + 1], dl, dr);
                    if (i >= t0) dv.push_back (dl);
                    if (i >= t0 - hist) { neuve.process (m[2 * i], m[2 * i + 1], dl, dr); if (i >= t0) dn.push_back (dl); }
                    if (i >= t0) { neuveFroide.process (m[2 * i], m[2 * i + 1], dl, dr); dc.push_back (dl); }
                }
                auto tranche = [&] (const std::vector<double>& v, size_t a, size_t b) { double s = 0; for (size_t i = a; i < b && i < v.size(); ++i) s += v[i] * v[i]; return 10.0 * std::log10 (s / (double) (b - a) + 1e-30); };
                double pireW = 0, pireC = 0;
                for (size_t a = 0; a + 2400 <= (size_t) (2.0 * fs); a += 2400)         // tranches de 50 ms sur les 2 premières secondes
                {
                    if (tranche (dv, a, a + 2400) < -100.0) continue;                 // wet négligeable (< −100 dBFS) : l'écart en dB n'a pas de sens
                    pireW = std::max (pireW, std::abs (tranche (dn, a, a + 2400) - tranche (dv, a, a + 2400)));
                    pireC = std::max (pireC, std::abs (tranche (dc, a, a + 2400) - tranche (dv, a, a + 2400)));
                }
                ++total;
                const bool ok = pireW <= 1.0;
                if (! ok) ++echecs;
                std::cout << (ok ? "  PASS  " : "  FAIL  ") << "W01 préchauffage " << c.nom << " : écart de niveau du delta, pire tranche de 50 ms : préchauffée " << pireW << " dB, à froid " << pireC << " dB" << std::endl;
            }
        }
    }
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
        Shape sh; sh.prepare (48000, Shape::Cible::Transitoires, Forme::Cloche, 200, 0.7, 9, 0.0, 0.85);
        std::vector<double> x (48000 * 30);
        unsigned s = 5; for (double& v : x) { s = s * 1664525u + 1013904223u; v = ((s >> 8) / 8388608.0 - 1.0) * 0.1; }
        const auto t0 = std::chrono::steady_clock::now();
        double acc = 0; for (double v : x) acc += sh.process (v);
        const double dt = std::chrono::duration<double> (std::chrono::steady_clock::now() - t0).count();
        std::cout << "coût Shape v5 : " << dt / 30.0 * 100.0 << " % d'un cœur par bande mono (" << acc * 0 << ")\n";
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
