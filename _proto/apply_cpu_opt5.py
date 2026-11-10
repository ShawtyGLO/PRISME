"""Optimisation CPU 5 (2026-11-09), SANS changement de son : __restrict sur les pointeurs des boucles par bande (Tame analyse/synthese, Shape banc) :
le compilateur vectorise (AVX2, 4 doubles) des boucles dont les iterations sont INDEPENDANTES (une bande = une case). Memes operations, meme ordre : bit-identique."""
import os, re
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")
def edit(path, pairs):
    p = os.path.join(SRC, path); s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:80]); s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)
edit("Dsp/Tame.h", [
 ("        double* z1 = aZ1.data(); double* z2 = aZ2.data(); double* pef = ef.data(); double* pes = es.data();\n        const double *b0 = aB0.data(), *b1 = aB1.data(), *b2 = aB2.data(), *a1 = aA1.data(), *a2 = aA2.data();\n        const double *pcf = cf.data(), *pcs = cse.data(), *ocf = aOmCf.data(), *ocs = aOmCs.data();",
  "        double* __restrict z1 = aZ1.data(); double* __restrict z2 = aZ2.data(); double* __restrict pef = ef.data(); double* __restrict pes = es.data();\n        const double* __restrict b0 = aB0.data(); const double* __restrict b1 = aB1.data(); const double* __restrict b2 = aB2.data(); const double* __restrict a1 = aA1.data(); const double* __restrict a2 = aA2.data();\n        const double* __restrict pcf = cf.data(); const double* __restrict pcs = cse.data(); const double* __restrict ocf = aOmCf.data(); const double* __restrict ocs = aOmCs.data();"),
 ("        double *cp = cPrev.data(), *cc = cCur.data(), *tm = term.data(), *sz1 = sZ1.data(), *sz2 = sZ2.data();\n        const double *sb0 = sB0.data(), *sb1 = sB1.data(), *sb2 = sB2.data(), *sa1 = sA1.data(), *sa2 = sA2.data();",
  "        double* __restrict cp = cPrev.data(); double* __restrict cc = cCur.data(); double* __restrict tm = term.data(); double* __restrict sz1 = sZ1.data(); double* __restrict sz2 = sZ2.data();\n        const double* __restrict sb0 = sB0.data(); const double* __restrict sb1 = sB1.data(); const double* __restrict sb2 = sB2.data(); const double* __restrict sa1 = sA1.data(); const double* __restrict sa2 = sA2.data();"),
])
edit("Dsp/Shape.h", [
 ("            double* z1 = bZ1.data(); double* z2 = bZ2.data(); double* pef = ef.data();\n            const double *b0 = bB0.data(), *b1 = bB1.data(), *b2 = bB2.data(), *a1 = bA1.data(), *a2 = bA2.data(), *pce = ce.data(), *poc = omCe.data();",
  "            double* __restrict z1 = bZ1.data(); double* __restrict z2 = bZ2.data(); double* __restrict pef = ef.data();\n            const double* __restrict b0 = bB0.data(); const double* __restrict b1 = bB1.data(); const double* __restrict b2 = bB2.data(); const double* __restrict a1 = bA1.data(); const double* __restrict a2 = bA2.data(); const double* __restrict pce = ce.data(); const double* __restrict poc = omCe.data();"),
])
print("ok")
