from __future__ import annotations

import pandas as pd

MAJOR_NORMALIZATION = {
    "Data and Artificial Intelligence": "Data & Artificial Intelligence",
    "Data engineering & Intelligence Artificielle": "Data Engineering & Intelligence Artificielle",
    "Cybersécurité, Infrastructure & Logiciel": "Cybersécurité, Infrastructure & Logiciels",
    "Cybersécurité, infrastructure & logiciels": "Cybersécurité, Infrastructure & Logiciels",
    "Cybersécurité, SI & gouvernance": "Cybersécurité, SI & Gouvernance",
    "Cybersécurité & cloud": "Cybersécurité & Cloud",
    "Cybersécurité et ethical hacking": "Cybersécurité & Ethical Hacking",
    "Cybersécurité, Réseau & Cloud": "Cybersécurité, Réseaux & Cloud",
    "Réseaux et Sécurité": "Réseaux & Sécurité",
    "Big Data et Machine Learning": "Big Data & Machine Learning",
    "Logiciels et Systèmes d'Information (LSI)": "Logiciels et Systèmes d'Information",
}

VALID_YEARS = {
    "Prépa": {1, 2}, "Ingénieur": {1, 2, 3}, "Bachelor": {1, 2, 3},
    "BTS": {1, 2}, "Master": {1, 2},
}

# ============================================================================
# Référentiel officiel des majeures EFREI (site institutionnel, audité manuellement
# fin 2026). Objectif : que chaque valeur de `major` soit rattachée à un nom
# officiel actuel, une filière/famille, et un statut explicite de confiance.
#
# Ne PAS modifier ces dictionnaires sans repasser par le même travail d'audit
# (comparaison de la timeline annee_academique x major pour distinguer un
# renommage réel d'une coexistence de deux programmes distincts). Voir la
# section "Canonisation des majeures" du notebook 04 pour la méthode.
# ============================================================================

OFFICIAL_MAJORS = {
    # Ingénieur — 13 majeures (4 filières)
    "Information Systems Strategy & Governance", "Software Engineering", "IT for Finance",
    "Technologies Immersives et IA",
    "Cybersécurité, SI & Gouvernance", "Cybersécurité, Infrastructure & Logiciels", "Cybersécurité & Cloud",
    "Data & Artificial Intelligence", "Data Engineering", "Bio & Numérique", "Business Intelligence & Analytics",
    "Transports intelligents", "Systèmes robotiques & drones",
    # Ingénieur — majeures en apprentissage
    "Logiciels et Systèmes d'Information", "Big Data & Machine Learning", "Réseaux et Sécurité",
    # BTS
    "Services Informatiques aux Organisations (SIO)", "Communication",
    # Bachelors Technologie & Numérique
    "Développeur web & IA", "Cybersécurité & Réseaux", "Cybersécurité & Ethical Hacking", "Informatique",
    # Bachelors Digital & Management
    "Marketing Digital & Communication", "International Communication & Technology", "Data Marketing & IA",
    "Chef de projet e-commerce",
    # Mastères Technologie & Numérique
    "Dev Manager Full Stack", "Data Engineering & IA", "Cybersécurité", "Cybersécurité & Management", "Green IT",
    # Mastères Digital & Management
    "UX Design", "Communication & Stratégies Digitales", "Marketing Digital & Management", "Management, Data & IA",
    "Marketing & Technologies Digitales", "International Communication & Management",
    "Management & Digital Transformation", "Digital Supply Chain Management",
}

# Majeures volontairement conservées telles quelles : discontinuées, aucun nom officiel actuel.
MAJOR_KEEP_AS_IS = {"Digital Transformation"}

# Libellés bruts sans correspondance fiable trouvée sur le site officiel. Volontairement PAS
# renommés (mieux vaut une valeur en attente qu'un mauvais rattachement silencieux) — voir
# l'échange du 2026-08 : programme réel et actif d'après les données mais absent du menu
# marketing simplifié actuel du site EFREI.
MAJOR_PENDING_REVIEW = {
    "Communication Digitale & Internationale",
    "Business & Nouvelles Technologies",
    "Marketing Stratégie digitale",
    "Management & Stratégie Digitale",
}

# Renommage : ancien libellé brut -> nom officiel actuel (preuve : succession temporelle nette
# dans annee_academique, URL/page officielle, ou correspondance directe avec le menu du site).
MAJOR_CANONICAL = {
    # --- Ingénieur ---
    "Bio-Informatique": "Bio & Numérique",
    "Cloud Architecture": "Cybersécurité & Cloud",
    "Imagerie et Réalité Virtuelle": "Technologies Immersives et IA",
    "Réseaux & Sécurité": "Réseaux et Sécurité",

    # --- Bachelor ---
    "Développeur web et IA": "Développeur web & IA",
    "Ingénierie Cyber Sécurité": "Cybersécurité & Réseaux",
    "Ingénierie & Cybersécurité": "Cybersécurité & Réseaux",
    "Ingénierie & Cyber": "Cybersécurité & Réseaux",
    "Ingénierie & Numérique": "Informatique",
    "Marketing Digital Communication": "Marketing Digital & Communication",
    "Marketing Digital et Communication": "Marketing Digital & Communication",
    "Ingénierie Marketing Digital": "Data Marketing & IA",

    # --- Master ---
    "Data Engineering & Intelligence Artificielle": "Data Engineering & IA",
    "Cybersécurité, Réseaux & Cloud": "Cybersécurité",
    "Cybersecurity & Artificial Intelligence": "Cybersécurité",
    "Cybersecurity & Management": "Cybersécurité & Management",
    "Marketing Digital et Management": "Marketing Digital & Management",
    "Communication & Stratégie Digitale": "Communication & Stratégies Digitales",
    "Management Data & Intelligence Artificielle": "Management, Data & IA",
}

# Regroupement du nom canonique -> filière (Ingénieur) ou famille (BTS/Bachelor/Master).
MAJOR_GROUP = {
    # Ingénieur -> filière
    "Information Systems Strategy & Governance": "Information Technology",
    "Software Engineering": "Information Technology",
    "IT for Finance": "Information Technology",
    "Technologies Immersives et IA": "Information Technology",
    "Logiciels et Systèmes d'Information": "Information Technology",
    "Digital Transformation": "Information Technology",

    "Cybersécurité, SI & Gouvernance": "Sécurité et Réseaux",
    "Cybersécurité, Infrastructure & Logiciels": "Sécurité et Réseaux",
    "Cybersécurité & Cloud": "Sécurité et Réseaux",
    "Réseaux et Sécurité": "Sécurité et Réseaux",

    "Data & Artificial Intelligence": "Data Science",
    "Data Engineering": "Data Science",
    "Bio & Numérique": "Data Science",
    "Business Intelligence & Analytics": "Data Science",
    "Big Data & Machine Learning": "Data Science",

    "Transports intelligents": "Systèmes embarqués",
    "Systèmes robotiques & drones": "Systèmes embarqués",

    # BTS / Bachelor / Master -> famille
    "Services Informatiques aux Organisations (SIO)": "Technologie & Numérique",
    "Développeur web & IA": "Technologie & Numérique",
    "Cybersécurité & Réseaux": "Technologie & Numérique",
    "Cybersécurité & Ethical Hacking": "Technologie & Numérique",
    "Informatique": "Technologie & Numérique",
    "Dev Manager Full Stack": "Technologie & Numérique",
    "Data Engineering & IA": "Technologie & Numérique",
    "Cybersécurité": "Technologie & Numérique",
    "Cybersécurité & Management": "Technologie & Numérique",
    "Green IT": "Technologie & Numérique",

    "Communication": "Digital & Management",
    "Marketing Digital & Communication": "Digital & Management",
    "International Communication & Technology": "Digital & Management",
    "Data Marketing & IA": "Digital & Management",
    "Chef de projet e-commerce": "Digital & Management",
    "UX Design": "Digital & Management",
    "Communication & Stratégies Digitales": "Digital & Management",
    "Marketing Digital & Management": "Digital & Management",
    "Management, Data & IA": "Digital & Management",
    "Marketing & Technologies Digitales": "Digital & Management",
    "International Communication & Management": "Digital & Management",
    "Management & Digital Transformation": "Digital & Management",
    "Digital Supply Chain Management": "Digital & Management",
    # Majeures réelles et actives mais absentes du menu simplifié du site : famille connue,
    # nom officiel encore en attente (voir MAJOR_PENDING_REVIEW).
    "Communication Digitale & Internationale": "Digital & Management",
    "Business & Nouvelles Technologies": "Digital & Management",
    "Marketing Stratégie digitale": "Digital & Management",
    "Management & Stratégie Digitale": "Digital & Management",
}


def enrich_programme_features(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    programme = df["programme"].str.strip().replace("", pd.NA)
    pays = df["pays"].str.strip().str.upper().replace("", pd.NA)
    programme_clean = (
        programme.str.replace(r"(?i)\s*\[SWIM\]\s*$", "", regex=True)
        .str.replace(r"(?i)\s*-\s*(?:Paris|Bordeaux)\s*$", "", regex=True)
        .str.replace(r"(?i)\s+(?:Paris|Bordeaux)\s*$", "", regex=True)
        .str.strip()
    )

    df["real_program"] = pd.Series(pd.NA, index=df.index, dtype="string")
    masks = {
        "Prépa": programme_clean.str.match(r"(?i)^Prépa\b", na=False),
        "Ingénieur": programme_clean.str.match(r"(?i)^(?:Ingénieur|Ingé)\b", na=False),
        "Bachelor": programme_clean.str.match(r"(?i)^Bachelor\b", na=False),
        "BTS": programme_clean.str.match(r"(?i)^BTS\b", na=False),
        "Master": programme_clean.str.match(r"(?i)^M[12]\b", na=False),
    }
    for name, mask in masks.items():
        df.loc[mask, "real_program"] = name

    year_standard = programme_clean.str.extract(r"(?i)^(?:Prépa|Bachelor|BTS|Ingénieur|Ingé)\s*([123])\b", expand=False)
    year_master = programme_clean.str.extract(r"(?i)^M([12])\b", expand=False)
    df["program_year"] = year_standard.fillna(year_master).astype("Int64")

    df["programme_campus"] = (
        programme.str.extract(r"(?i)(Paris|Bordeaux)(?:\s*\[SWIM\])?\s*$", expand=False)
        .astype("string").str.title()
    )

    major_extracted = (
        programme_clean.str.replace(r"(?i)^(?:Prépa|Bachelor|BTS|Ingénieur|Ingé)\s*[123]\s*(?:-\s*)?", "", regex=True)
        .str.replace(r"(?i)^M[12]\s*", "", regex=True)
        .str.strip().replace("", pd.NA)
    )
    df["major"] = major_extracted.replace(MAJOR_NORMALIZATION).astype("string")
    df["major_status"] = "available"
    missing_major = df["major"].isna()
    not_applicable = missing_major & (
        df["real_program"].eq("Prépa")
        | (df["real_program"].eq("Ingénieur") & df["program_year"].eq(1))
    )
    df.loc[missing_major, "major_status"] = "not_declared"
    df.loc[not_applicable, "major_status"] = "not_applicable"

    df["is_swim_program"] = programme.str.contains(r"\[SWIM\]", case=False, na=False).astype("boolean")
    df["is_swim_stage"] = df["type_stage"].str.strip().str.upper().eq("SWIM").astype("boolean")
    international = pd.Series(pd.NA, index=df.index, dtype="boolean")
    known_country = pays.notna()
    international.loc[known_country] = pays.loc[known_country].ne("FR")
    df["is_international_stage"] = international
    return df


def assign_major_canonical(frame: pd.DataFrame) -> pd.DataFrame:
    """Rattache chaque `major` à un nom officiel (référentiel site EFREI) et à sa filière/famille.

    Ajoute trois colonnes :
    - `major_canonical` : nom officiel actuel si connu, sinon la valeur `major` d'origine
      (jamais vidée — voir MAJOR_CANONICAL/MAJOR_KEEP_AS_IS/MAJOR_PENDING_REVIEW).
    - `major_canonical_status` : "official" | "kept_as_is" | "pending_review" | pd.NA (si `major`
      est lui-même NA, ex. Prépa).
    - `programme_groupe` : filière (Ingénieur) ou famille (BTS/Bachelor/Master).

    Ne renomme jamais silencieusement vers une mauvaise cible : tout `major` sans correspondance
    connue reste inchangé avec le statut `pending_review`, pour rester repérable plutôt que d'être
    fondu dans une catégorie incorrecte.
    """
    df = frame.copy()
    df["major_canonical"] = df["major"].map(MAJOR_CANONICAL).fillna(df["major"])

    status = pd.Series(pd.NA, index=df.index, dtype="string")
    has_major = df["major_canonical"].notna()
    status.loc[has_major & df["major_canonical"].isin(OFFICIAL_MAJORS)] = "official"
    status.loc[has_major & df["major_canonical"].isin(MAJOR_KEEP_AS_IS)] = "kept_as_is"
    status.loc[has_major & df["major_canonical"].isin(MAJOR_PENDING_REVIEW)] = "pending_review"
    df["major_canonical_status"] = status

    df["programme_groupe"] = df["major_canonical"].map(MAJOR_GROUP).astype("string")
    return df


def major_canonicalization_issues(frame: pd.DataFrame) -> pd.DataFrame:
    """Filet de sécurité : toute valeur de `major_canonical` non couverte par le référentiel
    (ni officielle, ni conservée volontairement, ni explicitement en attente) est une vraie
    anomalie à traiter — typiquement un nouveau libellé jamais vu apparaît dans une future
    extraction de données."""
    has_major = frame["major_canonical"].notna()
    recognized = OFFICIAL_MAJORS | MAJOR_KEEP_AS_IS | MAJOR_PENDING_REVIEW
    unknown = has_major & ~frame["major_canonical"].isin(recognized)
    return frame.loc[unknown].copy()


def programme_validation_issues(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    issues: dict[str, pd.DataFrame] = {}
    programme_present = frame["programme"].notna()
    issues["programmes_non_reconnus"] = frame.loc[programme_present & frame["real_program"].isna()].copy()
    issues["annees_non_extraites"] = frame.loc[programme_present & frame["program_year"].isna()].copy()
    invalid = pd.Series(False, index=frame.index)
    for program, years in VALID_YEARS.items():
        invalid |= frame["real_program"].eq(program) & ~frame["program_year"].isin(years)
    issues["annees_invalides"] = frame.loc[invalid].copy()
    return issues
