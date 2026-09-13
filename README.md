<p align="center">
  <img src="drt_screen_creator/resources/logo-drt.png" alt="Logo Dofus Retro Tools" width="96">
</p>

<h1 align="center">DRT Screen Creator</h1>

<p align="center">
  Application Windows de captures d’écran conçue pour alimenter les contenus de
  <a href="https://dofusretrotools.com">Dofus Retro Tools</a>.
</p>

DRT Screen Creator permet de mémoriser une zone d’écran et de la capturer instantanément avec un raccourci global. Un second raccourci ouvre une sélection libre pour les captures ponctuelles. Les images sont enregistrées localement en JPEG haute qualité et numérotées automatiquement.

## Télécharger l’application

1. Ouvrez la page [Releases](https://github.com/GraveLaFlemme/DRT-Screen-Creator/releases/latest).
2. Dans **Assets**, téléchargez `DRT-Screen-Creator-v1.2.1.zip`.
3. Extrayez entièrement le ZIP dans le dossier de votre choix.
4. Lancez `DRT-Screen-Creator.exe`.

Python et PyCharm ne sont pas nécessaires pour utiliser la version téléchargée.

Une version `portable.exe` est également proposée. Le ZIP contenant le dossier complet reste recommandé, car il est plus facile à diagnostiquer en cas de problème.

> L’application n’étant pas signée numériquement, Windows SmartScreen peut afficher un avertissement au premier lancement. Vérifiez que le fichier vient bien de la Release officielle de ce dépôt.

## Configuration rapide

1. Cliquez sur **Définir la zone**, tracez le rectangle fixe, puis validez avec Entrée.
2. Choisissez le dossier de destination des captures.
3. Saisissez un nom de base, par exemple `quête`.
4. Choisissez deux raccourcis clavier différents.
5. Cliquez sur **Armer la capture**.

Les fichiers sont créés sous la forme suivante :

```text
quête-1.jpg
quête-2.jpg
quête-3.jpg
```

L’application détecte les fichiers déjà présents et reprend automatiquement après le plus grand numéro, sans écraser une ancienne image.

## Les deux modes de capture

### Zone prédéfinie

Le premier raccourci capture immédiatement la zone mémorisée. Il est adapté aux séries de captures qui doivent conserver exactement le même cadrage.

### Capture libre

Le second raccourci assombrit les écrans et permet de tracer une zone temporaire :

- faites glisser la souris pour dessiner la zone ;
- faites glisser un bord ou un coin pour la redimensionner ;
- faites glisser l’intérieur pour la déplacer ;
- cliquez une fois dans la zone, ou appuyez sur Entrée, pour capturer ;
- appuyez sur Échap pour annuler sans créer de fichier ni consommer de numéro.

La sélection libre ne remplace jamais la zone prédéfinie.

## Fonctionnalités

- raccourcis globaux Windows actifs même lorsque l’application est réduite ;
- sélection compatible avec plusieurs moniteurs et coordonnées négatives ;
- JPEG qualité 95 avec sous-échantillonnage 4:4:4 ;
- nom Unicode et numérotation automatique sans écrasement ;
- aperçu de la dernière capture ;
- confirmation visuelle et son de capture personnalisé ;
- accès rapide à l’image et au dossier de destination ;
- fonctionnement dans la zone de notification Windows ;
- détection des changements de résolution, de disposition ou de mise à l’échelle ;
- une seule instance active à la fois.

## Données et confidentialité

L’application fonctionne entièrement en local. Elle ne contient aucun compte utilisateur, suivi, publicité, téléversement ou connexion au site.

La configuration et les journaux sont conservés dans :

```text
%LOCALAPPDATA%\DofusRetroTools\ScreenCreator
```

Les captures restent exclusivement dans le dossier choisi par l’utilisateur.

## Compatibilité

- Windows 10 ou Windows 11, 64 bits ;
- interface en français ;
- Python 3.11 uniquement pour lancer ou construire le projet depuis les sources.

Ce projet est un outil communautaire pour Dofus Retro Tools. Il n’est ni affilié à Ankama ni approuvé par Ankama.

## Licence

Le code source est distribué sous licence [MIT](LICENSE).

## Construire l’application soi-même

Clonez le dépôt puis ouvrez PowerShell dans son dossier :

```powershell
git clone https://github.com/GraveLaFlemme/DRT-Screen-Creator.git
cd DRT-Screen-Creator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
```

Lancement depuis les sources :

```powershell
.\.venv\Scripts\python.exe main.py
```

Construction de la version dossier recommandée :

```powershell
.\scripts\build.ps1 -Mode onedir
```

Construction de l’EXE portable mono-fichier :

```powershell
.\scripts\build.ps1 -Mode onefile
```

Les fichiers générés apparaissent dans `dist`. Ils ne sont pas suivis par Git.
