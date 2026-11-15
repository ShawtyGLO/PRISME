# PRISME

Traitement d'excitation et de mastering en C++ / JUCE, avec un prototype Python et un banc de
mesure complet.

## La démarche

Le projet est construit autour de ses bancs : **une cinquantaine de scripts de mesure et de
rendu** accompagnent le prototype. Chaque réglage retenu est consigné dans un *point de
sauvegarde* qui contient la recette et les commandes pour le rejouer à l'identique.

Exemple, pour le mode « Iron Auto flanc raide » du 24/09/2026 :

    python render5.py          # rendus par mode de canal
    python bench_mastering.py  # chiffres du tableau (sec vs rendus)

Les paramètres exacts de la bande sont notés à côté. N'importe qui peut refabriquer le résultat
et vérifier le chiffre : c'est l'objectif.

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
