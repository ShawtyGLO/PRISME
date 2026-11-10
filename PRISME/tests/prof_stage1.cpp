// Micro-banc : memes operations que Tame::stage1 (N = 121, sizeV4 = 97, 1 trame toutes les 32 echantillons a 48 kHz = 1500 trames/s).
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <vector>
using C = std::chrono::steady_clock;
static double dt (C::time_point a) { return std::chrono::duration<double> (C::now() - a).count(); }
int main()
{
    const int N = 121, sizeV4 = 97, trames = 1500 * 20;                         // 20 s
    std::vector<double> es (N), ef (N), detr (N), tri (std::max (sizeV4, N)), diffv (N);
    std::vector<float> Lf (N), Lp (N), Ls (N), line (N + 400);
    unsigned s = 1; auto rnd = [&] { s = s * 1664525u + 1013904223u; return (s >> 8) / 8388608.0 * 0.05; };
    for (int k = 0; k < N; ++k) { es[k] = rnd(); ef[k] = rnd(); detr[k] = rnd() * 60 - 60; diffv[k] = rnd() * 10 - 5; }
    double acc = 0, tLog = 0, tLogN = 0, tUni = 0, tPct = 0, tMed = 0;
    for (int f = 0; f < trames; ++f)
    {
        for (int k = 0; k < N; ++k) es[k] += 1e-6 * (k & 3);
        auto a0 = C::now();
        for (int k = 0; k < N; ++k) Lf[k] = (float) (20.0 * std::log10 (std::max (es[k], 0.5 * ef[k]) * 1.5707963 + 1e-12));
        tLog += dt (a0);
        a0 = C::now();
        for (int k = 0; k < N; ++k) Lp[k] = (float) (8.6858896380650365530 * std::log (std::max (es[k], 0.5 * ef[k]) * 1.5707963 + 1e-12));
        tLogN += dt (a0);
        a0 = C::now();
        for (int pass = 0; pass < 2; ++pass)
        {   const int size = pass ? 5 : 13, size1 = size / 2, size2 = size - size1 - 1;
            for (int i = 0; i < size1; ++i) line[i] = Lp[0]; for (int i = 0; i < N; ++i) line[size1 + i] = Lp[i]; for (int i = 0; i < size2; ++i) line[size1 + N + i] = Lp[N - 1];
            double tmp = 0; for (int i = 0; i < size; ++i) tmp += line[i]; tmp /= size; Ls[0] = (float) tmp;
            for (int i = 1; i < N; ++i) { tmp += (line[i + size - 1] - line[i - 1]) / size; Ls[i] = (float) tmp; } }
        tUni += dt (a0);
        if (f % 16 == 0)
        {   a0 = C::now(); const int h = sizeV4 / 2, rang = (int) (sizeV4 * 15.0 / 100.0);
            for (int k = 0; k < N; ++k) { for (int d = -h; d <= h; ++d) tri[d + h] = detr[std::clamp (k + d, 0, N - 1)]; std::nth_element (tri.begin(), tri.begin() + rang, tri.begin() + sizeV4); acc += tri[rang]; }
            tPct += dt (a0); }
        a0 = C::now(); std::copy (diffv.begin(), diffv.end(), tri.begin()); std::nth_element (tri.begin(), tri.begin() + N / 2, tri.begin() + N); acc += tri[N / 2]; tMed += dt (a0);
        acc += Lf[3] + Ls[5];
    }
    const double k = 100.0 / 20.0;
    std::cout << "log10 x121 / trame      : " << tLog * k << " %   (variante log*cte : " << tLogN * k << " %)\n";
    std::cout << "uniformFilter x2        : " << tUni * k << " %\n";
    std::cout << "percentile 121 x nth(97): " << tPct * k << " % amorti (1 trame sur 16)\n";
    std::cout << "mediane nth(121)        : " << tMed * k << " %\n" << (acc * 0) << "\n";
    // ecart log10 vs log*cte et pow10 vs exp (sur 1e6 valeurs)
    double eLog = 0, eExp = 0;
    for (int i = 1; i < 1000000; ++i) { const double v = i * 1e-6; eLog = std::max (eLog, std::abs (20.0 * std::log10 (v) - 8.6858896380650365530 * std::log (v)) / std::abs (20.0 * std::log10 (v)));
        const double g = (i % 60) - 30.0; eExp = std::max (eExp, std::abs (std::pow (10.0, g / 20.0) - std::exp (g * 0.11512925464970229)) / std::pow (10.0, g / 20.0)); }
    std::cout << "ecart relatif max  20log10 -> log*cte : " << eLog << "   pow10 -> exp : " << eExp << "\n";
}
