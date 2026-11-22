# Gestionnaire de polices (Windows)

Petit logiciel pour **voir, trier, installer et désinstaller** ses polices.

## Lancer
1. Installer Python (https://www.python.org, cocher « Add Python to PATH »).
2. Double-cliquer sur **Lancer.bat** (installe Pillow + rarfile au premier lancement).

Astuce : glisser des `.zip`/`.ttf` sur `Lancer.bat` les propose directement à l'installation.

## Fonctions
- Liste de toutes les polices avec aperçu de votre texte, taille réglable.
- Recherche, filtres (Favoris / Installées par moi / Système), tri (nom, type, fichier, taille).
- Panneau de détail : alphabet, chiffres, accents, plusieurs tailles.
- Favoris : double-clic ou touche **F**. Multi-sélection : Ctrl/Maj + clic. Flèches pour naviguer.
- Désinstaller : bouton ou touche **Suppr** (polices système = lancer en administrateur).
- Installer depuis **.ttf .otf .ttc .zip .rar .7z** (archives imbriquées ok), avec aperçu avant
  installation et doublons ignorés. Installation pour l'utilisateur courant, sans droits admin.
- RAR/7z : utilise 7-Zip s'il est installé (recommandé : https://www.7-zip.org).

## Nouveautés
- **Mode sombre** : bouton 🌙 / ☀ en haut à droite (mémorisé).
- **Mise à jour intégrée** (exe) : vérifie GitHub au démarrage + bouton « ⬆ Mise à jour ».
  Télécharge le nouvel exe, le remplace et relance tout seul.
- **Filtre Doublons** : polices installées en plusieurs fichiers.
- **Exporter…** : copie les fichiers des polices sélectionnées (ou affichées) dans un dossier (sauvegarde).
- **Ctrl+C** : copie le nom des polices sélectionnées.

Télécharger l'exe : https://github.com/Pierro0871/FontManager/releases/latest

## Version 3
- **Glisser-déposer** des .ttf/.otf/.zip/.rar directement dans la fenêtre.
- **📁 Collections** : vos groupes (« Logo », « Projet X »…), filtre « 📁 nom ».
- **⚡ Tri rapide** : une police à la fois — ← jeter, → garder, ↑ favori, ⌫ annuler, Échap terminer.
- **Filtre Style** : Serif, Sans, Script, Déco, Mono, Symbole, Gras, Italique (détection auto, pas toujours juste).
- **⚖ Comparer** 2 à 4 polices côte à côte (Ctrl+clic pour sélectionner).
- **Couleurs de l'aperçu** : boutons A (texte), ▇ (fond), ↺ (par défaut).
- **🔤 Tous les caractères** : grille de tous les signes, clic = copier.
- **Licence** : auteur, licence, intégration et usage commercial (deviné depuis le texte de licence : à vérifier).
- **♻ Corbeille** : les polices désinstallées sont gardées, bouton Restaurer.
- **🔒 Protection** : les polices dont Windows a besoin (Segoe, Arial, Calibri…) ne peuvent pas être supprimées.

## Collections (v1.7)
La colonne de gauche montre une grosse case de couleur par collection, avec son nombre de familles. Un clic affiche seulement cette collection.

Pour ranger une police :
- touche **1 à 9** : met la sélection dans la collection du même numéro, ou l'en retire si elle y est déjà ;
- **clic droit** sur une police : cocher les collections, ou en créer une ;
- **glisser** une police sur la case d'une collection.

Toute la famille suit : ranger Roboto range aussi Roboto Bold, Italic, Light.

La liste montre une ligne par famille ; la flèche ▸ (ou la touche →) affiche ses styles. Chaque police rangée porte la couleur de sa collection : bande à gauche, fond teinté, pastille avec le nom.

Clic droit sur une case de collection : renommer, changer la couleur, exporter en zip, réinstaller depuis la corbeille, tout désinstaller, vider, supprimer.

Le tri rapide marche par famille ; les touches 1 à 9 y rangent aussi la famille affichée.

## Trier (v1.8)
- **Non rangées** : case sous « Toutes les polices ». Elle montre les familles qui ne sont dans aucune collection. Une police rangée quitte la liste et la suivante est sélectionnée, donc il suffit d'enchaîner les touches 1 à 9.
- **Glisser** : un aperçu de la police suit la souris, et la case de collection visée s'encadre.
- **Collections de départ**, créées une seule fois : Titres, Texte courant, Manuscrite, Logo, Fun & déco, Rétro, Pro & sobre, À supprimer. Clic droit sur une case pour la renommer ou la supprimer.

## Droits (v1.9)
Chaque police porte un badge de couleur avec ses droits, classés comme sur DaFont : Domaine public, Libre (OFL, Apache…), 100% gratuite, Fournie par Windows, Donationware, Shareware, Usage personnel, Démo, Commerciale, Inconnue.
- Tri « Droits » : les plus libres d'abord.
- Filtre « Droits : … » pour ne voir qu'une catégorie.
- Le panneau de droite explique ce que la catégorie permet.

Le classement est deviné à partir du texte de licence rangé dans le fichier. Pour un projet client, vérifiez sur le site de l'auteur.
