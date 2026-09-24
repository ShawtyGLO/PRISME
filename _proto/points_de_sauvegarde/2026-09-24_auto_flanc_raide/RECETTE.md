# Recette — Iron Auto « flanc raide » (2026-09-24)

Voir la note du vault : `Obsidian Vault/PRISME/PRISME Points de sauvegarde.md` (recette détaillée, caractère sonore, chiffres).

Rejouer :
    python render5.py            # rendus par mode de canal (Auto flanc raide, +5 dB)
    python bench_mastering.py    # chiffres du tableau (sec vs rendus)

Paramètres de la bande (excite_band) :
    mode="iron", source="auto", f0=12000, q=2.0, gain_db=5.0, drive=1.5, oversample=2,
    norm="zone", out_sections=3, deemph=True (projection sur la réponse linéaire de la même chaîne),
    adaptive=True, tau_fast=None, norm_tau=0.2, null_tau=0.03

⚠️ Pas de dépôt git dans PRISME VST : cette copie sert de sauvegarde.
