"""PRISME — prototype DSP (étape 0).

Contenu :
  - 5 modes de saturation (Triode, Diode, Iron, Class-A, Rectifier), chacun avec sa
    primitive F1 pour l'ADAA d'ordre 1 (anti-aliasing sans latence).
  - filtres RBJ (cloche, shelfs) + identité cloche = 1 + (A²-1)·passe-bande (Q' = A·Q).
  - résidu d'excitation « harmoniques seules » (équivalent du De-emphasis de Spectre).

Tout en float64 (règle apprise sur InvisibleClip : l'ADAA en float32 annule catastrophiquement).
"""
import numpy as np
from scipy.signal import lfilter, resample_poly

# ---------------------------------------------------------------- saturations
_B = 0.18                       # biais Triode
_SL = 1.0 - np.tanh(_B) ** 2    # pente en 0 -> normalisation à gain petit signal = 1
_EPS_R = 0.05                   # lissage du kink du Rectifier


def _logcosh(u):
    a = np.abs(u)
    return a + np.log1p(np.exp(-2.0 * a)) - np.log(2.0)


def triode_f(x):
    return (np.tanh(x + _B) - np.tanh(_B)) / _SL


def triode_F(x):
    return (_logcosh(x + _B) - x * np.tanh(_B)) / _SL


def classa_f(x):                # cubique borné à ±1 : monotone (corrige l'ancien x-x³/3 sur ±1,5)
    c = np.clip(x, -1.0, 1.0)
    return c - c ** 3 / 3.0


def classa_F(x):
    a = np.abs(x)
    return np.where(a <= 1.0, a * a / 2.0 - a ** 4 / 12.0, 5.0 / 12.0 + (2.0 / 3.0) * (a - 1.0))


def iron_f(x):
    return x / np.sqrt(1.0 + x * x)


def iron_F(x):
    return np.sqrt(1.0 + x * x)


def diode_f(x):
    return np.where(x >= 0, 1.0 - np.exp(-np.abs(x)), -(1.0 - np.exp(-1.5 * np.abs(x))) / 1.5)


def diode_F(x):
    ax = np.abs(x)
    pos = ax + np.exp(-ax) - 1.0
    neg = -(-ax - np.exp(-1.5 * ax) / 1.5) / 1.5 - 1.0 / 2.25
    # pour x<0 : F1(x) = -(x - e^{1.5x}/1.5)/1.5 - 1/2.25, avec x = -ax
    return np.where(x >= 0, pos, neg)


def rect_f(x):
    return np.sqrt(x * x + _EPS_R ** 2) - _EPS_R


def rect_F(x):
    return 0.5 * (x * np.sqrt(x * x + _EPS_R ** 2) + _EPS_R ** 2 * np.arcsinh(x / _EPS_R)) - _EPS_R * x


def rect_curves(eps):
    """Rectifier à lissage du coude variable : eps petit = coude franc (riche), grand = doux (surtout H2)."""
    f = lambda x: np.sqrt(x * x + eps ** 2) - eps
    F = lambda x: 0.5 * (x * np.sqrt(x * x + eps ** 2) + eps ** 2 * np.arcsinh(x / eps)) - eps * x
    return f, F


# nom -> (f, F1, sortie_contient_deja_les_harmoniques_seules)
MODES = {
    "triode": (triode_f, triode_F, False),
    "diode": (diode_f, diode_F, False),
    "iron": (iron_f, iron_F, False),
    "classa": (classa_f, classa_F, False),
    "rect": (rect_f, rect_F, True),
}


def saturate(x, mode, adaa=True, eps=1e-6):
    """Applique la courbe `mode` à x (naïf ou ADAA d'ordre 1)."""
    f, F, _ = MODES[mode] if mode != "lin" else (lambda v: v, lambda v: 0.5 * v * v, False)
    if not adaa:
        return f(x)
    x1 = np.concatenate(([0.0], x[:-1]))
    dx = x - x1
    small = np.abs(dx) < eps
    safe = np.where(small, 1.0, dx)
    return np.where(small, f(0.5 * (x + x1)), (F(x) - F(x1)) / safe)


def dc_block(x, fs, fc=20.0):
    r = 1.0 - 2.0 * np.pi * fc / fs
    return lfilter([1.0, -1.0], [1.0, -r], x)


def excite_residual(x, mode, drive, fs, adaa=True, oversample=1):
    """Ce que l'exciter AJOUTE : harmoniques seules (fondamental et compression retirés).

    x : signal source de la bande. drive : gain avant la courbe (normalisé à la sortie).
    Pour le Rectifier, la courbe produit déjà H2/H4 : on ne retire que le continu.
    """
    _, _, is_harm = MODES[mode]
    if oversample > 1:
        xs = resample_poly(x, oversample, 1)
    else:
        xs = x
    y = saturate(xs * drive, mode, adaa=adaa) / drive
    if oversample > 1:
        y = resample_poly(y, 1, oversample)
        xs = x
    res = y if is_harm else y - x
    return dc_block(res, fs)


# --------------------------------------------------------------- filtres RBJ
def rbj_peaking(fs, f0, gain_db, q):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / fs
    al = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    b = np.array([1 + al * A, -2 * c, 1 - al * A])
    a = np.array([1 + al / A, -2 * c, 1 - al / A])
    return b / a[0], a / a[0]


def rbj_bandpass0db(fs, f0, q):
    w0 = 2 * np.pi * f0 / fs
    al = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    b = np.array([al, 0.0, -al])
    a = np.array([1 + al, -2 * c, 1 - al])
    return b / a[0], a / a[0]


# ------------------------------------------------ désaccord lent des raies
def random_shift(res, fs, spread_hz, rate_hz=3.0, seed=0):
    """Décalage de fréquence (bande unique) lent et aléatoire : étale chaque raie harmonique.

    df(t) = bruit gaussien passe-bas (rate_hz), borné à ±spread_hz. Hors ligne (Hilbert FFT) ;
    en temps réel : paire de passe-tout (réseau de Hilbert IIR) + oscillateur complexe.
    """
    from scipy.signal import butter, sosfilt, hilbert
    rng = np.random.default_rng(seed)
    w = sosfilt(butter(2, rate_hz, btype="low", fs=fs, output="sos"), rng.standard_normal(len(res)))
    w = np.clip(w / (np.std(w) + 1e-12), -2.5, 2.5) / 2.5
    phase = 2 * np.pi * np.cumsum(w * spread_hz) / fs
    return np.real(hilbert(res) * np.exp(1j * phase))
