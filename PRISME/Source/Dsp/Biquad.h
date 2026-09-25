// PRISME — biquad en forme transposée II (identique à scipy.signal.lfilter), en double. Aucune dépendance JUCE.
#pragma once
#include <cmath>

namespace prisme
{
constexpr double kPi = 3.14159265358979323846;   // pas de M_PI : non défini par défaut sous MSVC

struct BiquadCoefs
{
    double b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0;          // a0 normalisé à 1
};

// Formules RBJ (Audio EQ Cookbook) — mêmes que `rbj_bandpass0db`, `rbj_lowpass`, `rbj_highpass` du prototype.
inline BiquadCoefs rbjBandpass0dB (double fs, double f0, double q)
{
    const double w0 = 2.0 * kPi * f0 / fs, al = std::sin (w0) / (2.0 * q), c = std::cos (w0), a0 = 1.0 + al;
    return { al / a0, 0.0, -al / a0, -2.0 * c / a0, (1.0 - al) / a0 };
}

inline BiquadCoefs rbjLowpass (double fs, double f0, double q = 0.7071)
{
    const double w0 = 2.0 * kPi * f0 / fs, al = std::sin (w0) / (2.0 * q), c = std::cos (w0), a0 = 1.0 + al;
    return { (1.0 - c) / 2.0 / a0, (1.0 - c) / a0, (1.0 - c) / 2.0 / a0, -2.0 * c / a0, (1.0 - al) / a0 };
}

inline BiquadCoefs rbjHighpass (double fs, double f0, double q = 0.7071)
{
    const double w0 = 2.0 * kPi * f0 / fs, al = std::sin (w0) / (2.0 * q), c = std::cos (w0), a0 = 1.0 + al;
    return { (1.0 + c) / 2.0 / a0, -(1.0 + c) / a0, (1.0 + c) / 2.0 / a0, -2.0 * c / a0, (1.0 - al) / a0 };
}

// Shelf RBJ (pente S = 1) : haut = true → shelf aigu. Mêmes formules que `rbj_shelf` du prototype.
inline BiquadCoefs rbjShelf (double fs, double f0, double gainDb, bool haut)
{
    const double A = std::pow (10.0, gainDb / 40.0), w0 = 2.0 * kPi * f0 / fs, c = std::cos (w0), s = std::sin (w0);
    const double al = s / 2.0 * std::sqrt ((A + 1.0 / A) * (1.0 / 1.0 - 1.0) + 2.0), t = 2.0 * std::sqrt (A) * al;
    double b0, b1, b2, a0, a1, a2;
    if (haut)
    {
        b0 = A * ((A + 1) + (A - 1) * c + t);  b1 = -2 * A * ((A - 1) + (A + 1) * c);  b2 = A * ((A + 1) + (A - 1) * c - t);
        a0 = (A + 1) - (A - 1) * c + t;        a1 = 2 * ((A - 1) - (A + 1) * c);       a2 = (A + 1) - (A - 1) * c - t;
    }
    else
    {
        b0 = A * ((A + 1) - (A - 1) * c + t);  b1 = 2 * A * ((A - 1) - (A + 1) * c);   b2 = A * ((A + 1) - (A - 1) * c - t);
        a0 = (A + 1) + (A - 1) * c + t;        a1 = -2 * ((A - 1) + (A + 1) * c);      a2 = (A + 1) + (A - 1) * c - t;
    }
    return { b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0 };
}

// Forme de la zone d'une bande : cloche → passe-bande 0 dB ; shelf aigu → passe-haut ; shelf grave → passe-bas (le Q des shelfs est fixe).
enum class Forme { Cloche, ShelfGrave, ShelfAigu };

inline BiquadCoefs zoneFilter (Forme forme, double fs, double f0, double q)
{
    if (forme == Forme::Cloche)    return rbjBandpass0dB (fs, f0, q);
    if (forme == Forme::ShelfAigu) return rbjHighpass (fs, f0);
    return rbjLowpass (fs, f0);
}

class Biquad
{
public:
    void set (const BiquadCoefs& c) { k = c; }
    void reset() { z1 = z2 = 0.0; }

    inline double process (double x)
    {
        const double y = k.b0 * x + z1;
        z1 = k.b1 * x - k.a1 * y + z2;
        z2 = k.b2 * x - k.a2 * y;
        return y;
    }

private:
    BiquadCoefs k;
    double z1 = 0.0, z2 = 0.0;
};

// Lissage du premier ordre y[n] = (1−c)·x[n] + c·y[n−1] (= lfilter([1−c],[1,−c])) avec démarrage « à chaud » optionnel.
class OnePole
{
public:
    void setCoef (double c_) { c = c_; }
    void reset() { y = 0.0; }
    void warm (double x0) { y = x0; }
    inline double process (double x) { y = (1.0 - c) * x + c * y; return y; }

private:
    double c = 0.0, y = 0.0;
};
}
