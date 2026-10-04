"""PRISME — compensation de sonie (prototype flux, 2026-10-04) : le signal TRAITÉ est recalé sur la sonie du signal SEC pour que l'A/B ne soit pas biaisé par le volume.

  - pondération K (ITU-R BS.1770) : étage 1 = shelf aigu +4 dB (1 682 Hz), étage 2 = passe-haut (38 Hz), mêmes formules que pyloudnorm, valables à toute fréquence d'échantillonnage ;
  - puissance = somme des carrés pondérés des deux canaux, moyennée : cumulative pendant la première seconde (pas de démarrage sur zéro), puis lissée (τ = 1 s) ;
  - écart = sonie(sec) − sonie(traité) en dB, borné à ±12 dB ; GATE absolu à −70 dB (pleine échelle) sur le sec ET sur le traité : en dessous, la correction est GELÉE (pas de dérive dans les silences) ;
  - gain appliqué = écart lissé (τ = 0,3 s) : lent, donc sans pompage ; il agit sur le signal traité seulement (le bypass reste le sec intact) ;
  - sec et traité doivent être ALIGNÉS (l'assemblage retarde déjà le sec de la latence) ;
  - sortie : (signal traité × gain, gain en dB par échantillon).
"""
import numpy as np
from scipy.signal import lfilter

TAU_MESURE, TAU_GAIN = 1.0, 0.3
BORNE_DB, GATE_DB = 12.0, -70.0
DEC = 16                          # l'écart de sonie est évalué à fs/16


def coefs_k(fs):
    """(b1, a1), (b2, a2) : étages de la pondération K (formules de pyloudnorm / BS.1770 généralisées)."""
    G, Q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    K = np.tan(np.pi * fc / fs)
    Vh = 10.0 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0 = 1.0 + K / Q + K * K
    b1 = np.array([(Vh + Vb * K / Q + K * K) / a0, 2.0 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0])
    a1 = np.array([1.0, 2.0 * (K * K - 1.0) / a0, (1.0 - K / Q + K * K) / a0])
    Q2, fc2 = 0.5003270373238773, 38.13547087602444
    K2 = np.tan(np.pi * fc2 / fs)
    a2 = np.array([1.0, 2.0 * (K2 * K2 - 1.0) / (1.0 + K2 / Q2 + K2 * K2), (1.0 - K2 / Q2 + K2 * K2) / (1.0 + K2 / Q2 + K2 * K2)])
    b2 = np.array([1.0, -2.0, 1.0])
    return (b1, a1), (b2, a2)


class _Mesure:
    """Puissance K moyennée d'un signal stéréo, en flux."""
    def __init__(self, fs):
        (self.b1, self.a1), (self.b2, self.a2) = coefs_k(fs)
        self.z1 = [np.zeros(2), np.zeros(2)]
        self.z2 = [np.zeros(2), np.zeros(2)]
        self.c = np.exp(-1.0 / (TAU_MESURE * fs))
        self.K, self.n, self.somme, self.p = int(TAU_MESURE * fs), 0, 0.0, 0.0

    def puissance(self, x):
        """x : (n, 2) → puissance moyennée (n,) : somme des carrés pondérés K des deux canaux."""
        n = len(x)
        e = np.zeros(n)
        for c in range(2):
            y, self.z1[c] = lfilter(self.b1, self.a1, x[:, c], zi=self.z1[c])
            y, self.z2[c] = lfilter(self.b2, self.a2, y, zi=self.z2[c])
            e += y * y
        p = np.empty(n)
        k = int(min(n, max(0, self.K - self.n)))
        if k > 0:
            cs = self.somme + np.cumsum(e[:k])
            p[:k] = cs / (self.n + 1 + np.arange(k))
            self.somme = float(cs[-1])
        self.n += k
        if k < n:
            y0 = float(p[k - 1]) if k > 0 else self.p
            p[k:], _ = lfilter([1 - self.c], [1, -self.c], e[k:], zi=np.array([self.c * y0]))
        self.p = float(p[-1])
        return p


class Sonie:
    def __init__(self, fs):
        self.fs = fs
        self.m_sec, self.m_trt = _Mesure(fs), _Mesure(fs)
        self.cg = np.exp(-1.0 / (TAU_GAIN * fs))
        self.cible, self.g, self.cnt = 0.0, 0.0, 0

    def process(self, sec, traite):
        """sec, traite : (n, 2) alignés → (traité × gain, gain dB (n,)). L'écart de sonie est évalué toutes les DEC échantillons (log10 : coût) et tenu entre deux évaluations."""
        n = len(sec)
        ps, pt = self.m_sec.puissance(sec), self.m_trt.puissance(traite)
        pos = np.arange((-self.cnt) % DEC, n, DEC)
        self.cnt += n
        m = len(pos)
        if m > 0:
            Ls = 10.0 * np.log10(ps[pos] + 1e-20)
            Lt = 10.0 * np.log10(pt[pos] + 1e-20)
            ouvert = (Ls > GATE_DB) & (Lt > GATE_DB)
            cf = np.clip(Ls - Lt, -BORNE_DB, BORNE_DB)
            idx = np.maximum.accumulate(np.where(ouvert, np.arange(m), -1))
            tenu_f = np.where(idx >= 0, cf[np.maximum(idx, 0)], self.cible)       # gate fermé : correction gelée sur la dernière valeur valide
            fr = np.full(n, -1)
            fr[pos] = np.arange(m)
            ff = np.maximum.accumulate(fr)
            tenu = np.where(ff >= 0, tenu_f[np.maximum(ff, 0)], self.cible)
            self.cible = float(tenu_f[-1])
        else:
            tenu = np.full(n, self.cible)
        g, _ = lfilter([1 - self.cg], [1, -self.cg], tenu, zi=np.array([self.cg * self.g]))
        self.g = float(g[-1])
        return traite * (10.0 ** (g / 20.0))[:, None], g


def sonie_band(sec, traite, fs, block=8192):
    s = Sonie(fs)
    out, gs = np.empty_like(traite), []
    for i in range(0, len(sec), block):
        o, g = s.process(sec[i:i + block], traite[i:i + block])
        out[i:i + block] = o
        gs.append(g)
    return out, np.concatenate(gs)


def sonie_k_db(x, fs):
    """Sonie K (dB pleine échelle) d'un signal stéréo : moyenne des carrés pondérés K sur la seconde moitié du signal (pour les tests)."""
    (b1, a1), (b2, a2) = coefs_k(fs)
    e = 0.0
    for c in range(2):
        y = lfilter(b2, a2, lfilter(b1, a1, x[:, c]))
        e = e + y[len(y) // 2:] ** 2
    return 10.0 * np.log10(np.mean(e) + 1e-20)
