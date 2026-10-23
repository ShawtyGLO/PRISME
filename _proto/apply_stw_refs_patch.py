"""Patch 2026-10-23 (suite) : références de la largeur stéréo (champ st_width ajouté au fichier de config des bandes, une configuration de plus)."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))


def edit(path, pairs):
    p = os.path.join(HERE, path)
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:90])
        s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)


edit("export_refs.py", [
    ('s.get("hc_f", 20000.0), s.get("hc_pente", 12))) + "\\n")', 's.get("hc_f", 20000.0), s.get("hc_pente", 12), s.get("st_width", 1.0))) + "\\n")'),
    ('for nom, cfg in (("type", config_type()), ("variee", cfg2), ("liee", cfg3), ("filtres", cfg4)):',
     'cfg5 = config_type()\n'
     'cfg5[0].update(type="tame", gain_db=-6.0, canal="stereo", link=0.5, st_width=0.0)\n'
     'cfg5[1].update(type="lift", gain_db=5.0, amount=80.0, canal="stereo", link=0.3, st_width=2.0)\n'
     'cfg5[2].update(type="shape", gain_db=4.0, canal="stereo", link=0.0, st_width=0.4)\n'
     'cfg5[3].update(type="tame", gain_db=-4.0, canal="stereo", link=1.0, st_width=1.6)\n'
     'cfg5[4].update(type="exciter", gain_db=5.0, canal="stereo", st_width=0.3)        # l\'Exciter (delta mono) ignore le curseur\n'
     'for nom, cfg in (("type", config_type()), ("variee", cfg2), ("liee", cfg3), ("filtres", cfg4), ("largeur", cfg5)):'),
])
edit(os.path.join("..", "PRISME", "tests", "test_refs.cpp"), [
    ("double lf0, lq, lg, lw, ltime, lsens, lam, lrel, llink, lpur, llcf, lhcf;", "double lf0, lq, lg, lw, ltime, lsens, lam, lrel, llink, lpur, llcf, lhcf, lstw;"),
    ("llc >> llcf >> llcp >> lhc >> lhcf >> lhcp)", "llc >> llcf >> llcp >> lhc >> lhcf >> lhcp >> lstw)"),
    ("b.hcOn = lhc != 0; b.hcF = lhcf; b.hcPente = lhcp;", "b.hcOn = lhc != 0; b.hcF = lhcf; b.hcPente = lhcp; b.stWidth = lstw;"),
])
print("ok")
