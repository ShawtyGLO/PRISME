# PRISME

Traitement d'excitation et de gestion de la dynamique et des détails utilisables en mix comme en mastering en C++ / JUCE, avec un prototype Python et un banc de mesure complet.

Ce plugin peut :

- saturer ;
- augmenter ou diminuer les résonances (comme Soothe) ;
- augmenter ou diminuer les détails sonores (comme de l'upward compression) ;
- augmenter ou diminuer les transients ou les sustains.

Tout cela de manière parallèle et l'interface est utilisables comme un EQ.
  

## La démarche

Le projet est construit autour de ses bancs : **une cinquantaine de scripts de mesure et de
rendu** accompagnent le prototype. Chaque réglage retenu est consigné dans un *point de
sauvegarde* qui contient la recette et les commandes pour le rejouer à l'identique.

Exemple, pour le mode « Iron Auto flanc raide » du 24/09/2026 :

    python render5.py          # rendus par mode de canal
    python bench_mastering.py  # chiffres du tableau (sec vs rendus)

Les paramètres exacts de la bande sont notés à côté. N'importe qui peut refabriquer le résultat
et vérifier le chiffre : c'est l'objectif.

## Ce que mesurent les bancs

| Banc | Ce qu'il isole |
|---|---|
| `bench_ablation` | la contribution réelle d'un étage, en le retirant |
| `bench_alias` | le repliement introduit par la non-linéarité |
| `bench_leak` | la fuite entre bandes du découpage |
| `bench_equilibre` | l'équilibre spectral avant et après |
| `bench_mastering` | la comparaison sec contre rendu, à niveau égalisé |
| `bench_quality`, `bench_scaling` | la tenue en qualité et en charge |

L'ablation est le plus instructif : tant qu'on n'a pas écouté ce que devient le son **sans** un
étage, on ne sait pas ce que cet étage apporte — on sait seulement ce qu'on croit entendre.

## Contenu

| Dossier | Rôle |
|---|---|
| `PRISME/` | le plugin : source C++, projet JUCE |
| `_proto/` | prototype Python, bancs de mesure, points de sauvegarde |

Les rendus audio et les bibliothèques Python vendorisées sont exclus du dépôt : ils se
refabriquent avec les scripts, et ils pèsent plus d'un gigaoctet.

## Construire

Ouvrir `PRISME/PRISME.jucer` dans Projucer, puis compiler sous Visual Studio 2022.
Cible : VST3, Windows 64 bits. Validation avec [pluginval](https://github.com/Tracktion/pluginval).

## Note

Conception, bancs de mesure et validation sont de moi. L'écriture du code s'appuie sur une
assistance IA.

## Droits

© Lucas Lallier-Ginoux. **Tous droits réservés.** Ce dépôt est publié en consultation
uniquement, comme portfolio. Aucune licence d'utilisation, de modification, de redistribution
ou d'exploitation commerciale n'est accordée.
