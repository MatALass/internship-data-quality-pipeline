# Pipeline qualité des données de stages

Nettoyage, résolution et enrichissement d'un export brut de ~6 000 stages étudiants EFREI
(identité, entreprise, adresse, programme) en un dataset final exploitable, avec traçabilité
complète des corrections et un système de rapports qualité automatisés.

## Données : un jeu de démonstration fictif

Le dépôt ne contient aucune vraie personne. Le pipeline tourne sur `data/demo/stages_demo_raw.csv`,
un jeu de 6 022 lignes qui garde les défauts de l'export réel sans ses étudiants :

| Opération | Ce qui change | Ce qui est conservé |
|---|---|---|
| Identités fictives | chaque mot d'un nom devient un mot fictif (listes Faker), partout le même | casse, accents, particules, prénoms collés, emails mal découpés, doublons |
| Stages mélangés | entreprise, adresse, ville, intitulé passent à un autre étudiant du même niveau | répartition par entreprise et par programme |
| Numéros de rue | remplacés, identiques pour une même adresse | rue, code postal, ville, pays |

Remplacer les noms par des identifiants ne suffisait pas : l'email contient le nom, et le trio
programme + année + entreprise est unique pour 88 % des lignes de l'export réel.

Sur le jeu de démo, le notebook 01 retrouve presque les mêmes anomalies que sur le réel :

| Catégorie d'identité | Export réel | Démo |
|---|---|---|
| `accents_espaces` | 326 | 326 |
| `prenoms_secondaires` | 66 | 64 |
| `divergence_reelle` | 13 | 15 |
| Prénoms re-segmentés depuis l'email | 29 | 27 |

Le jeu se régénère depuis l'export réel, en local uniquement :

```powershell
python scripts/make_demo_dataset.py          # lit data/raw/stages_efrei_raw.csv (jamais versionné)
```

Le script refuse d'écrire si un nom complet ou un email réel se retrouve dans le résultat, et
recalcule les overrides ciblés par `stage_id` (`config/demo/`) pour qu'ils suivent les stages
déplacés. `tests/test_dataset_privacy.py` vérifie en CI que seul `data/demo/` est versionné et
que tous les noms du jeu viennent des listes fictives.

**Choix du jeu** : `python run_pipeline.py --dataset demo|real|auto` (ou la variable
`STAGES_DATASET`). En `auto`, l'export réel est utilisé s'il est présent dans `data/raw/`, sinon
la démo. `--offline` coupe le géocodage réseau (seuls les caches servent).

> **RGPD, export réel** : tout `data/` sauf `data/demo/` est ignoré par git (`.gitignore`), un
> `.pbix` aussi (il embarque ses données). Les notebooks ne versionnent jamais leurs sorties :
> `run_pipeline.py` les retire avant réécriture, et `nbstripout` sert de garde-fou pour les
> exécutions manuelles dans Jupyter.

## Architecture

```
config/                    Overrides manuels (CSV), source de vérité pour les corrections ciblées
  identity_overrides.template.csv  Modèle vide (mêmes en-têtes que le fichier réel, voir plus bas)
  location_overrides.csv     stage_id, corrected_city, corrected_country, reason
  postal_overrides.csv       stage_id, corrected_postal_code, reason

data/
  raw/                      Export brut, jamais modifié
  interim/                  Sorties intermédiaires entre étapes du pipeline
  processed/                Dataset final unique (stages_efrei_final.csv)
  reference/                Décisions de fusion entreprises (semi-manuel) ET
                            identity_overrides.csv (source_identity, corrected_identity, reason) —
                            contient des noms réels d'étudiants, jamais versionné (voir RGPD ci-dessous)
  reports/                  Rapports qualité (métier, technique, registre d'anomalies)

notebooks/                 Un notebook par étape ; chargement, appel de fonctions métier,
                            audit lisible et export uniquement — aucune logique métier inline.
                            Les sorties de cellules ne sont jamais versionnées (voir RGPD).

src/stages_cleaning/       Toute la logique métier, testée unitairement.
  config.py                   Chargement générique des CSV d'overrides
  provenance.py                Construction de l'identifiant déterministe stage_id
  identity.py                  Parsing nom/prénom, re-segmentation email, canonisation sûre
  normalize.py                  Normalisation texte/pays/ville (clés de rapprochement)
  country.py                    Résolution pays (source, inférence, overrides, géocodage)
  postal.py                     Résolution code postal (validation, inférence, overrides)
  geocode.py                     Client Nominatim, cache, mapping générique par clé
  programme.py                   Extraction cursus/année/majeure/campus, flags SWIM/international
  company.py                     Normalisation, détection de doublons TF-IDF, canonicalisation,
                                  familles analytiques d'entreprises
  quality.py                     Registre d'anomalies technique (audit complet)
  quality_reporting/             Moteur de rapports métier + technique (engine, reports, runner)

tests/                      Un fichier de tests par module de src/
run_pipeline.py             Exécute tous les notebooks dans l'ordre (voir plus bas)
generate_quality_reports.py Génère les rapports qualité sans passer par un notebook
```

**Principe directeur** : les notebooks ne contiennent jamais de règle métier. Toute règle vit
dans `src/stages_cleaning/`, est testée dans `tests/`, et le notebook se contente de charger les
données, appeler la fonction, afficher un audit lisible et exporter.

Les trois fichiers d'overrides (`identity`, `location`/`country`, `postal`) sont appliqués en
mode strict par défaut : un `stage_id` (ou une identité) présent dans un fichier d'override mais
absent du dataset courant fait lever une erreur explicite plutôt que d'être silencieusement
ignoré — utile si l'export brut change et qu'un `stage_id` devient orphelin après un
rafraîchissement des données.

## Pipeline

```
00_profiling_raw              data/raw → (aucune sortie, profilage seul)
01_identity_cleaning          data/raw → data/interim/stages_efrei_with_name.csv
02_country_cleaning           01 sortie → data/interim/stages_efrei_with_country.csv
03_postal_code_cleaning       02 sortie → data/interim/stages_efrei_with_postal_code.csv
04_programme_enrichment       03 sortie → data/interim/stages_efrei_with_programme.csv
05_normalisation_entreprises  04 sortie → data/processed/stages_efrei_final.csv   ← producteur unique du final
06_data_quality_report        data/processed/stages_efrei_final.csv → data/reports/*
99_validation                  relit toutes les sorties ci-dessus et bloque toute régression
```

| # | Rôle | Produit |
|---|------|---------|
| 00 | Profilage du brut, aucune correction | — |
| 01 | Identité : `stage_id`, overrides manuels, parsing nom/prénom, re-segmentation email, canonisation sûre uniquement (les divergences réelles restent `needs_review`) | `stage_id`, `nom`, `prenom`, `identity_*` |
| 02 | Pays : normalisation ISO-2, inférence graduée par niveau de preuve (`high`/`medium`/`low`), overrides ciblés par `stage_id` | `pays`, `country_resolution_*` |
| 03 | Code postal : validation par pattern pays, inférence depuis des sources déjà validées, jamais depuis des placeholders | `code_postal`, `postal_code_final_status` |
| 04 | Programme : cursus/année/majeure/campus, trois notions séparées (`is_swim_program`, `is_swim_stage`, `is_international_stage`) | `real_program`, `major_status`, `is_*` |
| 05 | Entreprise : normalisation syntaxique, détection de doublons probables (TF-IDF), fusion **uniquement** sur décision `merge` validée manuellement, famille analytique | `entreprise_normalisee`, `entreprise_canonique`, `entreprise_famille` |
| 06 | Rapport qualité métier + technique à partir du même registre d'anomalies | `data/reports/*.xlsx`, `quality_issues.csv` |
| 99 | Invariants : cardinalité, unicité `stage_id`, ISO-2, statuts postaux, non-régression des colonnes, absence de livrables dupliqués | — (assertions) |

Chaque étape ne modifie jamais les colonnes produites par les étapes précédentes, hors les
colonnes qu'elle a explicitement le droit de réécrire (déclarées en positif) : `99_validation`
le vérifie désormais sur l'intégralité du pipeline (`01→02`, `02→03`, `03→04`, `04→05`), via
`pd.testing.assert_frame_equal` sur les colonnes héritées non mutables à chaque étape.

## Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Exécution

**Option 1 — tout le pipeline d'un coup :**

```powershell
python run_pipeline.py                         # export réel s'il est là, sinon démo
python run_pipeline.py --dataset demo --offline  # ce que lance la CI
```

Exécute les 8 notebooks dans l'ordre, réécrit chaque `.ipynb` avec ses nouvelles sorties (sorties
de cellules retirées avant écriture par défaut, voir RGPD ci-dessus — `--keep-outputs` pour les
conserver en débogage local), et s'arrête à la première erreur. Un nom de notebook inconnu dans
`--only` fait échouer la commande explicitement plutôt que d'être ignoré silencieusement.
Sous-ensemble possible :

```powershell
python run_pipeline.py --only 01_identity_cleaning 02_country_cleaning
python run_pipeline.py --keep-outputs   # debug local uniquement, ne jamais committer le résultat
```

**Option 2 — notebook par notebook**, dans Jupyter, en respectant l'ordre ci-dessus.

### Étape manuelle : validation des fusions d'entreprises (notebook 05)

Au premier passage, `05_normalisation_entreprises.ipynb` génère
`data/reference/company_merge_decisions.csv` avec toutes les paires candidates et une colonne
`decision` vide. **Tant que `decision` reste vide, aucune fusion n'est appliquée** —
`entreprise_canonique` est simplement égal à `entreprise_normalisee`. Pour valider :

1. Ouvrir `data/reference/company_merge_decisions.csv`.
2. Renseigner `decision` avec `merge`, `distinct` ou `review`.
3. Pour les lignes `merge`, renseigner `entreprise_canonique` si un nom canonique précis est voulu
   (sinon le nom le plus fréquent du groupe est choisi automatiquement).
4. Enregistrer, puis relancer le notebook 05 (le fichier de décisions n'est jamais écrasé).

### Géocodage réseau

`RUN_NETWORK_GEOCODING = True` par défaut dans les notebooks 02 et 03. **C'est un choix
délibéré, différent de la recommandation initiale de l'audit round 3** (qui proposait `False`
par défaut pour prioriser la reproductibilité hors ligne — voir `AUDIT_FIXES.md`, point B-1).
En pratique, le géocodage Nominatim résout une part significative des pays et codes postaux que
les recoupements internes au dataset ne peuvent pas déterminer (383 pays et plusieurs centaines
de codes postaux sur l'export actuel) ; désactiver le réseau par défaut aurait dégradé la
couverture du dataset final pour un gain de reproductibilité jugé secondaire par l'équipe, sachant
que :

- **le cache rend les runs suivants hors ligne** : une fois une localisation résolue, elle est
  écrite dans `data/interim/*_geocoding_cache.csv` (livré avec le projet) et n'est plus jamais
  re-géocodée — seules les localisations réellement nouvelles déclenchent un appel réseau ;
- **une panne réseau n'empoisonne plus le cache** : avant ce correctif, toute exception (coupure
  réseau, proxy d'école, machine hors ligne) était silencieusement interprétée comme
  « introuvable » et écrite en cache de façon permanente, sans retenter. Ce n'est plus le cas
  (`geocode.py`, `swallow_exceptions=False` + capture explicite) : une panne interrompt
  proprement le géocodage, conserve les résultats déjà obtenus, et laisse les localisations
  restantes en attente d'un prochain run — jamais de faux `not_found` définitif ;
- **le risque RGPD est documenté, pas éliminé** : chaque appel réseau envoie une adresse de stage
  à Nominatim/OpenStreetMap (service tiers). C'est un compromis assumé entre couverture des
  données et exposition réseau, pas une absence de risque. Si un run strictement hors ligne est
  nécessaire (environnement sans accès réseau, audit de reproductibilité, CI), repasser
  `RUN_NETWORK_GEOCODING` à `False` dans le(s) notebook(s) concerné(s) — le pipeline continue de
  fonctionner normalement à partir des caches déjà constitués, avec une couverture pays/CP
  réduite aux données déjà en cache.

Piloter le flag par variable d'environnement plutôt qu'en dur dans le notebook
(`os.environ.get("STAGES_RUN_NETWORK", "1") == "1"`) reste une amélioration possible pour
distinguer plus explicitement un run de développement (réseau activé) d'un run de CI
(réseau désactivé) sans risque d'oubli lors d'un commit.

## Rapports qualité

```powershell
python generate_quality_reports.py
```

Produit `data/reports/rapport_qualite_metier.xlsx` (à transmettre au service stages),
`data/reports/rapport_qualite_technique.xlsx` (audit/maintenance), `data/reports/quality_issues.csv`
(registre normalisé) et `data/reports/resume_qualite.pdf` (une à deux pages : KPI + évolution
depuis le dernier rapport, pensé pour être lu ou transféré par email sans logiciel spécifique).
L'évolution est calculée automatiquement à partir des instantanés conservés dans
`data/reports/history/` (non versionné, RGPD). Voir `REPORTING.md` pour le détail des règles et
comment en ajouter une.

## Export prêt pour la rentrée

```powershell
python build_analysis_export.py
```

`stages_efrei_final.csv` (producteur unique, notebook 05) n'est **jamais** filtré ni amputé : le
principe suivi depuis le début du projet est de ne jamais supprimer de ligne silencieusement.
Pour un usage aval (recherche de stage, chatbot, tableau de bord...), certaines lignes restent
trop peu fiables pour être exposées telles quelles. Décision prise le 06/08/2026 : 3 motifs
d'exclusion, définis dans `src/stages_cleaning/analysis_export.py`, testés dans
`tests/test_analysis_export.py` :

| Motif | Lignes | Condition |
|---|---|---|
| `dossier_vide` | 2 | ni entreprise, ni ville, ni pays renseignés |
| `identite_divergente` | 8 | identité étudiante ambiguë (`identity_variant_category == "divergence_reelle"`) |
| `entreprise_non_exploitable` | 19 | nom d'entreprise réduit à une forme juridique seule ou à un libellé générique |

Le script produit deux fichiers dans `data/processed/` :
- `stages_efrei_final_flagge.csv` : les 6018 lignes du final + colonnes `exclu_analyse` (bool) et
  `motif_exclusion` (texte, motifs cumulés séparés par `|`) — pour qui veut voir *pourquoi* une
  ligne est écartée.
- `stages_efrei_pret_rentree.csv` : uniquement les 5989 lignes non exclues, sans ces deux colonnes
  — c'est ce fichier qui doit être consommé par un usage externe (front, chatbot).

Les autres signalements du rapport qualité (pays à confiance faible, formats de CP non couverts,
CP non résolus, SWIM à vérifier) restent volontairement dans le dataset : jugés non bloquants
pour un usage analytique, à la différence des 3 motifs ci-dessus.

## Tests

```powershell
pytest
```

Un module de `src/stages_cleaning/` = un fichier de test. `99_validation.ipynb` complète ces
tests unitaires par des invariants de bout en bout. La CI (GitHub Actions) lance `pytest` puis
le pipeline complet sur le jeu de démo, hors ligne.

## Limites connues

- Les caches de géocodage (`data/interim/country_geocoding_cache.csv`,
  `data/interim/postal_code_geocoding_cache.csv`) **sont livrés** avec ce projet pour permettre
  une exécution reproductible sans attendre de nouveaux appels réseau ; ils ne sont pas versionnés
  dans git (voir `.gitignore`, RGPD) mais font partie du livrable transmis. Une localisation
  absente du cache déclenche un appel réseau réel à Nominatim tant que
  `RUN_NETWORK_GEOCODING = True` (voir ci-dessus).
- La revue manuelle des fusions d'entreprises (`company_merge_decisions.csv`) doit être effectuée
  explicitement ; tant qu'elle ne l'est pas, `entreprise_canonique` n'apporte rien de plus que
  `entreprise_normalisee`. Les nouvelles paires candidates détectées à chaque run sont ajoutées
  au fichier de décisions sans écraser les décisions déjà prises (`decision=""` pour les
  nouvelles paires) ; le nombre de paires en attente remonte dans le rapport qualité technique
  (règle `COMPANY_MERGE_DECISIONS_PENDING`).
- Une partie des pays et des codes postaux reste `unresolved` faute de preuve interne ou
  géocodée suffisante (voir `data/reports/rapport_qualite_technique.xlsx` pour le détail
  chiffré). Une inférence de code postal sur une preuve trop faible (une seule autre ligne dans
  la même ville) n'est plus acceptée automatiquement : elle reste `unresolved` et remonte dans
  `POSTAL_UNRESOLVED` pour arbitrage humain.
- Un géocodage résolu uniquement par nom de ville (`city_geocode`, sans code postal ni adresse)
  reste sujet à l'homonymie et est marqué d'une confiance dégradée (`geocoded_low`), visible dans
  la règle `COUNTRY_LOW_CONFIDENCE`.

## Historique

`AUDIT_FIXES.md` documente les corrections issues des audits successifs du projet.
