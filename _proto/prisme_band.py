"""PRISME — étape 1 : bande « Exciter / Expander » additive complète.

    sortie = entrée + montant · filtre_sortie( résidu_harmoniques( source ) )

  source  : 'auto'  zone SOUS la bande (f0/h, h = harmonique dominante du mode) -> l'harmonique
                    dominante tombe au centre de la bande ;
            'band'  la bande elle-même (comportement Spectre) ;
            'large' tout le signal.
  focus   : filtre de sortie (cloche -> passe-bande, shelf haut -> passe-haut, shelf bas -> passe-bas)
            qui localise l'effet dans la zone de la bande. Défaut : actif sauf source 'band'.
  deemph  : résidu « harmoniques seules » (comme le De-Emphasis de Spectre).
  adaptive: excitation à niveau constant (montée du bas niveau avant la courbe, puis retour) =
            principe du chemin latéral Dolby A ; drive = niveau cible à l'entrée de la courbe.
  gain_db : > 0 exciter ; < 0 expander (résidu soustrait, ne « tame » PAS).
"""
import numpy as np
from scipy.signal import lfilter, resample_poly
from prisme_dsp import MODES, saturate, dc_block, rbj_bandpass0db, random_shift

H_DOMINANT = {"triode": 2, "diode": 2, "iron": 3, "classa": 3, "rect": 2}


def rbj_lowpass(fs, f0, q=0.7071):
    w0 = 2 * np.pi * f0 / fs
    al = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    b = np.array([(1 - c) / 2, 1 - c, (1 - c) / 2])
    a = np.array([1 + al, -2 * c, 1 - al])
    return b / a[0], a / a[0]


def rbj_highpass(fs, f0, q=0.7071):
    w0 = 2 * np.pi * f0 / fs
    al = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    b = np.array([(1 + c) / 2, -(1 + c), (1 + c) / 2])
    a = np.array([1 + al, -2 * c, 1 - al])
    return b / a[0], a / a[0]


def zone_filter(shape, fs, f0, q):
    if shape == "bell":
        return rbj_bandpass0db(fs, f0, q)
    if shape == "highshelf":
        return rbj_highpass(fs, f0)
    return rbj_lowpass(fs, f0)


# AGC d'entrée de l'Exciter (2026-09-25) : le plafond historique de +24 dB était atteint presque tout le temps sur les bandes médiums (réglage « Saturation » sans effet,
# delta très pointu = crépitements) ; enveloppe plus rapide (10 ms), montée jusqu'à +40 dB, descente jusqu'à 0,05.
AGC_TAU, AGC_GMIN, AGC_GMAX_DB = 0.01, 0.05, 40.0


def rbj_shelf(fs, f0, gain_db, haut):
    """Shelf RBJ (pente S = 1) : `haut` True = shelf aigu, False = shelf grave."""
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / fs
    c, s_ = np.cos(w0), np.sin(w0)
    al = s_ / 2.0 * np.sqrt((A + 1.0 / A) * (1.0 / 1.0 - 1.0) + 2.0)
    t = 2.0 * np.sqrt(A) * al
    if haut:
        b = np.array([A * ((A + 1) + (A - 1) * c + t), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - t)])
        a = np.array([(A + 1) - (A - 1) * c + t, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - t])
    else:
        b = np.array([A * ((A + 1) - (A - 1) * c + t), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - t)])
        a = np.array([(A + 1) + (A - 1) * c + t, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - t])
    return b / a[0], a / a[0]


TILT_DB = 9.0        # pente totale (basses ↔ aigus) de l'Exciter en mode Bande pour un tilt de ±1


def tilt_pivot(shape, f0, fs):
    return min(0.4 * fs, f0 * 2.5) if shape == "highshelf" else max(40.0, f0 / 2.5) if shape == "lowshelf" else f0


def adapt_gain(s, fs, target, gmax_db=AGC_GMAX_DB, tau=AGC_TAU, tau_fast=None, gmin=AGC_GMIN):
    """Gain montant seulement : ramène l'enveloppe crête estimée de s vers `target`.

    tau_fast : si donné, enveloppe = max(lente, rapide) -> attaque rapide, relâchement lent.
    Sans elle, l'attaque suit la constante lente : à l'attaque d'une percussion le gain reste
    énorme quelques ms et sature la transitoire.
    """
    a = np.exp(-1.0 / (tau * fs))
    env = lfilter([1 - a], [1, -a], np.abs(s)) * (np.pi / 2)
    if tau_fast:
        b = np.exp(-1.0 / (tau_fast * fs))
        env = np.maximum(env, lfilter([1 - b], [1, -b], np.abs(s)) * (np.pi / 2))
    return np.clip(target / np.maximum(env, 1e-9), gmin, 10 ** (gmax_db / 20))


def null_coef(y, s, fs, tau=0.03):
    """Coefficient c(t) minimisant |y - c·s|² sur une fenêtre glissante (projection)."""
    a = np.exp(-1.0 / (tau * fs))
    num = lfilter([1 - a], [1, -a], y * s)
    den = lfilter([1 - a], [1, -a], s * s) + 1e-12
    return num / den


def excite_band(x, fs, shape="bell", f0=12000.0, q=0.7, gain_db=6.0, mode="iron",
                source="auto", drive=0.5, adaptive=True, deemph=True, focus=None,
                adaa=True, oversample=1, norm=False, ratio_ref=0.25, src_q=2.0, floor_ratio=0.05, phase="none", out_sections=2, tau_fast=None, norm_tau=0.2, spread_hz=0.0, rate_hz=3.0, seed=0, win_lo_div=None, win_hi_mul=1.5, null_tau=0.03, low_hp_ratio=None):
    if focus is None:
        focus = source != "band"
    # --- source
    if source == "auto":
        h = H_DOMINANT[mode]
        fs_src = max(f0 / h, 60.0)
        # source sélective (2 sections en cascade, Q ≥ src_q) : elle ne doit pas laisser passer la
        # zone de sortie, sinon la saturation compresse ce contenu et l'ajout devient une coupe
        zf = zone_filter(shape, fs, fs_src, max(q, src_q))
        s0 = lfilter(*zf, lfilter(*zf, x))
    elif source == "window":
        # fenêtre de détection AUTOUR de la zone : corps sous la zone (f0/lo_div) + zone + abords (f0·hi_mul)
        z1 = rbj_highpass(fs, max(f0 / (win_lo_div or H_DOMINANT[mode]), 60.0))
        s0 = lfilter(*z1, lfilter(*z1, x))
        if win_hi_mul:
            z2 = rbj_lowpass(fs, min(f0 * win_hi_mul, 0.45 * fs))
            s0 = lfilter(*z2, lfilter(*z2, s0))
    elif source == "hp":
        # source passe-haut (style Aphex) : le non-linéaire ne voit ni les basses ni les graves
        zf = rbj_highpass(fs, max(f0 / H_DOMINANT[mode], 60.0))
        s0 = lfilter(*zf, lfilter(*zf, x))
    elif source == "band":
        s0 = lfilter(*zone_filter(shape, fs, f0, q), x)
    else:
        s0 = x.copy()
    # --- saturation (niveau adaptatif ou fixe)
    g = adapt_gain(s0, fs, drive, tau_fast=tau_fast) if adaptive else drive
    sin = s0 * g

    def chaine(curve):
        v = resample_poly(sin, oversample, 1) if oversample > 1 else sin
        w = saturate(v, curve, adaa=adaa)
        if oversample > 1:
            w = resample_poly(w, 1, oversample)
            w = w[: len(s0)] if len(w) >= len(s0) else np.pad(w, (0, len(s0) - len(w)))
        return w

    y = chaine(mode)
    if deemph:
        # De-emphasis EXACT : on retire la réponse LINÉAIRE de la même chaîne (suréchantillonnage + ADAA),
        # pas le signal d'entrée. L'ADAA est un filtre de 2 échantillons en régime linéaire (−3 dB à 12 kHz,
        # retard d'un demi-échantillon) : soustraire l'entrée laissait un résidu linéaire énorme en aigu.
        y_lin = chaine("lin")
        if deemph == "sub":
            res = (y - y_lin) / g
        else:                                   # + projection : c(t) ≈ 1 pour les courbes impaires, ≈ 0 pour le redresseur
            c = null_coef(y, y_lin, fs, tau=null_tau)
            res = (y - c * y_lin) / g
    else:
        res = y / g
    res = dc_block(res, fs)
    if spread_hz > 0:
        res = random_shift(res, fs, spread_hz, rate_hz, seed)
    if focus:
        zo = zone_filter(shape, fs, f0, q)
        for _ in range(out_sections):          # 1 section = 6 dB/oct par flanc, 2 = 12 dB/oct
            res = lfilter(*zo, res)
        if low_hp_ratio and shape == "bell":   # flanc bas plus raide (24 dB/oct) : d'où vient la fuite du corps
            zh = rbj_highpass(fs, f0 / low_hp_ratio)
            for _ in range(2):
                res = lfilter(*zh, res)
    if phase == "quad":
        # injection en quadrature (90°) : les harmoniques ajoutées ne peuvent pas annuler les
        # partiels déjà présents à la même fréquence (hors ligne : Hilbert FFT, latence à prévoir en temps réel)
        from scipy.signal import hilbert
        res = np.imag(hilbert(res))
    amount = 10 ** (abs(gain_db) / 20.0) - 1.0
    if norm == "zone":
        # Gain « d'air » : les harmoniques valent (montant × contenu RÉEL de la zone d'air), avec un
        # plancher (floor_ratio × corps de la zone source) pour pouvoir en créer dans une zone vide.
        # Le niveau vient de la zone, la couleur de la courbe -> les modes se comparent à volume égal.
        a = np.exp(-1.0 / (norm_tau * fs))
        zr = zone_filter(shape, fs, max(f0 / H_DOMINANT[mode], 60.0), max(q, src_q))
        s_ref = s0 if source == "auto" else lfilter(*zr, lfilter(*zr, x))
        rs = np.sqrt(lfilter([1 - a], [1, -a], s_ref * s_ref))
        zb = lfilter(*zone_filter(shape, fs, f0, q), x)
        rz = np.sqrt(lfilter([1 - a], [1, -a], zb * zb))
        rr = np.sqrt(lfilter([1 - a], [1, -a], res * res))
        target = amount * np.maximum(rz, floor_ratio * rs)
        res = res * np.clip(target / np.maximum(rr, 1e-9), 0.0, 100.0)
        return x + np.sign(gain_db) * res
    if norm:
        # Gain « d'air » : niveau des harmoniques ramené à ratio_ref × niveau de la source,
        # quelle que soit la courbe -> les modes se comparent en couleur, pas en volume.
        a = np.exp(-1.0 / (0.2 * fs))
        # référence = corps sonore de la zone source « Auto » (indépendante du réglage Source,
        # sinon 'large' prendrait les basses fortes pour référence)
        if source == "auto":
            s_ref = s0
        else:
            zr = zone_filter(shape, fs, max(f0 / H_DOMINANT[mode], 60.0), max(q, src_q))
            s_ref = lfilter(*zr, lfilter(*zr, x))
        rs = np.sqrt(lfilter([1 - a], [1, -a], s_ref * s_ref))
        rr = np.sqrt(lfilter([1 - a], [1, -a], res * res))
        res = res * np.clip(ratio_ref * rs / np.maximum(rr, 1e-9), 0.0, 100.0)
    return x + np.sign(gain_db) * amount * res
