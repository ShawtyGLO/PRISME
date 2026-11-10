"""Optimisation CPU 4 (2026-11-09), SANS changement de son : Historique<N> a tampon MIROIR (chaque valeur ecrite a deux places, lecture lineaire sans branche ni modulo).
Les FIR de l'Exciter lisent alors un pointeur contigu : at(k) == buf[pos+k] toujours valide. Resultat bit-identique (memes produits, meme ordre de sommation)."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")
p = os.path.join(SRC, "Dsp", "Exciter.h"); s = open(p, encoding="utf-8").read()
a = '''class Historique
{
public:
    void reset() { buf.fill (0.0); pos = 0; }
    inline void push (double x) { pos = (pos == 0) ? N - 1 : pos - 1; buf[(size_t) pos] = x; }
    inline double at (int k) const { int i = pos + k; if (i >= N) i -= N; return buf[(size_t) i]; }

private:
    std::array<double, N> buf {};
    int pos = 0;
};'''
b = '''class Historique
{
public:
    void reset() { buf.fill (0.0); pos = N; }
    // tampon miroir : la valeur est ecrite en pos et en pos + N, donc buf[pos .. pos + N - 1] est toujours l'historique contigu (at(0) = la plus recente)
    inline void push (double x) { pos = (pos == 0) ? N - 1 : pos - 1; buf[(size_t) pos] = x; buf[(size_t) pos + N] = x; }
    inline double at (int k) const { return buf[(size_t) (pos + k)]; }
    inline const double* data() const { return buf.data() + pos; }                    // pointeur contigu sur les N dernieres valeurs

private:
    std::array<double, 2 * N> buf {};
    int pos = N;
};'''
assert a in s; s = s.replace(a, b, 1); open(p, "w", encoding="utf-8").write(s)
p = os.path.join(SRC, "Dsp", "ExciterV3.h"); s = open(p, encoding="utf-8").read()
a = '''        double v0 = 0, v1 = 0;
        for (int i = 0; i < 21; ++i) v0 += tables::hUp[2 * i] * hUp.at (i);
        for (int i = 0; i < 20; ++i) v1 += tables::hUp[2 * i + 1] * hUp.at (i);
        hY.push (adaa (v0));
        double y = 0;
        for (int i = 0; i < 41; ++i) y += tables::h0[i] * hY.at (i);'''
b = '''        double v0 = 0, v1 = 0;
        { const double* hu = hUp.data();                                              // lecture contigue (tampon miroir), memes produits, meme ordre
          for (int i = 0; i < 21; ++i) v0 += tables::hUp[2 * i] * hu[i];
          for (int i = 0; i < 20; ++i) v1 += tables::hUp[2 * i + 1] * hu[i]; }
        hY.push (adaa (v0));
        double y = 0;
        { const double* hy = hY.data();
          for (int i = 0; i < 41; ++i) y += tables::h0[i] * hy[i]; }'''
assert a in s; s = s.replace(a, b, 1); open(p, "w", encoding="utf-8").write(s)
print("ok")
