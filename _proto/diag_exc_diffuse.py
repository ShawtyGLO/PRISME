"""Exciter DIFFUS (à la Aural Exciter) : le wet traverse une chaîne de passe-tout (dispersion de phase) — mêmes amplitudes, transitoires étalés.
Mesures : crête/RMS du wet, retard de groupe ; rendus comparatifs dans renders/exciter_diffus."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import sosfilt
from scipy.io import wavfile
import prisme_exciter_stream as ES
from diag_exc_multi import multi
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")


def apf_sos(fs, fc, q):
    w0 = 2 * np.pi * fc / fs
    al = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    b = np.array([1 - al, -2 * c, 1 + al])
    a = np.array([1 + al, -2 * c, 1 - al])
    return np.concatenate([b / a[0], a / a[0]])


def dispersion(x, fs, n=10, fmin=600.0, fmax=14000.0, q=0.7, decal=0.0):
    """n passe-tout d'ordre 2 répartis en log entre fmin et fmax (decal : décalage en octaves, pour décorréler un canal de l'autre)."""
    fcs = fmin * (fmax / fmin) ** (np.arange(n) / (n - 1)) * 2 ** decal
    sos = np.array([apf_sos(fs, min(f, 0.45 * fs), q) for f in fcs])
    return sosfilt(sos, x)


def crest(y):
    return np.max(np.abs(y)) / np.sqrt(np.mean(y ** 2))


if __name__ == "__main__":
    fs, x = load(SRC)
    x = x[int(30 * fs): int(48 * fs)]
    D = ES.D_OS
    peak = np.max(np.abs(x))
    dry = np.concatenate([np.zeros((D, 2)), x[:-D]])
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "exciter_diffus")

    def ecrit(nom, y):
        wavfile.write(os.path.join(out, nom + ".wav"), int(fs), (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))

    ecrit("00_sec", dry)
    for tag, kw in (("bell3k_iron_+2,4", dict(f0=3000.0, mode="iron", gain=2.4)), ("shelf9,6k_iron_+5", dict(f0=9600.0, mode="iron", gain=5.0, shape="highshelf"))):
        for K in (1, 4):
            w = [multi(np.ascontiguousarray(x[:, c]), fs, K=K, **kw) for c in (0, 1)]
            base = np.stack(w, axis=1)
            print(f"{tag} K={K} : crête/RMS wet {crest(base[int(fs):, 0]):5.1f}", end="")
            for n, q in ((6, 0.7), (12, 0.7), (12, 1.5)):
                dd = np.stack([dispersion(w[c], fs, n=n, q=q) for c in (0, 1)], axis=1)
                print(f" | {n} passe-tout Q{q}: {crest(dd[int(fs):, 0]):5.1f}", end="")
            print()
            ecrit(f"{tag}_K{K}_sans_diffusion", dry + base)
            dd = np.stack([dispersion(w[c], fs, n=12, q=0.7) for c in (0, 1)], axis=1)
            ecrit(f"{tag}_K{K}_diffus_12x", dry + dd)
            ecr = np.stack([dispersion(w[0], fs, n=12, q=0.7), dispersion(w[1], fs, n=12, q=0.7, decal=0.25)], axis=1)
            ecrit(f"{tag}_K{K}_diffus_12x_large", dry + ecr)
    print(sorted(os.listdir(out)))
