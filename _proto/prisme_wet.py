"""PRISME — chemin « wet pur » (proposition de llg53, 2026-09-24).

    wet   = saturation( dry · drive ) / drive          (100 % du signal, aucun filtre, aucune adaptation)
    ajout = courbe( wet − dry )                        (de-emphasis : harmoniques seules ; ou courbe(wet))
    sortie = dry + montant · ajout

La courbe (cloche / shelf) est « ce qu'on garde du wet pour l'ajouter au dry » : effet localisé par
construction, un seul paramètre de niveau (drive), pas de source, pas de normalisation.
"""
import numpy as np
from scipy.signal import lfilter, resample_poly
from prisme_dsp import MODES, saturate, dc_block, random_shift
from prisme_band import zone_filter


def wet_band(x, fs, shape="bell", f0=12000.0, q=2.0, gain_db=5.0, mode="iron", drive=1.0,
             deemph=True, sections=2, oversample=2, adaa=True, spread_hz=0.0, rate_hz=3.0, seed=0):
    sin = x * drive
    if oversample > 1:
        sin = resample_poly(sin, oversample, 1)
    y = saturate(sin, mode, adaa=adaa)
    if oversample > 1:
        y = resample_poly(y, 1, oversample)
        y = y[: len(x)] if len(y) >= len(x) else np.pad(y, (0, len(x) - len(y)))
    y = y / drive
    if deemph:                                  # retire la réponse LINÉAIRE de la même chaîne (ADAA + suréchantillonnage)
        v = resample_poly(x * drive, oversample, 1) if oversample > 1 else x * drive
        yl = saturate(v, "lin", adaa=adaa)
        if oversample > 1:
            yl = resample_poly(yl, 1, oversample)
            yl = yl[: len(x)] if len(yl) >= len(x) else np.pad(yl, (0, len(x) - len(yl)))
        res = y - yl / drive
    else:
        res = y
    res = dc_block(res, fs)
    if spread_hz > 0:
        res = random_shift(res, fs, spread_hz, rate_hz, seed)
    zo = zone_filter(shape, fs, f0, q)
    for _ in range(sections):
        res = lfilter(*zo, res)
    amount = 10 ** (abs(gain_db) / 20.0) - 1.0
    return x + np.sign(gain_db) * amount * res
