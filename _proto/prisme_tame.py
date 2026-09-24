"""PRISME — type de bande « Tame » (moteur temporel, 2026-09-24), bipolaire, avec largeur de traitement.

Principe (même squelette additif que l'Exciter) :

    sortie = entrée + Σᵢ (gᵢ(t) − 1) · BPᵢ(entrée)

  - la COURBE (cloche / shelf) définit OÙ le Tame agit : poids wᵢ = |H_courbe(fᵢ)| pour chaque bande de la grille ;
  - une grille de bandes étroites (passe-bande RBJ 0 dB) couvre la zone + 1 octave de contexte de chaque côté ;
  - DÉTECTION : niveau de chaque bande (enveloppe attaque rapide / relâchement lent) comparé à la MOYENNE (en dB) de ses
    voisines. Ce qui dépasse le voisinage de plus de `thresh_db` est une résonance ; l'excès est l'unité de travail, donc
    indépendant du niveau d'entrée ;
  - LARGEUR DE TRAITEMENT `width` ∈ [0, 1] : résolution de la grille, 2 bandes/octave (0 = large, ressemble à un EQ
    dynamique) à 12 bandes/octave (1 = fin, précis, suit chaque pic) ;
  - BIPOLAIRE `gain_db` : < 0 supprime les résonances (jusqu'à |gain_db|) ; > 0 les RÉHAUSSE (jusqu'à +gain_db).
"""
import numpy as np
from scipy.signal import lfilter, freqz
from scipy.ndimage import uniform_filter1d
from prisme_dsp import rbj_bandpass0db
from prisme_band import zone_filter


def grille(shape, f0, q, width, fs, ctx=1.0):
    """Fréquences centrales, Q de chaque bande et poids de zone."""
    R = 2.0 * 6.0 ** width                                     # bandes par octave : 2 (large) → 12 (fin)
    if shape == "bell":
        sq3 = np.sqrt(3.0) / q                                 # demi-largeur à −6 dB de la cloche, en octaves
        demi = np.log2((sq3 + np.sqrt(sq3 ** 2 + 4)) / 2)
        lo, hi = f0 / 2 ** (demi + ctx), f0 * 2 ** (demi + ctx)
    elif shape == "highshelf":
        lo, hi = f0 / 2 ** ctx, 0.45 * fs
    else:
        lo, hi = 25.0, f0 * 2 ** ctx
    hi = min(hi, 0.45 * fs)
    n = int(np.ceil(np.log2(hi / lo) * R)) + 1
    f = lo * 2 ** (np.arange(n) / R)
    f = f[f < 0.45 * fs]
    Qi = 1.0 / (2.0 * np.sinh(np.log(2.0) / (2.0 * R)))
    b, a = zone_filter(shape, fs, f0, q)
    _, h = freqz(b, a, worN=2 * np.pi * f / fs)
    # somme complexe du banc au centre de chaque bande : le banc ne somme pas à 1 (recouvrement + phases), donc
    # (g − 1) appliqué à une seule bande agirait à moitié. On corrige de S_i = Re(Σ_j H_j(f_i)).
    S = np.zeros(len(f))
    w_c = 2 * np.pi * f / fs
    for fj in f:
        _, hj = freqz(*rbj_bandpass0db(fs, fj, Qi), worN=w_c)
        S += hj.real
    return f, Qi, np.abs(h), R, np.maximum(S, 0.3)


def tame_band(x, fs, shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=0.5, thresh_db=3.0, ratio=None, ctx=1.0, diag=False):
    """Tame bipolaire. gain_db < 0 : supprime les résonances ; > 0 : les réhausse. width : 0 large … 1 fin."""
    if gain_db == 0.0:
        return x.copy()
    f, Qi, w, R, S = grille(shape, f0, q, width, fs, ctx)
    N, T = len(f), len(x)
    depth = abs(gain_db)
    if ratio is None:                                          # plus la profondeur choisie est grande, plus la détection est ferme
        ratio = float(np.clip(depth / 4.5, 1.0, 3.0))          # (mesuré : −9 dB → rapport 2 ≈ −6,5 dB sur un pic de +10 dB, bruit seul ≤ 0,07 dB)
    # ---- 1re passe : niveaux (dB) de chaque bande, enveloppe attaque rapide / relâchement lent
    L = np.empty((N, T), dtype=np.float32)
    for i in range(N):
        bi = lfilter(*rbj_bandpass0db(fs, f[i], Qi), x)
        ab = np.abs(bi)
        tf = max(0.005, 3.0 / f[i], Qi / (np.pi * f[i]))
        ts = max(0.06, 8.0 / f[i])
        af, as_ = np.exp(-1.0 / (tf * fs)), np.exp(-1.0 / (ts * fs))
        env = np.maximum(lfilter([1 - af], [1, -af], ab), lfilter([1 - as_, ], [1, -as_], ab)) * (np.pi / 2)
        L[i] = 20 * np.log10(env + 1e-12)
    # ---- excès par rapport à la moyenne (dB) des voisines, hors la bande elle-même
    # fenêtre de référence proportionnelle à la largeur de traitement : large = ±1,5 octave (voit les bosses larges),
    # fin = ±0,5 octave (ne réagit qu'aux pics étroits)
    m = max(2, int(round(R * (0.5 + (1.0 - width)))))
    size = 2 * m + 1
    moy = uniform_filter1d(L, size=size, axis=0, mode="nearest")
    ref = (moy * size - L) / (size - 1)
    seuil = thresh_db - 1.0 * (1.0 - width)                     # large : 2 dB, fin : 3 dB (la moyenne large atténue l'excès)
    exces = np.maximum(L - ref - seuil, 0.0) * ratio
    diag_exces = exces.mean(axis=1)
    del L, moy, ref
    red = np.minimum(exces, depth)
    del exces
    red *= (1.0 if gain_db > 0 else -1.0) * w[:, None].astype(np.float32)          # zone : pondération par la courbe
    asm = np.exp(-1.0 / (0.004 * fs))
    red = lfilter([1 - asm], [1, -asm], red, axis=1).astype(np.float32)             # lissage 4 ms
    diag_red = red.mean(axis=1)
    # ---- 2e passe : application additive (g − 1) · BPᵢ(x)
    y = x.astype(np.float64).copy()
    for i in range(N):
        if w[i] < 0.02:
            continue
        bi = lfilter(*rbj_bandpass0db(fs, f[i], Qi), x)
        # Pas de division par S[i] : la somme complexe du banc (S ≈ 1,65) ne vaut que pour un gain appliqué à TOUTES les bandes ;
        # pour un pic isolé (une ou deux bandes actives), (g − 1)·BPᵢ est exact au centre de la bande.
        y += (10.0 ** (red[i].astype(np.float64) / 20.0) - 1.0) * bi
    if diag:
        return y, dict(f=f, S=S, w=w, exces=diag_exces, red=diag_red)
    return y
