from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

from .normalize import strip_accents

LEGAL_FORMS = {
    "sa", "sas", "sasu", "sarl", "eurl", "snc", "scs", "gie", "se", "ei",
    "ltd", "limited", "inc", "llc", "gmbh", "ag", "plc", "srl", "spa",
    "bv", "nv", "aps", "lda", "sal", "fzco",
}

GENERIC_VALUES = {
    "enseignement", "fonction publique", "service public", "auto entreprise",
    "micro entreprise", "mission humanitaire", "ong",
}

EXACT_ALIASES = {
    "bnpparibas": "bnp paribas",
    "societe general": "societe generale",
    "one point": "onepoint",
    "nature et decouverte": "nature et decouvertes",
    "airbus defense and space": "airbus defence and space",
    "semei trading": "seimei trading",
    "south east univeristy": "south east university",
    "bali intership": "bali internship",
    "planmygapyear": "plan my gap year",
    "mittaphap saelao project": "mittaphap sae lao project",
    "regie autonome des transports parisiens": "ratp",
    "la regie autonome des transports parisiens ratp": "ratp",
    "electricite de france": "edf",
    "electricite de france edf": "edf",
    "centre national de la recherche scientifique": "cnrs",
    "etablissement francais du sang efs": "etablissement francais du sang",
    "societe francaise du radiotelephone s f r": "sfr",
    "rte reseau de transport d electricite": "rte",
    "credit lyonnais": "lcl",
    "thales sixgts": "thales six gts",
    "credit agricole corporate and investment bank": "credit agricole corporate et investment bank",
    "credit agricole corporate investment banking": "credit agricole corporate et investment bank",
}

# Chaque règle est évaluée dans l'ordre ; la première correspondance l'emporte.
FAMILY_RULES: list[tuple[str, str]] = [
    # Retail
    (r"^fnac darty\b.*$", "fnac darty"),
    (r"^(?:darty\b.*|etablissements darty et fils)$", "darty"),
    (r"^fnac\b.*$", "fnac"),
    (r"^decathlon\b.*$", "decathlon"),
    (r"^carrefour\b.*$", "carrefour"),
    (r"^auchan\b.*$", "auchan"),
    (r"^intersport\b.*$", "intersport"),
    (r"^samsonite\b.*$", "samsonite"),
    (r"^wefix\b.*$", "wefix"),
    (r"^nespresso\b.*$", "nespresso"),
    (r"^nature et decouvertes\b.*$", "nature et decouvertes"),
    # Banque et assurance
    (r"^bnp paribas\b.*$", "bnp paribas"),
    (r"^credit agricole\b.*$", "credit agricole"),
    (r"^caceis\b.*$", "caceis"),
    (r"^bpce\b.*$", "bpce"),
    (r"^natixis\b.*$", "natixis"),
    (r"^amundi\b.*$", "amundi"),
    (r"^axa\b.*$", "axa"),
    (r"^groupama\b.*$", "groupama"),
    # Industrie et technologie
    (r"^thales\b.*$", "thales"),
    (r"^safran\b.*$", "safran"),
    (r"^orange\b.*$", "orange"),
    (r"^sopra steria\b.*$", "sopra steria"),
    (r"^devoteam\b.*$", "devoteam"),
    (r"^wavestone\b.*$", "wavestone"),
    (r"^sii\b.*$", "sii"),
    (r"^totalenergies\b.*$", "totalenergies"),
    (r"^schneider electric\b.*$", "schneider electric"),
    (r"^airbus\b.*$", "airbus"),
    (r"^(?:bosch|robert bosch)\b.*$", "bosch"),
    (r"^(?:societe )?mbda\b.*$", "mbda"),
    (r"^(?:renault|renault group)\b.*$", "renault"),
    # Énergie
    (r"^edf\b.*$", "edf"),
    (r"^rte\b.*$", "rte"),
    (r"^cea\b.*$", "cea"),
    (r"^commissariat a l energie atomique\b.*$", "cea"),
    # Transport et télécom
    (r"^sncf\b.*$", "sncf"),
    (r"^ratp\b.*$", "ratp"),
    (r"^sfr\b.*$", "sfr"),
    # Recherche et public
    (r"^cnrs\b.*$", "cnrs"),
    (r".*\binserm\b.*", "inserm"),
    (r"^inrae\b.*$", "inrae"),
    # EFREI
    (r"^(?:efrei|efrei paris|efrei research lab|incubateur efrei|incubateur efrei paris)$", "efrei"),
    # ADP
    (r"^(?:aeroports de paris|groupe adp)\b.*$", "groupe adp"),
]

VALID_DECISIONS = {"", "merge", "distinct", "review"}
SUGGESTION_PRIORITY = {"merge_probable": 1, "review": 2, "weak_candidate": 3}

CANDIDATE_COLUMNS = [
    "entreprise_1", "entreprise_2", "frequence_1", "frequence_2", "frequence_totale",
    "similarite_tfidf", "similarite_tokens", "ratio_longueur", "inclusion",
    "suggestion", "score_priorite",
]

_SPACED_LEGAL_FORMS = [
    (r"\bs\s+a\s+s\s+u\b", "sasu"), (r"\bs\s+a\s+r\s+l\b", "sarl"),
    (r"\be\s+u\s+r\s+l\b", "eurl"), (r"\bs\s+a\s+s\b", "sas"),
    (r"\bs\s+n\s+c\b", "snc"), (r"\bs\s+a\b", "sa"),
]


def _normalize_spaced_legal_forms(value: str) -> str:
    """Normalise les formes juridiques écrites caractère par caractère (s a s u -> sasu)."""
    for pattern, replacement in _SPACED_LEGAL_FORMS:
        value = re.sub(pattern, replacement, value)
    return value


def _remove_registration_numbers(value: str) -> str:
    """Retire les identifiants administratifs ajoutés au nom (SIRET, SIREN, numéros longs)."""
    value = re.sub(r"\b(?:numero\s+)?(?:siret|siren)\b.*$", "", value)
    value = re.sub(r"\s+(?:\d[\s]*){9,14}$", "", value)
    return value.strip()


def _remove_legal_forms(value: str) -> str:
    """Retire les formes juridiques situées en tête ou en fin de nom."""
    forms_pattern = "|".join(sorted(LEGAL_FORMS, key=len, reverse=True))
    value = re.sub(rf"^(?:{forms_pattern})\s+", "", value)
    previous = None
    while previous != value:
        previous = value
        value = re.sub(rf"\s+(?:{forms_pattern})$", "", value).strip()
    return value


def normalize_company_name(value: Any) -> Any:
    """Normalisation syntaxique prudente : casse, accents, symboles, formes juridiques, alias exacts sûrs."""
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if not text:
        return pd.NA
    text = strip_accents(text).lower()
    text = text.replace("&", " et ").replace("+", " plus ")
    text = re.sub(r"[\u2019'`´]", " ", text)
    text = re.sub(r"[-_/\\\u2013\u2014]+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text).replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = _normalize_spaced_legal_forms(text)
    text = _remove_registration_numbers(text)
    text = _remove_legal_forms(text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return pd.NA
    return EXACT_ALIASES.get(text, text)


def company_quality(value: Any) -> str:
    """Classe la qualité d'un nom d'entreprise déjà normalisé."""
    if pd.isna(value):
        return "missing"
    if value in LEGAL_FORMS:
        return "legal_form_only"
    if value in GENERIC_VALUES:
        return "generic_label"
    if len(value) <= 1:
        return "suspicious"
    return "ok"


def enrich_company_normalization(frame: pd.DataFrame) -> pd.DataFrame:
    """Ajoute `entreprise_normalisee` et `entreprise_qualite`."""
    df = frame.copy()
    df["entreprise_normalisee"] = df["entreprise"].map(normalize_company_name).astype("string")
    df["entreprise_qualite"] = df["entreprise_normalisee"].map(company_quality).astype("string")
    return df


def _token_jaccard(name_1: str, name_2: str) -> float:
    tokens_1, tokens_2 = set(name_1.split()), set(name_2.split())
    union = tokens_1 | tokens_2
    return len(tokens_1 & tokens_2) / len(union) if union else 0.0


def _length_ratio(name_1: str, name_2: str) -> float:
    longer = max(len(name_1), len(name_2))
    return min(len(name_1), len(name_2)) / longer if longer else 0.0


def _is_contained(name_1: str, name_2: str) -> bool:
    return name_1 in name_2 or name_2 in name_1


def _suggest_decision(row: pd.Series) -> str:
    """Classe une paire candidate par probabilité de doublon. Ne fusionne jamais automatiquement."""
    tfidf, tokens, ratio, inclusion = row["similarite_tfidf"], row["similarite_tokens"], row["ratio_longueur"], row["inclusion"]
    if tfidf >= 0.94 and ratio >= 0.85:
        return "merge_probable"
    if tfidf >= 0.90 and tokens >= 0.65:
        return "merge_probable"
    if inclusion and tfidf >= 0.82:
        return "review"
    if tfidf >= 0.84:
        return "review"
    return "weak_candidate"


def build_company_candidates(frame: pd.DataFrame, min_similarity: float = 0.78, n_neighbors: int = 12) -> pd.DataFrame:
    """Détecte des paires de noms d'entreprise probablement doublons via TF-IDF + plus proches voisins.

    Ne modifie jamais les données : produit uniquement des candidats à valider manuellement.
    """
    valid = frame.loc[frame["entreprise_qualite"].eq("ok"), "entreprise_normalisee"]
    counts = valid.value_counts().rename_axis("entreprise").reset_index(name="frequence")
    names = counts["entreprise"].tolist()
    if len(names) < 2:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)
    frequency_map = dict(zip(counts["entreprise"], counts["frequence"]))

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=False, min_df=1)
    matrix = vectorizer.fit_transform(names)
    k = min(n_neighbors, len(names))
    distances, indices = NearestNeighbors(n_neighbors=k, metric="cosine", algorithm="brute").fit(matrix).kneighbors(matrix)

    rows, seen_pairs = [], set()
    for source_index, source_name in enumerate(names):
        for distance, target_index in zip(distances[source_index], indices[source_index]):
            target_name = names[target_index]
            if source_name == target_name:
                continue
            similarity = 1 - distance
            if similarity < min_similarity:
                continue
            pair_key = tuple(sorted([source_name, target_name]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            rows.append({
                "entreprise_1": source_name, "entreprise_2": target_name,
                "frequence_1": frequency_map[source_name], "frequence_2": frequency_map[target_name],
                "frequence_totale": frequency_map[source_name] + frequency_map[target_name],
                "similarite_tfidf": round(float(similarity), 4),
                "similarite_tokens": round(_token_jaccard(source_name, target_name), 4),
                "ratio_longueur": round(_length_ratio(source_name, target_name), 4),
                "inclusion": _is_contained(source_name, target_name),
            })
    candidates = pd.DataFrame(rows, columns=CANDIDATE_COLUMNS[:-2])
    if candidates.empty:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)

    candidates["suggestion"] = candidates.apply(_suggest_decision, axis=1)
    candidates["score_priorite"] = candidates["similarite_tfidf"] * np.log1p(candidates["frequence_totale"])
    order = candidates["suggestion"].map(SUGGESTION_PRIORITY)
    candidates = (
        candidates.assign(_order=order)
        .sort_values(["_order", "score_priorite", "similarite_tfidf"], ascending=[True, False, False])
        .drop(columns="_order")
        .reset_index(drop=True)
    )
    return candidates


def reconcile_merge_decisions(candidates: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """Ajoute au référentiel les paires candidates absentes, sans jamais toucher aux décisions existantes.

    Le VERIFICATION.md original constatait déjà des paires candidates orphelines (jamais reportées
    dans ``company_merge_decisions.csv``) : l'écart grandissait en silence au fil des rafraîchissements.
    Cette fonction est append-only : une paire déjà présente (dans un sens ou dans l'autre) n'est
    jamais dupliquée ni réécrasée, seules les nouvelles paires sont ajoutées avec ``decision=""``.
    """
    if candidates.empty:
        return decisions
    if decisions.empty or "entreprise_1" not in decisions.columns:
        existing_keys: set[frozenset] = set()
    else:
        pairs = zip(decisions.get("entreprise_1", []), decisions.get("entreprise_2", []))
        existing_keys = {frozenset((a, b)) for a, b in pairs if pd.notna(a) and pd.notna(b)}

    new_rows, seen = [], set()
    for _, row in candidates.iterrows():
        key = frozenset((row["entreprise_1"], row["entreprise_2"]))
        if key in existing_keys or key in seen:
            continue
        seen.add(key)
        new_rows.append(row)
    if not new_rows:
        return decisions

    additions = pd.DataFrame(new_rows).reset_index(drop=True)
    additions["decision"] = additions.get("decision", "")
    additions["decision"] = additions["decision"].fillna("")
    additions["entreprise_canonique"] = additions.get("entreprise_canonique", "")
    additions["commentaire"] = additions.get("commentaire", "")
    return pd.concat([decisions, additions], ignore_index=True)


def validate_decisions(decisions: pd.DataFrame) -> pd.DataFrame:
    """Normalise et valide la colonne `decision` d'un référentiel de fusion."""
    df = decisions.copy()
    df["decision"] = df.get("decision", pd.Series(dtype="string")).fillna("").astype(str).str.strip().str.lower()
    invalid = set(df["decision"].unique()) - VALID_DECISIONS
    if invalid:
        raise ValueError(f"Décisions invalides détectées : {sorted(invalid)}")
    return df


class _UnionFind:
    """Structure minimale pour regrouper les entreprises connectées par des décisions de fusion."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, value: str) -> str:
        self.parent.setdefault(value, value)
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, value_1: str, value_2: str) -> None:
        root_1, root_2 = self.find(value_1), self.find(value_2)
        if root_1 != root_2:
            self.parent[root_2] = root_1


def apply_company_canonicalization(frame: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """Fusionne les entreprises uniquement pour les paires explicitement validées `merge`.

    Les paires sans décision (`""`), `distinct` ou `review` ne sont jamais fusionnées.
    """
    df = frame.copy()
    decisions = validate_decisions(decisions)
    approved = decisions.loc[decisions["decision"].eq("merge")].copy()

    union_find = _UnionFind()
    for _, row in approved.iterrows():
        company_1, company_2 = row.get("entreprise_1"), row.get("entreprise_2")
        if pd.isna(company_1) or pd.isna(company_2):
            continue
        union_find.union(company_1, company_2)

    components: dict[str, list[str]] = {}
    for company in union_find.parent:
        components.setdefault(union_find.find(company), []).append(company)

    frequency_map = (
        df.loc[df["entreprise_qualite"].eq("ok")].groupby("entreprise_normalisee").size().to_dict()
    )
    aliases: dict[str, str] = {}
    for root, members in components.items():
        component_rows = approved.loc[approved["entreprise_1"].isin(members) | approved["entreprise_2"].isin(members)]
        manual_canonical = component_rows["entreprise_canonique"].map(normalize_company_name).dropna().astype(str).str.strip()
        manual_canonical = manual_canonical[manual_canonical != ""]
        if not manual_canonical.empty:
            canonical = manual_canonical.value_counts().index[0]
        else:
            canonical = max(sorted(members), key=lambda company: (frequency_map.get(company, 0), -len(company)))
        for member in members:
            aliases[member] = canonical

    df["entreprise_canonique"] = df["entreprise_normalisee"].replace(aliases).astype("string")
    return df


def get_company_family(value: Any) -> Any:
    """Regroupe une entreprise canonique dans une famille analytique. Ne modifie jamais `entreprise_canonique`."""
    if pd.isna(value):
        return pd.NA
    for pattern, family_name in FAMILY_RULES:
        if re.match(pattern, value):
            return family_name
    return value


def assign_company_family(frame: pd.DataFrame) -> pd.DataFrame:
    """Ajoute `entreprise_famille` à partir de `entreprise_canonique`."""
    df = frame.copy()
    df["entreprise_famille"] = df["entreprise_canonique"].map(get_company_family).astype("string")
    return df
