"""PRISME — type de bande « Lift / Détail » (flux, 2026-09-25) : gain par bande qui dépend du NIVEAU de la bande, bipolaire.

    sortie = entrée + (g(L) − 1) · b(t),       b = signal de la bande (cloche / shelf / passe-bande de la courbe)

  - niveau L(t) en dBFS = 20·log10(π/2 · E), E = enveloppe de |b| (lissage τ_a = 3/f0 borné à 2–20 ms, puis relâchement
    exponentiel de `release_ms`, 95 % à t = durée) : un sinus plein pleine échelle au centre de la bande donne 0 dBFS ;
  - Amount (0 … 100 %) fixe le SEUIL ABSOLU T = −60 + 0,48·Amount dBFS (0 % → −60, 100 % → −12) ;
  - courbe : lift_dB = G · smoothstep((T − L)/W), W = max(1,667·|G|, 6) dB → pente maximale 0,9 < 1 : la sortie reste monotone ;
    rien au-dessus de T, plein gain G à W dB sous T ;
  - G > 0 : ascendant (relève ce qui est faible) ; G < 0 : expandeur descendant (abaisse ce qui est faible) ;
  - PROTECTION DU SOUFFLE (G > 0 seulement, automatique) : plancher N = suiveur du minimum de l'enveloppe lente (τ 100 ms) : descend tout
    de suite, remonte de 3 dB/s, jamais sous −75 dBFS ni utilisé au-dessus de −55 dBFS (au-delà c'est du contenu, pas du souffle) ; porte = smoothstep((Ls − N − MARGE)/6 dB), Ls = niveau lent (τ 100 ms) : ce qui est au niveau du souffle n'est pas relevé ;
  - g = 10^(lift/20) ; additif, causal, latence propre nulle, état conservé entre blocs, deux bandes s'additionnent.
"""
import numpy as np
from scipy.signal import lfilter
from prisme_band import zone_filter
from prisme_shape import _tient_relache

SEUIL_MIN, SEUIL_MAX = -60.0, -12.0
PLANCHER_MIN_DB = -75.0
PLANCHER_MAX_DB = -55.0                          # au-dessus, ce n'est plus du souffle mais du contenu (musique dense : le plancher ne doit pas monter jusqu'à elle)
MONTEE_PLANCHER_DB_S = 3.0
MARGE_DB = 8.0                                   # le souffle doit dépasser le plancher de MARGE + 0..6 dB pour être relevé (réglé par tests_lift)


def seuil_dbfs(amount):
    return SEUIL_MIN + (SEUIL_MAX - SEUIL_MIN) * float(np.clip(amount, 0.0, 100.0)) / 100.0


def smoothstep(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def courbe_lift_db(L, gain_db, amount, gate=1.0):
    """Courbe statique : lift (dB) en fonction du niveau de bande L (dBFS)."""
    W = max(1.667 * abs(gain_db), 6.0)
    return gain_db * smoothstep((seuil_dbfs(amount) - L) / W) * gate


class Lift:
    def __init__(self, fs, shape="bell", f0=1000.0, q=1.0, gain_db=6.0, amount=50.0, release_ms=150.0):
        self.fs, self.G, self.amount = fs, float(gain_db), float(amount)
        self.b, self.a = zone_filter(shape, fs, f0, q)
        ta = float(np.clip(3.0 / f0, 0.002, 0.020))
        self.ca = np.exp(-1.0 / (ta * fs))
        self.cr = np.exp(-1.0 / ((release_ms / 1000.0 / 3.0) * fs))          # 3 constantes → 95 % à t = durée
        self.cs = np.exp(-1.0 / (0.1 * fs))
        self.cn = np.exp(-1.0 / ((8.685889638 / MONTEE_PLANCHER_DB_S) * fs))  # remontée du plancher : 6 dB/s
        self.zb, self.za, self.zs = np.zeros(2), None, None
        self.y_hold, self.y_floor = 0.0, None
        self.W = max(1.667 * abs(self.G), 6.0)
        self.T = seuil_dbfs(self.amount)

    def process(self, x, keep=False):
        b, s = self.detecte(x)
        return self.applique(x, b, s, keep)

    def detecte(self, x):
        """Renvoie (b, s) : signal de la zone et courbe de relevé s (0 … 1, porte de souffle comprise) — la liaison stéréo agit sur s."""
        n = len(x)
        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)
        ab = np.abs(b)
        if self.za is None:                                                   # démarrage à chaud (le plancher ne part pas de zéro)
            self.za, self.zs = np.array([self.ca * ab[0]]), np.array([self.cs * ab[0]])
        Ea, self.za = lfilter([1 - self.ca], [1, -self.ca], ab, zi=self.za)
        E, self.y_hold = _tient_relache(Ea, self.cr, self.y_hold)             # attaque rapide, relâchement 150 ms
        L = 20.0 * np.log10(E * (np.pi / 2) + 1e-12)
        s = smoothstep((self.T - L) / self.W)
        if self.G > 0.0:
            Es, self.zs = lfilter([1 - self.cs], [1, -self.cs], ab, zi=self.zs)
            inv = np.minimum(1.0 / (Es * (np.pi / 2) + 1e-9), 10.0 ** (-PLANCHER_MIN_DB / 20.0))   # plancher d'état ≥ −75 dBFS
            if self.y_floor is None:
                self.y_floor = float(inv[0])          # démarre sur le niveau lent (borné à −75 dBFS)
            inv_n, self.y_floor = _tient_relache(inv, self.cn, self.y_floor)   # min-suiveur : 1/N = max(1/Es, c·1/N)
            N = -20.0 * np.log10(inv_n)
            N = np.clip(N, PLANCHER_MIN_DB, PLANCHER_MAX_DB)
            Ls = 20.0 * np.log10(Es * (np.pi / 2) + 1e-12)                     # porte pilotée par le niveau LENT : pas de scintillement sur du souffle
            s = s * smoothstep((Ls - N - MARGE_DB) / 6.0)
        self.last_L = L
        return b, s

    def applique(self, x, b, s, keep=False):
        lift = self.G * s
        g = 10.0 ** (lift / 20.0)
        y = x + (g - 1.0) * b
        return (y, g) if keep else y


def lift_band(x, fs, shape="bell", f0=1000.0, q=1.0, gain_db=6.0, amount=50.0, release_ms=150.0, block=8192, diag=False):
    if gain_db == 0.0:
        return x.copy()
    s = Lift(fs, shape, f0, q, gain_db, amount, release_ms)
    y = np.empty(len(x))
    gs = []
    for i in range(0, len(x), block):
        out = s.process(x[i:i + block], keep=diag)
        if diag:
            y[i:i + block], g = out
            gs.append(g)
        else:
            y[i:i + block] = out
    return (y, dict(g=np.concatenate(gs))) if diag else y
