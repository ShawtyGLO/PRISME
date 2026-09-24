"""« Gomme de saturation » (exciter négatif) — mesures du 2026-09-25.

Question de llg53 : l'exciter négatif peut-il ENLEVER la saturation d'un signal déjà chargé en harmoniques ?
Trois gommes comparées : (1) premier ordre  y = 2x − f(x)  (le gain négatif de l'Exciter) ; (2) inversion itérative  u ← x + u − f(u)  ;
(3) sensibilité à l'accord (profondeur de la gomme d contre celle de la source).
Courbe : Iron  f_d(x) = iron(d·x)/d.  Sinus 1 kHz à 192 kHz (aucun repliement), H3 relatif au fondamental.
"""
import sys
sys.path.append(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "_libs"))
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
fs = 192000
n = fs
t = np.arange(n) / fs
w = np.hanning(n)
iron = lambda x: x / np.sqrt(1 + x * x)
sat = lambda x, d: iron(d * x) / d


def harm(y, k, f0=1000):
    Y = np.abs(np.fft.rfft(y * w))
    return 20 * np.log10(Y[k * f0 - 2:k * f0 + 3].max() / Y[f0 - 2:f0 + 3].max() + 1e-30)


def inverse(x, d, it):
    u = x.copy()
    for _ in range(it):
        u = x + u - sat(u, d)
    return u


print("1) Premier ordre : y = 2x − f_d(x), source saturée avec d = 2 — H3 avant → après (dB)\n")
print(f"{'gomme d':>9s}" + "".join(f"{'niveau ' + str(a):>20s}" for a in (0.2, 0.4, 0.8)))
for d in (1.0, 1.4, 2.0, 2.4, 2.8, 4.0):
    row = f"{d:9.1f}"
    for a in (0.2, 0.4, 0.8):
        x = sat(a * np.sin(2 * np.pi * 1000 * t), 2.0)
        row += f"{harm(x, 3):9.1f} →{harm(2 * x - sat(x, d), 3):7.1f}   "
    print(row)
print("\n2) Inversion itérative, saturation FORTE (niveau 0,8 ; H3 source −17 dB) — H3 après")
u0 = 0.8 * np.sin(2 * np.pi * 1000 * t)
x = sat(u0, 2.0)
print(f"{'gomme d':>9s}" + "".join(f"{f'{it} itér.':>10s}" for it in (1, 2, 4, 8, 16)))
for d in (1.4, 1.7, 2.0, 2.4, 2.8):
    print(f"{d:9.1f}" + "".join(f"{harm(inverse(x, d, it), 3):10.1f}" for it in (1, 2, 4, 8, 16)))
print("\n3) Accord (110/220/330/440 Hz) saturé (d = 2) puis gommé : énergie parasite / énergie des partiels (dB)")
f_p = [110, 220, 330, 440]
u = sum(0.12 * np.sin(2 * np.pi * f * t + i) for i, f in enumerate(f_p))
x2 = sat(u, 2.0)


def parasite(z):
    Z = np.abs(np.fft.rfft(z * w)) ** 2
    ok = sum(Z[f - 3:f + 4].sum() for f in f_p)
    return 10 * np.log10((Z[50:8000].sum() - ok) / ok)


print(f"  avant {parasite(x2):.1f} dB")
for d in (1.7, 2.0, 2.4):
    print(f"  d = {d} : " + "  ".join(f"{it} itér. {parasite(inverse(x2, d, it)):.1f}" for it in (1, 2, 4, 8)))
print("\nConclusion : exacte quand la courbe ET la profondeur sont accordées ; l'itération diverge si la gomme est trop profonde ;")
print("le premier ordre ne convient qu'aux saturations légères. La courbe doit être CONNUE (mémoire nulle) : ce n'est pas un outil aveugle.")
