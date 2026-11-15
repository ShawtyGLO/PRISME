"""PRISME — type de bande « Lift / Détail » à SEUIL RELATIF (flux, prototype 2026-10-04) : gain par bande qui dépend du niveau de la bande PAR RAPPORT À SON NIVEAU HABITUEL.

    sortie = entrée + (g − 1) · b ,   b = signal de la bande (cloche / shelf / passe-bande de la courbe)

Différence avec `prisme_lift.py` (seuil absolu en dBFS) : le seuil n'est plus fixé en dBFS mais RELATIF à la moyenne long terme du niveau de la zone.
  - niveau de zone L(t) (dBFS) : enveloppe de |b| (attaque τ_a = 3/f0 bornée 2–20 ms), relâchement exponentiel ADAPTATIF (voir plus bas) ;
  - niveau habituel lt(t) : moyenne en dB de la zone, τ = 3 s (démarrage à chaud sur le 1er échantillon), niveaux sous −90 dBFS écrêtés (le silence ne tire pas la moyenne vers −∞) ;
  - rel = L − lt (dB) : 0 pour un signal stationnaire, < 0 quand la zone est plus faible que d'habitude (détail, queue, ambiance) ;
  - Amount (0 … 100 %) : seuil relatif Th = −(15 − 0,12·Amount) dB  (0 % : on ne relève que ce qui est ≥ 15 dB sous l'habituel ; 100 % : dès 3 dB sous l'habituel) ;
  - courbe : lift = G · smoothstep((Th − rel)/W), W = max(1,667·|G|, 6) dB (pente < 1 : sortie monotone) ; rien quand rel ≥ Th, plein gain à W sous Th ;
  - RELÂCHEMENT ADAPTATIF : deux suiveurs de niveau, rapide (relâchement/3) et lent (relâchement) ; tant que la zone n'est pas nettement sous l'habituel (rel_lent > Th − W/2) on suit
    le RAPIDE (le relevé s'enclenche vite quand le niveau chute vraiment) ; une fois installé (rel_lent ≤ Th − W/2) on suit le LENT (le relevé se maintient, pas de scintillement) ;
    le retour d'un niveau fort coupe le relevé aussitôt (attaque rapide) ;
  - PROTECTION DU SOUFFLE (G > 0) : identique à `prisme_lift.py` (plancher absolu suiveur du minimum, porte sur le niveau lent) : ce qui est au niveau du souffle n'est pas relevé ;
  - g = 10^(lift/20) ; additif, causal, latence propre nulle, état conservé entre blocs ; mêmes noms d'interface que `Lift` (detecte / applique / process).
"""
import numpy as np
from scipy.signal import lfilter
from prisme_band import zone_filter
from prisme_shape import _tient_relache
from prisme_lift import smoothstep, PLANCHER_MIN_DB, PLANCHER_MAX_DB, MONTEE_PLANCHER_DB_S, MARGE_DB

TAU_REF = 3.0                    # niveau habituel : moyenne en dB sur ~3 s
PLANCHER_REF_DB = -90.0          # le silence ne descend pas la moyenne sous −90 dBFS


def seuil_rel_db(amount):
    return -(15.0 - 0.12 * float(np.clip(amount, 0.0, 100.0)))


def courbe_lift_rel_db(rel, gain_db, amount, gate=1.0):
    """Courbe statique : lift (dB) en fonction du niveau relatif rel = L − niveau habituel (dB)."""
    W = max(1.667 * abs(gain_db), 6.0)
    return gain_db * smoothstep((seuil_rel_db(amount) - rel) / W) * gate


class LiftRel:
    def __init__(self, fs, shape="bell", f0=1000.0, q=1.0, gain_db=6.0, amount=50.0, release_ms=150.0):
        self.fs, self.G, self.amount = fs, float(gain_db), float(amount)
        self.b, self.a = zone_filter(shape, fs, f0, q)
        ta = float(np.clip(3.0 / f0, 0.002, 0.020))
        self.ca = np.exp(-1.0 / (ta * fs))
        self.cr = np.exp(-1.0 / ((release_ms / 1000.0 / 3.0) * fs))                # relâchement lent (3 constantes → 95 % à t = durée)
        self.cr_fast = np.exp(-1.0 / ((release_ms / 1000.0 / 9.0) * fs))           # relâchement rapide : durée / 3
        self.cs = np.exp(-1.0 / (0.1 * fs))
        self.cn = np.exp(-1.0 / ((8.685889638 / MONTEE_PLANCHER_DB_S) * fs))
        self.c_ref = np.exp(-1.0 / (TAU_REF * fs))
        self.zb, self.za, self.zs = np.zeros(2), None, None
        self.hold_f, self.hold_s, self.y_floor, self.lt = 0.0, 0.0, None, None
        self.n_ref, self.somme_ref, self.K_ref = 0, 0.0, int(TAU_REF * fs)
        self.W = max(1.667 * abs(self.G), 6.0)
        self.Th = seuil_rel_db(self.amount)

    def process(self, x, keep=False):
        b, s = self.detecte(x)
        return self.applique(x, b, s, keep)

    def _niveau_habituel(self, Lr):
        """Moyenne CUMULATIVE pendant les premières TAU_REF secondes (comme le Tame v4 : pas de démarrage sur un silence), puis lissage à une constante TAU_REF."""
        n = len(Lr)
        lt = np.empty(n)
        k = int(min(n, max(0, self.K_ref - self.n_ref)))
        if k > 0:
            cs = self.somme_ref + np.cumsum(Lr[:k])
            lt[:k] = cs / (self.n_ref + 1 + np.arange(k))
            self.somme_ref = float(cs[-1])
        self.n_ref += k
        if k < n:
            y0 = float(lt[k - 1]) if k > 0 else self.lt
            lt[k:], _ = lfilter([1 - self.c_ref], [1, -self.c_ref], Lr[k:], zi=np.array([self.c_ref * y0]))
        self.lt = float(lt[-1])
        return lt

    def detecte(self, x):
        n = len(x)
        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)
        ab = np.abs(b)
        if self.za is None:                                                   # démarrage à chaud
            self.za, self.zs = np.array([self.ca * ab[0]]), np.array([self.cs * ab[0]])
        Ea, self.za = lfilter([1 - self.ca], [1, -self.ca], ab, zi=self.za)
        Ef, self.hold_f = _tient_relache(Ea, self.cr_fast, self.hold_f)       # suiveur rapide
        Esl, self.hold_s = _tient_relache(Ea, self.cr, self.hold_s)           # suiveur lent
        Lf = 20.0 * np.log10(Ef * (np.pi / 2) + 1e-12)
        Lsl = 20.0 * np.log10(Esl * (np.pi / 2) + 1e-12)
        Lr = np.maximum(Lsl, PLANCHER_REF_DB)
        lt = self._niveau_habituel(Lr)
        profond = (Lsl - lt) <= (self.Th - 0.5 * self.W)                      # relevé installé → suiveur lent ; sinon rapide
        L = np.where(profond, Lsl, Lf)
        s = smoothstep((self.Th - (L - lt)) / self.W)
        if self.G > 0.0:                                                       # protection du souffle (identique au Lift à seuil absolu)
            Es, self.zs = lfilter([1 - self.cs], [1, -self.cs], ab, zi=self.zs)
            inv = np.minimum(1.0 / (Es * (np.pi / 2) + 1e-9), 10.0 ** (-PLANCHER_MIN_DB / 20.0))
            if self.y_floor is None:
                self.y_floor = float(inv[0])
            inv_n, self.y_floor = _tient_relache(inv, self.cn, self.y_floor)
            N = np.clip(-20.0 * np.log10(inv_n), PLANCHER_MIN_DB, PLANCHER_MAX_DB)
            Ls = 20.0 * np.log10(Es * (np.pi / 2) + 1e-12)
            s = s * smoothstep((Ls - N - MARGE_DB) / 6.0)
        self.last_L, self.last_lt = L, lt
        return b, s

    def applique(self, x, b, s, keep=False):
        g = 10.0 ** (self.G * s / 20.0)
        y = x + (g - 1.0) * b
        return (y, g) if keep else y


def lift_rel_band(x, fs, shape="bell", f0=1000.0, q=1.0, gain_db=6.0, amount=50.0, release_ms=150.0, block=8192, diag=False):
    if gain_db == 0.0:
        return x.copy()
    s = LiftRel(fs, shape, f0, q, gain_db, amount, release_ms)
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
