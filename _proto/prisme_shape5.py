"""PRISME — type de bande « Shape » v5 en flux (2026-10-01) : détection de PERCUSSION (flux léger × veto tonal), seuil adaptatif, ANTICIPATION.

    sortie = entrée + (g − 1) · b_retardé ,   b = signal de la zone (cloche / shelf / passe-bande de la courbe), retardé de `look` échantillons.

Détecteur « D » validé à l'écoute par llg53 (point de sauvegarde du 2026-10-01 dans le vault) :
  B  flux léger : banc de bandes passe-bande RBJ, 3 par octave de 30 Hz à 0,45·fs ; enveloppe rapide τ = max(2 ms, 2/f) ; niveaux L_k en dB à fs/16 ;
     montée = L_k(t) − max sur 3 bandes voisines de L(t − retard), retard = clip(3/f0, 5, 30 ms) ; force B = max(montée moyenne des bandes de contexte
     (zone ± 1,5 oct), montée moyenne de toutes les bandes ≥ 60 Hz) × porte −95 dBFS ;
  C  veto tonal : prédicteur NLMS (16 coefficients, μ = 0,2) du signal de zone ; force C = 20·log10(env rapide |e| / env lente |e|), env rapide τ = clip(2/f0, 2, 10 ms),
     env lente τ = 50 ms, × porte −95 dBFS ; une note tenue est prévisible (résidu faible), une percussion ne l'est pas ;
  D  = √( max(B,0) · max(C,0) / 3 )  (aux instants décimés, tous les 16 échantillons).
Seuil ADAPTATIF : m0_eff = max(m0, quantile P de D sur les 2 dernières secondes) ; m0 = (10 − 9·sens)/2,35 (= 1,0 à sens 0,85) ; P = 99 − 12·sens (≈ 89 % par défaut) ;
  le quantile est mis à jour toutes les 16 poussées (une valeur de D toutes les 4 trames = 64 échantillons dans l'anneau de 2 s).
Poids T = clip((D − m0_eff)/2, 0, 1) → tenue/relâchement (durée `time_ms`, 30 ms par défaut ; 3 constantes) aux instants décimés, maintenu entre deux trames,
attaque lissée (0,45 période à 60 Hz … 0,8 période à 250 Hz et plus) au débit plein → Tl.
ANTICIPATION : le poids calculé à l'instant n s'applique à b(n − look) : le gain arrive AVANT l'attaque ; `look` = latence de l'assemblage (192 échantillons).
Transitoires : poids = Tl ; sustain : poids = 1 − Tl (partition de l'unité). Causal en entrée (le décalage est une latence), état conservé entre blocs.
"""
import numpy as np
from scipy.signal import lfilter
from prisme_band import zone_filter
from prisme_dsp import rbj_bandpass0db

DEC = 16
LOOK = 192                                        # = latence de l'assemblage (EngineStream.latence)
PER_OCT = 3
ORDRE, MU = 16, 0.2
PAS_ANNEAU, RECALC = 4, 16                        # une valeur de D toutes les 4 trames dans l'anneau de 2 s ; quantile recalculé toutes les 16 poussées
LARGEUR = 2.0
TIME_DEFAUT_MS = 30.0
M0_ECHELLE = 1.0 / 2.35


def zone_lo_hi(shape, f0, q, fs, ctx=1.0):
    if shape == "bell":
        sq3 = np.sqrt(3.0) / q
        demi = np.log2((sq3 + np.sqrt(sq3 ** 2 + 4)) / 2)
        lo, hi = f0 / 2 ** (demi + ctx), f0 * 2 ** (demi + ctx)
    elif shape == "highshelf":
        lo, hi = f0 / 2 ** ctx, 0.45 * fs
    else:
        lo, hi = 25.0, f0 * 2 ** ctx
    return max(lo, 20.0), min(hi, 0.45 * fs)


class Shape5:
    def __init__(self, fs, cible="transitoires", shape="bell", f0=200.0, q=0.7, gain_db=6.0, att_periods=None, time_ms=None, sens=0.85, look=LOOK):
        self.fs, self.cible, self.A, self.look = fs, cible, 10.0 ** (gain_db / 20.0), look
        self.b, self.a = zone_filter(shape, fs, f0, q)
        # banc léger
        f = 30.0 * 2.0 ** (np.arange(0, 100) / PER_OCT)
        self.f = f = f[f < 0.45 * fs]
        qb = 1.0 / (2.0 ** (1.0 / (2 * PER_OCT)) - 2.0 ** (-1.0 / (2 * PER_OCT)))
        self.K = len(f)
        self.cb = [rbj_bandpass0db(fs, fk, qb) for fk in f]
        self.ce = np.exp(-1.0 / (np.maximum(0.002, 2.0 / f) * fs))
        self.zb_k = [np.zeros(2) for _ in range(self.K)]
        self.ze_k = [np.zeros(1) for _ in range(self.K)]
        lo, hi = zone_lo_hi(shape, f0, q, fs, 1.5)
        c = np.where((f >= lo) & (f <= hi))[0]
        if len(c) < 3:
            c = np.argsort(np.abs(np.log2(f / f0)), kind="stable")[:3]
        self.ctx = np.sort(c)
        self.g0 = int(np.searchsorted(f, 60.0))
        tf = float(np.clip(3.0 / f0, 0.005, 0.03))
        self.lag = max(2, int(np.round(tf * fs / DEC)))
        # NLMS et enveloppes du résidu
        self.w, self.buf = np.zeros(ORDRE), np.zeros(ORDRE)
        te = float(np.clip(2.0 / f0, 0.002, 0.01))
        self.cef, self.ces = np.exp(-1.0 / (te * fs)), np.exp(-1.0 / (0.05 * fs))
        self.zef, self.zes = np.zeros(1), np.zeros(1)
        # seuil, tenue, attaque
        self.m0 = (10.0 - 9.0 * sens) * M0_ECHELLE
        self.P = 99.0 - 12.0 * sens
        self.R = int(np.round(2.0 * fs / (DEC * PAS_ANNEAU)))
        self.anneau = []
        self.pousses, self.qhold = 0, 0.0
        tr = (time_ms if (time_ms and time_ms > 0) else TIME_DEFAUT_MS) / 1000.0 / 3.0
        self.c_rel = np.exp(-DEC / (tr * fs))
        if att_periods is None:
            att_periods = float(np.clip(0.45 + 0.35 * np.log2(f0 / 60.0) / np.log2(250.0 / 60.0), 0.45, 0.8))
        self.c_att = np.exp(-1.0 / (max(att_periods / f0, 1.0 / fs) * fs))
        self.zb, self.z_att = np.zeros(2), np.zeros(1)
        self.H = None                                     # anneau des `lag` dernières trames de niveaux
        self.fc, self.cnt, self.yH = 0, 0, 0.0
        self.tail = np.zeros(look)                        # b retardé de `look`

    def _nlms(self, b):
        e = np.empty(len(b))
        w, buf = self.w, self.buf
        for i in range(len(b)):
            err = b[i] - w @ buf
            e[i] = err
            w = w + (MU / (buf @ buf + 1e-9)) * err * buf
            buf = np.concatenate([[b[i]], buf[:-1]])
        self.w, self.buf = w, buf
        return e

    def _trame(self, L, sC):
        """Une trame décimée : force D → seuil adaptatif → poids tenu."""
        if self.H is None:
            self.H = [L.copy() for _ in range(self.lag)]
        ref = self.H[0]
        self.H = self.H[1:] + [L]
        refm = np.maximum(np.maximum(ref, np.concatenate([ref[:1], ref[:-1]])), np.concatenate([ref[1:], ref[-1:]]))
        up = np.maximum(L - refm, 0.0)
        s_ctx = up[self.ctx].mean()
        s_glob = up[self.g0:].mean()
        sB = max(s_ctx, s_glob) * np.clip((L[self.ctx].max() + 95.0) / 10.0, 0.0, 1.0)
        sD = np.sqrt(max(sB, 0.0) * max(sC, 0.0) / 3.0)
        if self.fc % PAS_ANNEAU == 0:
            self.anneau.append(sD)
            if len(self.anneau) > self.R:
                self.anneau.pop(0)
            if self.pousses % RECALC == 0:
                v = np.sort(np.array(self.anneau))
                self.qhold = v[min(len(v) - 1, int(len(v) * self.P / 100.0))]
            self.pousses += 1
        self.fc += 1
        m0e = max(self.m0, self.qhold)
        T = float(np.clip((sD - m0e) / LARGEUR, 0.0, 1.0))
        self.yH = max(T, self.c_rel * self.yH)
        return self.yH

    def detecte(self, x):
        """Renvoie (b_retardé, Tl) : signal de zone retardé de `look` et poids transitoire lissé (avant le choix transitoires / sustain)."""
        n = len(x)
        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)
        idx = np.arange((-self.cnt) % DEC, n, DEC)
        m = len(idx)
        Lk = np.empty((self.K, m))
        for k in range(self.K):
            bk, self.zb_k[k] = lfilter(*self.cb[k], x, zi=self.zb_k[k])
            ef, self.ze_k[k] = lfilter([1 - self.ce[k]], [1, -self.ce[k]], np.abs(bk), zi=self.ze_k[k])
            Lk[k] = 20.0 * np.log10(ef[idx] * (np.pi / 2) + 1e-12)
        e = self._nlms(b)
        Ef, self.zef = lfilter([1 - self.cef], [1, -self.cef], np.abs(e), zi=self.zef)
        Es, self.zes = lfilter([1 - self.ces], [1, -self.ces], np.abs(e), zi=self.zes)
        sC = 20.0 * np.log10((Ef[idx] + 1e-12) / (Es[idx] + 1e-12)) * np.clip((20.0 * np.log10(Ef[idx] * (np.pi / 2) + 1e-12) + 95.0) / 10.0, 0.0, 1.0)
        yh = np.empty(m)
        for j in range(m):
            yh[j] = self._trame(Lk[:, j], sC[j])
        pos = np.full(n, -1)
        pos[idx] = np.arange(m)
        ff = np.maximum.accumulate(pos)
        zoh = np.where(ff >= 0, yh[np.maximum(ff, 0)], self.yH_prev if hasattr(self, "yH_prev") else 0.0)
        if m > 0:
            self.yH_prev = yh[-1]
        Tl, self.z_att = lfilter([1 - self.c_att], [1, -self.c_att], zoh, zi=self.z_att)
        self.cnt += n
        ext = np.concatenate([self.tail, b])
        self.tail = ext[n:] if self.look > 0 else self.tail
        bd = ext[:n] if self.look > 0 else b
        return bd, Tl

    def applique(self, x, b, Tl, keep=False):
        poids = Tl if self.cible == "transitoires" else 1.0 - Tl
        g = 1.0 + (self.A - 1.0) * poids
        y = x + (g - 1.0) * b
        return (y, g) if keep else y

    def process(self, x, keep=False):
        b, Tl = self.detecte(x)
        return self.applique(x, b, Tl, keep)


def shape5_band(x, fs, cible="transitoires", shape="bell", f0=200.0, q=0.7, gain_db=6.0, block=8192, diag=False, time_ms=None, sens=0.85, look=LOOK, **_):
    """x ALIGNÉ : le résultat est la sortie de la bande alignée sur x retardé de `look` (comme l'assemblage)."""
    if gain_db == 0.0:
        return x.copy()
    s = Shape5(fs, cible, shape, f0, q, gain_db, None, time_ms, sens, look)
    xd = np.concatenate([np.zeros(look), x])[:len(x)]                  # sec retardé
    y = np.empty(len(x))
    gs = []
    for i in range(0, len(x), block):
        out = s.process(x[i:i + block], keep=diag)
        if diag:
            d, g = out
            gs.append(g)
        else:
            d = out
        y[i:i + block] = d - x[i:i + block]                              # delta
    y = xd + y
    return (y, dict(g=np.concatenate(gs))) if diag else y
