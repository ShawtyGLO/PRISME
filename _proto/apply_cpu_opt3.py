"""Optimisation CPU 3 (2026-11-09), SANS changement de son : identites exactes.  Lift : pow(10, g/20) -> exp(g*ln10/20) (ecart mesure 7e-16, pow10 coute 2,8x exp).
Exciter : logcosh recalculait log(2) a chaque appel -> constante (ecart 0)."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")
def edit(path, pairs):
    p = os.path.join(SRC, path); s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:80]); s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)
edit("Dsp/Lift.h", [
 ("        const double g = std::pow (10.0, G * s / 20.0);", "        const double g = std::exp (G * s * 0.11512925464970229);          // = 10^(G s/20) ; exp coute 2,8x moins que pow (identite exacte a 1e-15)"),
 ("        const double inv = std::min (1.0 / (Es * (kPi / 2.0) + 1e-9), std::pow (10.0, -plancherMin / 20.0));",
  "        const double inv = std::min (1.0 / (Es * (kPi / 2.0) + 1e-9), invPlancherMin);"),
 ("    Biquad band;\n    OnePole ea, es;", "    Biquad band;\n    OnePole ea, es;\n    double invPlancherMin = 5623.413251903491;                         // = 10^(75/20) : plancher absolu −75 dBFS, constante (etait recalcule par pow a chaque echantillon)"),
])
edit("Dsp/ExciterV3.h", [
 ("    static double logcosh (double u) { const double a = std::abs (u); return a + std::log1p (std::exp (-2.0 * a)) - std::log (2.0); }",
  "    static double logcosh (double u) { const double a = std::abs (u); return a + std::log1p (std::exp (-2.0 * a)) - 0.69314718055994530942; }   // ln 2 constant (etait recalcule)"),
])
edit("Dsp/Exciter.h", [
 ("inline double logcosh (double u) { const double a = std::abs (u); return a + std::log1p (std::exp (-2.0 * a)) - std::log (2.0); }",
  "inline double logcosh (double u) { const double a = std::abs (u); return a + std::log1p (std::exp (-2.0 * a)) - 0.69314718055994530942; }"),
])
print("ok")
