import sys, time, numpy as np
src = open("bench_partage_lift_shape.py", encoding="utf-8").read()
exec(src[:src.index("# =============== QUALITÉ SHAPE")])
import shape_detect_lab as lab

def metrics(w, evts, notes):
    def mx(tl, a, b): return np.mean([w[int((tm + a) * fs):int((tm + b) * fs)].max() for tm in tl])
    hit = mx(evts, -0.001, 0.04)
    head = np.mean([w[int(tm * fs):int((tm + 0.005) * fs)].mean() for tm in evts])
    false = mx(notes, 0.0, 0.1)
    hors = w[(t > 1.0)].mean()
    lag = []
    for tm in evts:
        seg = w[int((tm - 0.01) * fs):int((tm + 0.05) * fs)]
        k = np.argmax(seg >= 0.5) if (seg >= 0.5).any() else None
        if k is not None: lag.append(k / fs * 1000 - 10)
    return hit, head, false, hors, (np.mean(lag) if lag else np.nan)

for nom, f0, evn in (("5 kHz", 5000.0, ("hat", "snare")), ("200 Hz", 200.0, ("kick", "snare"))):
    evts = sorted(sum([drums_t[e] for e in evn], []))
    print("\n=== zone bell %s ; événements : %s ===" % (nom, "+".join(evn)))
    t0 = time.time(); sA, bz = lab.strength_A(x, fs, "bell", f0, 0.7); tA = time.time() - t0
    t0 = time.time(); sB = lab.strength_B(x, fs, "bell", f0, 0.7); tB = time.time() - t0
    t0 = time.time(); sC = lab.strength_C(x, fs, "bell", f0, 0.7, b=bz); tC = time.time() - t0
    sD = np.minimum(sC / 3.0, sB)
    print("  temps de calcul (s, python) A %.2f  B %.2f  C %.2f" % (tA, tB, tC))
    grids = {"A": (sA, [2, 3, 4, 5, 6, 8, 10, 12], 4.0), "B": (sB, [0.5, 1, 1.5, 2, 3, 4, 5, 6], 2.0),
             "C": (sC, [2, 4, 6, 8, 10, 14, 18, 24], 4.0), "D": (sD, [0.5, 1, 1.5, 2, 3, 4, 5, 6], 2.0)}
    for look in (0.0, 3.0, 5.0):
        print("  anticipation %.0f ms :" % look)
        for k, (s, g, wd) in grids.items():
            best = None
            for m0 in g:
                w = lab.weights(s, fs, m0, wd, f0, time_ms=30.0, look_ms=look)
                hit, head, fal, hors, lag = metrics(w, evts, note_t)
                if fal <= 0.10 and (best is None or hit > best[0]): best = (hit, head, fal, hors, lag, m0)
            if best is None:
                w = lab.weights(s, fs, g[-1], wd, f0, time_ms=30.0, look_ms=look); hit, head, fal, hors, lag = metrics(w, evts, note_t); best = (hit, head, fal, hors, lag, g[-1])
            print("    %s (m0 %-4s) : détection %.2f | tête 5 ms %.2f | faux/note %.2f | poids hors événements %.3f | retard %+5.1f ms" % (k, best[5], best[0], best[1], best[2], best[3], best[4]))
