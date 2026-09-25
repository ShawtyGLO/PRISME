#define _CRT_SECURE_NO_WARNINGS
#include <chrono>
#include <cmath>
#include <iostream>
#include <vector>
#include <xmmintrin.h>
int main()
{
    _mm_setcsr (_mm_getcsr() | 0x8040);
    const int N = 121;
    std::vector<double> b0 (N, 0.01), b1 (N, 0), b2 (N, -0.01), a1 (N, -1.9), a2 (N, 0.98), z1 (N, 0), z2 (N, 0), ef (N, 0), es (N, 0), cf (N, 0.99), cs (N, 0.999), oc (N, 0.01), os (N, 0.001);
    double* Z1 = z1.data(); double* Z2 = z2.data(); double* EF = ef.data(); double* ES = es.data();
    const double *B0 = b0.data(), *B1 = b1.data(), *B2 = b2.data(), *A1 = a1.data(), *A2 = a2.data(), *CF = cf.data(), *CS = cs.data(), *OC = oc.data(), *OS = os.data();
    const int T = 48000 * 10;
    const auto t0 = std::chrono::steady_clock::now();
    double acc = 0;
    for (int t = 0; t < T; ++t)
    {
        const double x = 0.1 * std::sin (t * 0.05);
        for (int k = 0; k < N; ++k)
        {
            const double y = B0[k] * x + Z1[k];
            Z1[k] = B1[k] * x - A1[k] * y + Z2[k];
            Z2[k] = B2[k] * x - A2[k] * y;
            const double ab = std::abs (y);
            EF[k] = OC[k] * ab + CF[k] * EF[k];
            ES[k] = OS[k] * ab + CS[k] * ES[k];
        }
        acc += EF[5];
    }
    const double dt = std::chrono::duration<double> (std::chrono::steady_clock::now() - t0).count();
    std::cout << "analyse seule : " << dt / 10.0 * 100.0 << " % d'un cœur (" << acc * 0 << ")\n";
}
