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
