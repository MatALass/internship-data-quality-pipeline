from __future__ import annotations

import re
from typing import Any

import pandas as pd

NUMERIC_POSTAL_LENGTH = {
    "AT": 4, "AU": 4, "BE": 4, "BG": 4, "CH": 4, "CV": 4, "CY": 4,
    "DK": 4, "HU": 4, "LU": 4, "MT": 4, "NO": 4, "SI": 4, "TN": 4, "ZA": 4,
    "DE": 5, "DZ": 5, "EG": 5, "ES": 5, "FR": 5, "ID": 5, "IT": 5,
    "KR": 5, "KW": 5, "MA": 5, "MC": 5, "MX": 5, "MY": 5, "NP": 5,
    "PE": 5, "SA": 5, "TH": 5, "TR": 5, "US": 5,
    "CN": 6, "CO": 6, "IN": 6, "SG": 6, "VN": 6,
}

POSTAL_CODE_PATTERNS = {
    **{country: rf"^\d{{{length}}}$" for country, length in NUMERIC_POSTAL_LENGTH.items()},
    "BR": r"^\d{5}-\d{3}$", "CA": r"^[A-Z]\d[A-Z] \d[A-Z]\d$",
    "CZ": r"^\d{5}$", "GB": r"^[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2}$",
    "GR": r"^\d{5}$", "IE": r"^[A-Z0-9]{3} [A-Z0-9]{4}$",
    "IL": r"^\d{7}$", "IS": r"^\d{3}$", "JP": r"^\d{3}-\d{4}$",
    "MG": r"^\d{3}$", "NL": r"^\d{4} [A-Z]{2}$", "NZ": r"^\d{4}$",
    "PL": r"^\d{2}-\d{3}$", "PT": r"^\d{4}-\d{3}$", "SE": r"^\d{5}$",
    "SK": r"^\d{5}$", "TW": r"^(?:\d{3}|\d{5}|\d{6})$",
}

PO_BOX_PATTERN = re.compile(r"(?i)\b(?:BP|B\.P\.|BOX|PO\s*BOX)\b")
COUNTRY_PREFIXES = {"FR": ("F-", "FR-"), "DE": ("D-", "DE-"), "CH": ("CH-",), "LU": ("L-",)}
SUSPICIOUS_PLACEHOLDERS = {"0", "00", "000", "0000", "00000", "000000", "99", "999", "9999", "99999", "999999"}


def _basic_clean(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    text = str(value).replace("\xa0", " ").strip().upper()
    text = re.sub(r"\.0$", "", text)
    text = re.sub(r"\s+", " ", text)
    return text or pd.NA


def fix_leading_zeros(cp: Any, country: Any) -> Any:
    cp = _basic_clean(cp)
    if pd.isna(cp) or pd.isna(country):
        return cp
    expected = NUMERIC_POSTAL_LENGTH.get(str(country).upper())
    compact = str(cp).replace(" ", "")
    if expected and compact.isdigit() and len(compact) == expected - 1:
        return compact.zfill(expected)
    return cp


def normalize_postal_code(value: Any, country: Any = None) -> Any:
    cp = _basic_clean(value)
    if pd.isna(cp):
        return pd.NA
    country_code = str(country).upper() if pd.notna(country) else None
    if country_code:
        for prefix in COUNTRY_PREFIXES.get(country_code, ()):
            if str(cp).startswith(prefix):
                cp = str(cp)[len(prefix):].strip()
                break
    if country_code in {"US", "AU"}:
        match = re.search(r"\b(\d{4,5}(?:-\d{4})?)\b", str(cp))
        if match:
            cp = match.group(1)
    if country_code in NUMERIC_POSTAL_LENGTH:
        compact = re.sub(r"[\s.-]", "", str(cp))
        if "O" in compact and compact.replace("O", "0").isdigit():
            compact = compact.replace("O", "0")
        cp = fix_leading_zeros(compact, country_code)
    elif country_code in {"GR", "CZ", "SE", "SK"}:
        cp = re.sub(r"\s", "", str(cp))
    elif country_code == "CA":
        compact = re.sub(r"\s", "", str(cp)); cp = f"{compact[:3]} {compact[3:]}" if len(compact) == 6 else compact
    elif country_code == "GB":
        compact = re.sub(r"[\s-]", "", str(cp)); cp = f"{compact[:-3]} {compact[-3:]}" if len(compact) >= 5 else compact
    elif country_code == "IE":
        compact = re.sub(r"\s", "", str(cp)); cp = f"{compact[:3]} {compact[3:]}" if len(compact) == 7 else compact
    elif country_code == "NL":
        compact = re.sub(r"[\s-]", "", str(cp)); cp = f"{compact[:4]} {compact[4:]}" if len(compact) == 6 else compact
    elif country_code == "PT":
        compact = re.sub(r"[\s.-]", "", str(cp)); cp = f"{compact[:4]}-{compact[4:]}" if len(compact) == 7 and compact.isdigit() else str(cp).replace(".", "-")
    elif country_code == "JP":
        compact = re.sub(r"[\s-]", "", str(cp)); cp = f"{compact[:3]}-{compact[3:]}" if len(compact) == 7 and compact.isdigit() else compact
    elif country_code == "BR":
        compact = re.sub(r"[\s-]", "", str(cp)); cp = f"{compact[:5]}-{compact[5:]}" if len(compact) == 8 and compact.isdigit() else compact
    elif country_code == "PL":
        compact = re.sub(r"[\s-]", "", str(cp)); cp = f"{compact[:2]}-{compact[2:]}" if len(compact) == 5 and compact.isdigit() else compact
    elif country_code == "TW":
        cp = re.sub(r"(?i)^TA[ÏI]WAN\s+", "", str(cp)).strip(); cp = re.sub(r"\s", "", cp)
    return str(cp).strip() or pd.NA


def validate_postal_code(value: Any, country: Any) -> bool | None:
    if pd.isna(value):
        return False
    if pd.isna(country):
        return None
    pattern = POSTAL_CODE_PATTERNS.get(str(country).strip().upper())
    if pattern is None:
        return None
    return bool(re.fullmatch(pattern, str(value).strip().upper()))


def _simple_text_key(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"[^A-ZÀ-ÖØ-Ý0-9]+", "", str(value).upper().strip())


def is_suspicious_placeholder(value: Any) -> bool:
    cp = _basic_clean(value)
    return pd.notna(cp) and postal_code_match_key(cp) in SUSPICIOUS_PLACEHOLDERS


def postal_code_status(raw_value: Any, normalized_value: Any, country: Any, city: Any = None) -> str:
    if pd.isna(raw_value):
        return "missing"
    raw_text = str(raw_value).strip()
    if PO_BOX_PATTERN.search(raw_text):
        return "po_box_not_postal_code"
    if "+" in raw_text:
        return "plus_code_not_postal_code"
    if pd.notna(city) and _simple_text_key(normalized_value) == _simple_text_key(city):
        return "city_name_not_postal_code"
    if not any(char.isdigit() for char in raw_text):
        return "text_not_postal_code"
    if is_suspicious_placeholder(normalized_value):
        return "suspicious_placeholder"
    if pd.isna(country):
        return "not_validated_country_missing"
    validity = validate_postal_code(normalized_value, country)
    if validity is True:
        return "valid"
    if validity is False:
        return "invalid_format"
    return "not_validated_pattern_unsupported"


def postal_code_match_key(value: Any) -> str:
    cp = _basic_clean(value)
    if pd.isna(cp):
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(cp).upper())


def zero_lost(cp: Any, country: Any) -> bool:
    if pd.isna(cp) or pd.isna(country):
        return False
    expected = NUMERIC_POSTAL_LENGTH.get(str(country).upper())
    compact = re.sub(r"\s", "", str(cp))
    return bool(expected and compact.isdigit() and len(compact) == expected - 1)


def extract_embedded_postal_code(address: Any, country: Any) -> Any:
    if pd.isna(address) or pd.isna(country):
        return pd.NA
    country_code = str(country).upper()
    patterns = {
        "BR": r"\b(\d{5}-\d{3})\b", "PT": r"\b(\d{4}[.-]\d{3})\b",
        "JP": r"\b(\d{3}-\d{4})\b", "IE": r"\b([A-Z0-9]{3}\s?[A-Z0-9]{4})\b",
        "CA": r"\b([A-Z]\d[A-Z]\s?\d[A-Z]\d)\b",
    }
    pattern = patterns.get(country_code)
    if pattern is None and country_code in NUMERIC_POSTAL_LENGTH:
        pattern = rf"\b(\d{{{NUMERIC_POSTAL_LENGTH[country_code]}}})\b"
    if pattern is None:
        return pd.NA
    match = re.search(pattern, str(address), flags=re.IGNORECASE)
    if not match:
        return pd.NA
    candidate = normalize_postal_code(match.group(1), country_code)
    return candidate if validate_postal_code(candidate, country_code) is True else pd.NA


def final_postal_status(code: Any, country: Any) -> str:
    if pd.isna(code):
        return "unresolved"
    validity = validate_postal_code(code, country)
    if validity is True:
        return "valid_country_pattern"
    if pd.isna(country):
        return "unvalidated_country_missing"
    if validity is None:
        return "unvalidated_pattern_unsupported"
    return "invalid_country_pattern"


def prepare_postal_resolution(frame: pd.DataFrame) -> pd.DataFrame:
    """Prépare les statuts source et initialise la meilleure valeur disponible.

    Les valeurs non validables peuvent être conservées comme données source mais ne
    sont jamais propagées vers d'autres lignes par inférence.
    """
    df = frame.copy()
    if "code_postal_source_raw" not in df.columns:
        df["code_postal_source_raw"] = df["code_postal"]
    df["code_postal_normalized_source"] = pd.Series(
        [normalize_postal_code(cp, country) for cp, country in zip(df["code_postal_source_raw"], df["pays"])],
        index=df.index, dtype="string",
    )
    df["postal_code_source_status"] = pd.Series(
        [postal_code_status(raw, norm, country, city) for raw, norm, country, city in zip(
            df["code_postal_source_raw"], df["code_postal_normalized_source"], df["pays"], df["ville"]
        )],
        index=df.index, dtype="string",
    )
    retainable = df["postal_code_source_status"].isin({
        "valid", "not_validated_country_missing", "not_validated_pattern_unsupported"
    })
    df["code_postal_final"] = pd.NA
    df.loc[retainable, "code_postal_final"] = df.loc[retainable, "code_postal_normalized_source"]
    df["postal_code_resolution_method"] = pd.NA
    df.loc[retainable, "postal_code_resolution_method"] = "source"
    changed = retainable & df["code_postal_source_raw"].astype("string").str.strip().ne(df["code_postal_normalized_source"])
    df.loc[changed, "postal_code_resolution_method"] = "source_normalized"
    df.loc[df["postal_code_source_status"].eq("not_validated_country_missing"), "postal_code_resolution_method"] = "source_unvalidated_country_missing"
    df.loc[df["postal_code_source_status"].eq("not_validated_pattern_unsupported"), "postal_code_resolution_method"] = "source_unvalidated_pattern"
    return df


def infer_postal_from_valid_source(frame: pd.DataFrame) -> pd.DataFrame:
    """Infère un CP depuis des références validées, preuve la plus précise d'abord.

    Le nombre d'observations qui soutiennent l'inférence est conservé dans
    ``postal_code_inference_support``. L'inférence ville+pays exige au moins deux
    observations concordantes : un singleton (une seule autre ligne dans la même ville)
    est une preuve trop faible pour produire un CP présenté ensuite comme valide.
    """
    from .geocode import apply_mapping, unique_mapping_with_support
    from .normalize import normalize_address_key, normalize_city_key

    df = frame.copy()
    df["_city_key"] = df["ville"].map(normalize_city_key).replace("", pd.NA).astype("string")
    df["_address_key"] = df["adresse"].map(normalize_address_key).replace("", pd.NA).astype("string")
    df["postal_code_inference_support"] = pd.Series(pd.NA, index=df.index, dtype="Int64")
    reference = df[
        df["postal_code_source_status"].eq("valid")
        & df["code_postal_normalized_source"].notna()
    ].copy()
    rules = [
        (["_address_key", "_city_key", "pays"], "same_location_valid_source", 1),
        (["_city_key", "pays"], "city_country_unique_valid_source", 2),
    ]
    for keys, method, min_support in rules:
        mapping = unique_mapping_with_support(reference, keys, "code_postal_normalized_source")
        candidate, support = apply_mapping(df, keys, mapping)
        mask = df["code_postal_final"].isna() & candidate.notna() & support.ge(min_support).fillna(False)
        df.loc[mask, "code_postal_final"] = candidate[mask]
        df.loc[mask, "postal_code_resolution_method"] = method
        df.loc[mask, "postal_code_inference_support"] = support[mask]
    return df


def apply_postal_geocode_cache(frame: pd.DataFrame, cache: pd.DataFrame) -> pd.DataFrame:
    """Applique le cache de géocodage CP (logique auparavant inline dans le notebook 03)."""
    df = frame.copy()
    if cache.empty:
        return df
    duplicated = cache["location_key"].duplicated()
    if duplicated.any():
        raise ValueError(
            "Cache de géocodage CP corrompu : location_key dupliquées "
            f"{sorted(cache.loc[duplicated, 'location_key'].unique())[:5]}"
        )
    n_before = len(df)
    df = df.merge(cache, on="location_key", how="left")
    if len(df) != n_before:
        raise ValueError("La jointure du cache CP a modifié la cardinalité du dataset")
    mask = df["code_postal_final"].isna() & df["postal_code_geocode"].notna()
    df.loc[mask, "code_postal_final"] = df.loc[mask, "postal_code_geocode"]
    df.loc[mask, "postal_code_resolution_method"] = df.loc[mask, "geocode_method"]
    return df


def apply_postal_overrides(frame: pd.DataFrame, overrides: pd.DataFrame, strict: bool = True) -> pd.DataFrame:
    df = frame.copy()
    if overrides.empty:
        return df
    rows = overrides.dropna(subset=["stage_id", "corrected_postal_code"])
    unmatched = sorted(set(rows["stage_id"]) - set(df["stage_id"]))
    if unmatched and strict:
        raise ValueError(
            "Overrides CP sans correspondance (stage_id périmés après changement du brut ?) : "
            f"{unmatched}"
        )
    for _, row in rows.iterrows():
        mask = df["stage_id"].eq(row["stage_id"])
        if not mask.any():
            continue
        country = df.loc[mask, "pays"].iloc[0]
        candidate = normalize_postal_code(row["corrected_postal_code"], country)
        validity = validate_postal_code(candidate, country)
        if validity is False:
            raise ValueError(f"Override CP invalide pour {row['stage_id']}: {candidate}")
        df.loc[mask, "code_postal_final"] = candidate
        df.loc[mask, "postal_code_resolution_method"] = "manual_override"
    return df


def finalize_postal_resolution(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df["code_postal_final"] = pd.Series(
        [normalize_postal_code(cp, country) for cp, country in zip(df["code_postal_final"], df["pays"])],
        index=df.index, dtype="string",
    )
    statuses = pd.Series(
        [final_postal_status(cp, country) for cp, country in zip(df["code_postal_final"], df["pays"])],
        index=df.index, dtype="string",
    )
    invalid = statuses.eq("invalid_country_pattern")
    if invalid.any():
        df.loc[invalid, "code_postal_final"] = pd.NA
        df.loc[invalid, "postal_code_resolution_method"] = "unresolved_invalid_after_resolution"
        statuses.loc[invalid] = "unresolved"
    unresolved = df["code_postal_final"].isna()
    source_invalid = df["postal_code_source_status"].str.contains(r"invalid_format|not_postal_code|suspicious_placeholder", regex=True, na=False)
    source_missing = df["postal_code_source_status"].eq("missing")
    df.loc[unresolved & source_invalid, "postal_code_resolution_method"] = "unresolved_source_invalid"
    df.loc[unresolved & source_missing, "postal_code_resolution_method"] = "unresolved_source_missing"
    df.loc[unresolved & ~(source_invalid | source_missing), "postal_code_resolution_method"] = "unresolved"
    df["postal_code_final_status"] = statuses
    df["code_postal"] = df["code_postal_final"]
    return df
