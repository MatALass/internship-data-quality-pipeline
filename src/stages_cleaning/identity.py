from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

import pandas as pd

SAFE_CANONICALIZATION_CATEGORIES = {"accents_espaces", "prenoms_secondaires"}


def normalize_identity_key(value: Any) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"\s*,\s*", ",", text)


def norm_txt(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", text.lower())


def first_email_segment(email: Any) -> str | None:
    if pd.isna(email) or not str(email).lower().endswith("@efrei.net"):
        return None
    local = str(email).split("@", 1)[0]
    return local.split(".")[0] if "." in local else None


def cut_to_normalized_prefix(original: str, target_norm: str) -> str:
    for i in range(1, len(original) + 1):
        if norm_txt(original[:i]) == target_norm:
            return original[:i]
    return original


def split_identity(value: Any, email: Any) -> tuple[Any, Any]:
    if pd.isna(value):
        return pd.NA, pd.NA
    text = re.sub(r"\s+", " ", str(value).strip())
    if "," not in text:
        return text.upper(), pd.NA
    nom, prenoms = text.split(",", maxsplit=1)
    prenom_tokens = prenoms.replace(",", " ").strip().split()
    prenom = prenom_tokens[0].upper() if prenom_tokens else pd.NA
    if pd.notna(prenom):
        segment = first_email_segment(email)
        if segment:
            seg_norm, prenom_norm = norm_txt(segment), norm_txt(prenom)
            if len(seg_norm) >= 3 and prenom_norm != seg_norm and prenom_norm.startswith(seg_norm):
                prenom = cut_to_normalized_prefix(str(prenom), seg_norm)
    return nom.strip().upper(), prenom


def _richness(value: str) -> tuple[int, int]:
    decomposed = unicodedata.normalize("NFD", value)
    accents = sum(1 for ch in decomposed if unicodedata.combining(ch))
    separators = sum(value.count(ch) for ch in (" ", "-", "'", "´"))
    return accents + separators, len(value)


def pick_canonical_identity(series: pd.Series) -> str:
    counts = series.value_counts()
    top = sorted(counts[counts == counts.max()].index.tolist())
    return max(top, key=_richness)


def normalize_identity_display(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value).strip()).upper()
    return re.sub(r"\s*,\s*", ", ", text)


def _split_identity_parts(value: Any) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", str(value).strip())
    if "," in text:
        nom, prenoms = text.split(",", 1)
    else:
        nom, prenoms = text, ""
    return nom.strip(), prenoms.strip()


def classify_identity_variants(values: Iterable[Any]) -> str:
    variants = sorted({normalize_identity_display(v) for v in values if pd.notna(v)})
    if len(variants) <= 1:
        return "single"
    if len({norm_txt(v) for v in variants}) == 1:
        return "accents_espaces"
    parsed = [_split_identity_parts(v) for v in variants]
    if len({norm_txt(nom) for nom, _ in parsed}) == 1:
        first_names = [norm_txt(prenoms) for _, prenoms in parsed]
        if all(a.startswith(b) or b.startswith(a) for a in first_names for b in first_names):
            return "prenoms_secondaires"
    return "divergence_reelle"


def _email_segments(email: str) -> tuple[list[str], str] | None:
    local = email.split("@", 1)[0].lower()
    if "." in local:
        raw_segments = local.split(".")
    elif local.count("-") == 1:
        raw_segments = local.split("-")
    else:
        return None
    segments = [re.sub(r"\d+$", "", s) for s in raw_segments]
    segments = [s for s in segments if s]
    if len(segments) < 2:
        return None
    return segments[:-1], segments[-1]


def check_identity(etudiant: Any, email: Any) -> str | None:
    if pd.isna(email) or not str(email).lower().endswith("@efrei.net"):
        return None
    parsed_email = _email_segments(str(email))
    if parsed_email is None:
        return "email_sans_separateur"
    email_first_names, email_last = parsed_email
    nom_part, prenom_part = _split_identity_parts(etudiant)
    nom_n, prenoms_n = norm_txt(nom_part), norm_txt(prenom_part)
    last_n = norm_txt(email_last)
    name_words = [w for w in re.split(r"[\s\-']+", str(nom_part).lower()) if w]
    initials = "".join(w[0] for w in name_words)
    nom_ok = bool(last_n) and (last_n in nom_n or nom_n in last_n or norm_txt(initials) == last_n)
    prenom_candidates: list[str] = []
    for segment in email_first_names:
        prenom_candidates.append(segment)
        prenom_candidates.extend(segment.split("-"))
    prenom_ok = any(norm_txt(s) and norm_txt(s) in prenoms_n for s in prenom_candidates)
    if nom_ok and prenom_ok:
        return None
    if not nom_ok and not prenom_ok:
        return "prenom_et_nom_differents"
    return "nom_different" if not nom_ok else "prenom_different"


def apply_identity_cleaning(frame: pd.DataFrame, overrides: pd.DataFrame) -> pd.DataFrame:
    """Nettoie les identités et refuse de canoniser les divergences réelles.

    Règles de sûreté :
    - les lignes sans email ne sont jamais regroupées entre elles (pas de clé fiable) :
      elles restent ``single`` et ne sont jamais canonisées ;
    - seules les lignes effectivement modifiées par la canonisation sont réécrites ;
    - un canonique sans partie prénom vide explicitement ``prenom``.
    """
    df = frame.copy()
    source_identity = df["etudiant"].astype("string")
    override_map = {
        normalize_identity_key(src): corrected
        for src, corrected in zip(overrides.get("source_identity", []), overrides.get("corrected_identity", []))
        if pd.notna(src) and pd.notna(corrected)
    }
    keys = source_identity.map(normalize_identity_key)
    manual_mask = keys.isin(override_map)
    corrected = source_identity.copy()
    corrected.loc[manual_mask] = keys.loc[manual_mask].map(override_map)
    corrected = corrected.astype("string")

    parsed = pd.DataFrame(
        [split_identity(value, email) for value, email in zip(corrected, df["email"])],
        columns=["nom", "prenom"], index=df.index, dtype="string",
    )
    source_first = (
        corrected.str.split(",", n=1).str[1]
        .astype("string")  # une série 100 % NaN (aucune virgule) resterait float et casserait .str
        .str.strip().str.split().str[0].astype("string").str.upper()
    )
    resegmented = parsed["prenom"].ne(source_first).fillna(False)
    df["nom"], df["prenom"] = parsed["nom"], parsed["prenom"]

    parsed_identity = (df["nom"].fillna("") + ", " + df["prenom"].fillna("")).str.strip(" ,")
    grouping = pd.DataFrame({"email": df["email"], "identity": parsed_identity})
    categories = (
        grouping.dropna(subset=["email"])
        .groupby("email")["identity"]
        .transform(classify_identity_variants)
    )
    df["identity_variant_category"] = categories.reindex(df.index).fillna("single").astype("string")
    df["identity_requires_review"] = df["identity_variant_category"].eq("divergence_reelle").astype("boolean")

    safe_mask = df["identity_variant_category"].isin(SAFE_CANONICALIZATION_CATEGORIES)
    canonical = pd.Series(pd.NA, index=df.index, dtype="string")
    if safe_mask.any():
        canonical.loc[safe_mask] = (
            grouping.loc[safe_mask]
            .groupby("email")["identity"]
            .transform(pick_canonical_identity)
            .to_numpy()
        )
    canonicalized = safe_mask & canonical.notna() & parsed_identity.ne(canonical)
    if canonicalized.any():
        split = canonical.str.split(", ", n=1, expand=True).reindex(columns=[0, 1])
        df.loc[canonicalized, "nom"] = split.loc[canonicalized, 0].astype("string")
        df.loc[canonicalized, "prenom"] = (
            split.loc[canonicalized, 1].astype("string").str.strip().replace("", pd.NA)
        )

    df["identity_manual_corrected"] = manual_mask.astype("boolean")
    df["identity_email_resegmented"] = resegmented.astype("boolean")
    df["identity_canonicalized"] = canonicalized.astype("boolean")
    df["identity_final_status"] = "resolved_source"
    df.loc[safe_mask, "identity_final_status"] = "resolved_safe_canonicalization"
    df.loc[df["identity_requires_review"], "identity_final_status"] = "needs_review"

    def method_for_row(idx: int) -> str:
        steps = ["source_parse"]
        if bool(manual_mask.loc[idx]):
            steps.append("manual_correction")
        if bool(resegmented.loc[idx]):
            steps.append("email_resegmentation")
        if bool(canonicalized.loc[idx]):
            steps.append("safe_canonicalization")
        return "|".join(steps)

    df["identity_resolution_method"] = pd.Series([method_for_row(i) for i in df.index], index=df.index, dtype="string")
    return df
