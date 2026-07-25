# Portail des Stages & Alternances | IUT de Nice

Ce document explique le fonctionnement et l'utilisation du système de collecte et de diffusion des offres de stages et d'alternances pour l'IUT de Nice Côte d'Azur. 

Ce système a été conçu pour être entièrement gérable par les responsables pédagogiques via un fichier Google Sheets, sans aucune manipulation technique requise au quotidien.

---

## Liens d'accès rapides

* Le Portail Web (Étudiants) : [iut-nice-offre-etudiante.vercel.app](https://iut-nice-offre-etudiante.vercel.app/)
* Le Tableau de Configuration (Enseignants) : [CONFIG_FORMATIONS](https://docs.google.com/spreadsheets/d/1DNQZRR55YODMen7NSfEKrmGR9ygSd9yIda0S5-X-TVU/edit)
* Le Code Source (GitHub) : [github.com/timeogueusquin/iut-nice-offre-etudiante](https://github.com/timeogueusquin/iut-nice-offre-etudiante)

---

## Comment fonctionne le système (en 3 étapes)

Le fonctionnement est entièrement automatisé et suit un cycle quotidien :

1. **Configuration** : Les responsables pédagogiques définissent les critères de recherche de leur département dans le fichier Google Sheets (mots-clés, compétences, exclusions).
2. **Collecte automatique** : Chaque nuit, un programme s'exécute automatiquement dans le cloud. Il interroge les plateformes partenaires (France Travail, La Bonne Alternance, le CEA, le PASS Fonction Publique et JobHive), filtre les offres selon vos critères et les trie.
3. **Mise en ligne** : Les offres validées sont écrites dans l'onglet correspondant du Google Sheets, puis s'affichent instantanément sur le Portail Web destiné aux étudiants.

---

## Guide pratique pour le responsable de formation

Pour ajuster les offres reçues par vos étudiants, vous devez uniquement intervenir dans la feuille **CONFIG_FORMATIONS** du Google Sheets.

### Comment modifier les critères de votre BUT

Chaque ligne représente un département de l'IUT (SD, INFO, GEA, CS...). Vous pouvez modifier les colonnes suivantes :

* **Codes ROME** : Indiquez les codes métiers officiels (ex: `M1801, M1805`) séparés par des virgules pour cibler les offres de France Travail.
* **Mots exclus titre** : Mots-clés qui rejettent immédiatement une offre si présents dans le titre (ex: `commercial, manager`). Utile pour éliminer les hors-sujets.
* **Compétences** : Les compétences attendues structurées par catégories (ex: `Python: python, pandas; SQL: sql, postgres`). Utilisez des points-virgules pour séparer les catégories.
* **Compétences exigées** : Nombre minimum de compétences distinctes que l'étudiant doit posséder parmi votre liste pour que l'offre soit retenue (valeur par défaut : 2).
* **Mots clés titre** : Termes obligatoires dans le titre de l'offre (ex: `data, analyst`). Si cette colonne est vide (0 requis), le système utilise une recherche par similarité de sens.
* **Mots clés description** : Termes recherchés dans le texte de la description.
* **Activé** : Indiquez `oui` pour que le système cherche des offres pour votre département, ou `non` pour le désactiver.

### Fonctionnalités intelligentes intégrées

* **Traduction automatique** : Il est inutile de doubler vos mots-clés en anglais. Si vous configurez "données", le système cherchera aussi "data". Si vous configurez "developer", il cherchera aussi "développeur".
* **Recherche sémantique par intelligence artificielle** : Si une offre ne contient pas vos mots-clés exacts mais traite précisément du sujet de votre formation (par exemple une offre rédigée avec des synonymes), le système évalue le sens général du texte et retient l'offre si elle correspond à votre profil de formation.
* **Filtre spécifique pour Carrières Sociales (CS)** : Un filtre renforcé élimine automatiquement les offres de communication, de marketing ou de ressources humaines qui polluent souvent les recherches dans ce domaine.
* **Gestion des offres à l'étranger** : Le système identifie automatiquement les offres internationales issues des grands groupes technologiques, les formate (ex: "Londres (Royaume-Uni)") et permet aux étudiants de les filtrer d'un simple clic sur le portail.

---

## Guide d'utilisation du Portail Étudiant

Le Portail Web offre une interface épurée et facile à prendre en main par les étudiants :

* **Filtres**
* **Carte interactive** : Affiche les offres sur une carte de France pour faciliter la recherche par zone géographique.
* **Export de données** : Les étudiants peuvent exporter d'un seul clic leur sélection d'offres sous format CSV pour l'ouvrir dans Excel.
* **Moteur de recherche intelligent** : Recherche floue qui tolère les fautes d'orthographe ou les abréviations.

---

## Règles d'or pour la maintenance du Google Sheet

Pour éviter de bloquer l'exécution automatique nocturne :

* **Ne jamais supprimer ou renommer les colonnes** de la feuille `CONFIG_FORMATIONS`.
* **Ne jamais modifier les codes de département** (`SD`, `INFO`...) de la première colonne.
* Évitez d'utiliser des mots-clés trop généraux comme `stage`, `alternance`, `projet` ou `assistant` qui risquent d'importer des milliers d'offres hors-sujet.

---

<details>
<summary><b>Informations techniques pour les développeurs (Lancement local)</b></summary>

### Configuration des Variables d'environnement

Pour que le pipeline s'exécute automatiquement sur GitHub Actions, vous devez renseigner ces variables dans les paramètres de votre dépôt GitHub (onglet **Settings** > **Secrets and variables** > **Actions** > **New repository secret**) :

#### Secrets à configurer dans GitHub (Production)
*   `GOOGLE_SHEET_ID` : L'identifiant unique de la feuille de calcul Google Sheets. **Format** : Une chaîne de caractères de 44 caractères, visible dans l'adresse URL de votre feuille (ex: `1-Ffp3EySaDaH2vi...`).
*   `GOOGLE_CREDENTIALS_B64` : La clé d'accès (JSON) du compte de service Google encodée en base64 pour être collée sur une seule ligne. **Format** : Une longue chaîne de caractères se terminant parfois par `=` (ex: `ewogICJ0eXBlIjog...`).
*   https://console.cloud.google.com/apis/credentials?authuser=2&project=offres-etudiantes
*   `FRANCE_TRAVAIL_CLIENT_ID` : L'identifiant client pour l'API France Travail (anciennement Pôle Emploi). **Format** : Une clé d'environ 60 caractères alphanumériques (ex: `CLT_a1b2c3d4...`).
*   `FRANCE_TRAVAIL_CLIENT_SECRET` : La clé secrète associée au client de l'API France Travail. **Format** : Une chaîne de 64 caractères hexadécimaux.
*   `LBA_API_TOKEN` : Le jeton de sécurité pour l'API La Bonne Alternance. **Format** : Une clé API sous forme de chaîne de caractères fournie après inscription.

---

#### Pour un lancement en local (Développement)
Si vous souhaitez faire des tests en local sur votre machine, créez un fichier `.env` à la racine du projet avec ces valeurs :
```env
GOOGLE_SHEET_ID="votre_sheet_id"
GOOGLE_APPLICATION_CREDENTIALS="chemin/vers/votre/credentials.json"
FRANCE_TRAVAIL_CLIENT_ID="votre_id"
FRANCE_TRAVAIL_CLIENT_SECRET="votre_secret"
LBA_API_TOKEN="votre_token"
USE_GOOGLE_FORMATION_CONFIG="1"
```

### Démarrage du pipeline Python

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Lancement des collecteurs et de la fusion
python -m src.scrapers.legal_sources_all
python -m src.scrapers.jobhive_source
python -m src.pipeline.merge_artifacts
python -m src.pipeline.fusion_departements
python -m src.pipeline.export
```

### Démarrage du portail Next.js

```bash
cd nextjs-portal
npm install
npm run dev
```

</details>
