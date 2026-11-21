from __future__ import annotations

import pandas as pd

from .geocode import apply_mapping, unique_mapping_with_support
from .normalize import (
    is_iso_alpha2,
    normalize_city_for_geocoding,
    normalize_city_key,
    normalize_country_code,
)
from .postal import is_suspicious_placeholder, normalize_postal_code, postal_code_match_key


def _check_override_targets(df: pd.DataFrame, overrides: pd.DataFrame, label: str, strict: bool) -> None:
    unmatched = sorted(set(overrides["stage_id"].dropna()) - set(df["stage_id"]))
    if unmatched and strict:
        raise ValueError(
            f"Overrides {label} sans correspondance (stage_id périmés après changement du brut ?) : "
            f"{unmatched}"
        )


def apply_location_overrides(frame: pd.DataFrame, overrides: pd.DataFrame, strict: bool = True) -> pd.DataFrame:
    df = frame.copy()
    if "ville_source_raw" not in df.columns:
        df["ville_source_raw"] = df["ville"]
    df["city_resolution_method"] = "source"
    if overrides.empty:
        return df
    _check_override_targets(df, overrides, "localisation", strict)
    by_stage = overrides.dropna(subset=["stage_id"]).set_index("stage_id")
    for stage_id, row in by_stage.iterrows():
        mask = df["stage_id"].eq(stage_id)
        if not mask.any():
            continue
        if pd.notna(row.get("corrected_city")):
            df.loc[mask, "ville"] = row["corrected_city"]
            df.loc[mask, "city_resolution_method"] = "manual_override"
    return df


def prepare_country_columns(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df["pays_source_raw"] = df["pays"]
    df["pays_source"] = df["pays"].map(normalize_country_code).astype("string")
    df["country_source_status"] = "missing"
    present = df["pays_source_raw"].notna()
    valid = present & df["pays_source"].notna()
    normalized = valid & df["pays_source_raw"].str.upper().ne(df["pays_source"])
    invalid = present & df["pays_source"].isna()
    df.loc[valid, "country_source_status"] = "valid"
    df.loc[normalized, "country_source_status"] = "normalized"
    df.loc[invalid, "country_source_status"] = "invalid_unmapped"

    if "code_postal_source_raw" not in df.columns:
        df["code_postal_source_raw"] = df["code_postal"]
    df["code_postal"] = pd.Series(
        [normalize_postal_code(cp, country) for cp, country in zip(df["code_postal_source_raw"], df["pays_source"])],
        index=df.index, dtype="string",
    )
    df["_ville_geocode"] = df["ville"].map(normalize_city_for_geocoding).astype("string")
    df["_ville_key"] = df["ville"].map(normalize_city_key).replace("", pd.NA).astype("string")
    df["_cp_key"] = df["code_postal"].map(postal_code_match_key).replace("", pd.NA).astype("string")
    placeholder = df["code_postal"].map(is_suspicious_placeholder)
    df.loc[placeholder, "_cp_key"] = pd.NA
    return df


def infer_country_from_source(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df["pays_final"] = df["pays_source"]
    df["country_resolution_method"] = pd.NA
    df["country_resolution_confidence"] = pd.NA
    df["country_reference_count"] = pd.Series(pd.NA, index=df.index, dtype="Int64")

    source_present = df["pays_source"].notna()
    source_normalized = source_present & df["country_source_status"].eq("normalized")
    df.loc[source_present, "country_resolution_method"] = "source"
    df.loc[source_present, "country_resolution_confidence"] = "high"
    df.loc[source_normalized, "country_resolution_method"] = "source_normalized"

    reference = df[df["pays_source"].notna()].copy()
    rules = [
        (["_cp_key", "_ville_key"], "postal_code_city", 2),
        (["_ville_key"], "city_unique_source", 3),
    ]
    for keys, method, high_threshold in rules:
        mapping = unique_mapping_with_support(reference, keys, "pays_source")
        candidate, support = apply_mapping(df, keys, mapping)
        mask = df["pays_final"].isna() & candidate.notna()
        df.loc[mask, "pays_final"] = candidate[mask]
        df.loc[mask, "country_resolution_method"] = method
        df.loc[mask, "country_reference_count"] = support[mask]
        if method == "postal_code_city":
            confidence = support.ge(high_threshold).map({True: "high", False: "medium"})
        else:
            confidence = support.ge(high_threshold).map({True: "medium", False: "low"})
        df.loc[mask, "country_resolution_confidence"] = confidence[mask]
    return df


def apply_country_overrides(frame: pd.DataFrame, overrides: pd.DataFrame, strict: bool = True) -> pd.DataFrame:
    df = frame.copy()
    if overrides.empty:
        return df
    by_stage = overrides.dropna(subset=["stage_id", "corrected_country"]).set_index("stage_id")
    _check_override_targets(df, by_stage.reset_index(), "pays", strict)
    for stage_id, row in by_stage.iterrows():
        country = normalize_country_code(row["corrected_country"])
        if pd.isna(country):
            raise ValueError(f"Override pays invalide pour {stage_id}: {row['corrected_country']}")
        mask = df["stage_id"].eq(stage_id)
        df.loc[mask, "pays_final"] = country
        df.loc[mask, "country_resolution_method"] = "manual_override"
        df.loc[mask, "country_resolution_confidence"] = "manual"
        df.loc[mask, "country_reference_count"] = pd.NA
    return df


def finalize_country(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    invalid = df["pays_final"].notna() & ~df["pays_final"].map(is_iso_alpha2)
    if invalid.any():
        raise ValueError(f"Pays finaux non ISO-2 : {sorted(df.loc[invalid, 'pays_final'].unique())}")
    unresolved = df["pays_final"].isna()
    df.loc[unresolved, "country_resolution_method"] = "unresolved"
    df.loc[unresolved, "country_resolution_confidence"] = "unresolved"
    df["pays"] = df["pays_final"]
    return df


GEOCODE_CONFIDENCE = {
    "postal_code_city_geocode": "geocoded",
    "address_city_geocode": "geocoded",
    "verified_cache_seed": "geocoded",
    "city_geocode": "geocoded_low",  # ville seule : ambiguïté d'homonymes possible
}


def apply_country_geocode_cache(frame: pd.DataFrame, cache: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    if cache.empty:
        return df
    duplicated = cache["location_key"].duplicated()
    if duplicated.any():
        raise ValueError(
            "Cache de géocodage pays corrompu : location_key dupliquées "
            f"{sorted(cache.loc[duplicated, 'location_key'].unique())[:5]}"
        )
    n_before = len(df)
    df = df.merge(cache, on="location_key", how="left")
    if len(df) != n_before:
        raise ValueError("La jointure du cache pays a modifié la cardinalité du dataset")
    mask = df["pays_final"].isna() & df["pays_geocode"].notna()
    candidate = df.loc[mask, "pays_geocode"].map(normalize_country_code)
    df.loc[mask, "pays_final"] = candidate
    df.loc[mask, "country_resolution_method"] = df.loc[mask, "geocode_method"]
    df.loc[mask, "country_resolution_confidence"] = (
        df.loc[mask, "geocode_method"].map(GEOCODE_CONFIDENCE).fillna("geocoded_low")
    )
    return df


def correct_source_conflicts_from_geocode(frame: pd.DataFrame) -> pd.DataFrame:
    """Signale (sans la corriger) une source contredite par une preuve géocodée exacte.

    Une correction automatique par homonymie de ville a été jugée dangereuse : la « preuve »
    par ville provenait uniquement de lignes qui n'avaient pas de pays source, et pouvait
    écraser un pays déclaré légitime (ex. Paris, US) avec une confiance affichée "high".
    On applique le principe du projet : « une règle détecte un fait observable, pas une
    correction supposée ». La colonne ``country_source_geocode_conflict`` alimente le
    registre d'anomalies ; la correction passe par ``config/location_overrides.csv``.
    """
    df = frame.copy()
    required = {"pays_geocode", "geocode_method", "location_key"}
    df["country_source_geocode_conflict"] = pd.Series(False, index=df.index, dtype="boolean")
    if not required <= set(df.columns):
        return df
    own_geo = df["pays_geocode"].map(normalize_country_code).astype("string")
    precise = df["geocode_method"].isin({"postal_code_city_geocode", "address_city_geocode", "verified_cache_seed"})
    conflict = df["pays_final"].notna() & own_geo.notna() & precise & df["pays_final"].ne(own_geo)
    df.loc[conflict, "country_source_geocode_conflict"] = True
    return df
