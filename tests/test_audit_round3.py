"""Tests ajoutés suite à l'audit round 3 (voir AUDIT_FIXES.md).

Couvre les correctifs les plus dangereux identifiés par l'audit : canonisation d'identité
avec emails manquants, refus de correction automatique par homonymie de ville, caches de
géocodage corrompus, inférence de code postal sur preuve trop faible et overrides orphelins.
"""
from __future__ import annotations

import pandas as pd
import pytest

from stages_cleaning.company import reconcile_merge_decisions
from stages_cleaning.country import (
    apply_country_geocode_cache,
    apply_country_overrides,
    correct_source_conflicts_from_geocode,
)
from stages_cleaning.geocode import load_cache
from stages_cleaning.identity import apply_identity_cleaning
from stages_cleaning.postal import apply_postal_overrides, infer_postal_from_valid_source

EMPTY_IDENTITY_OVERRIDES = pd.DataFrame(columns=["source_identity", "corrected_identity", "reason"])


# --- S-2 : identité --------------------------------------------------------------------

def test_identity_missing_email_never_canonicalized():
    frame = pd.DataFrame({
        "stage_id": ["a", "b", "c", "d"],
        "etudiant": ["NAJERA, LEA", "NAJÉRA, LEA", "ROSARIO, MARIE", "ROSÁRIO,MARIE"],
        "email": pd.array(["lea.najera@efrei.net", "lea.najera@efrei.net", pd.NA, pd.NA], dtype="string"),
    })
    result = apply_identity_cleaning(frame, EMPTY_IDENTITY_OVERRIDES)
    no_email = result["email"].isna()
    assert result.loc[no_email, "nom"].notna().all()
    assert result.loc[no_email, "identity_variant_category"].eq("single").all()
    assert not result.loc[no_email, "identity_canonicalized"].any()
    assert result.loc[no_email, "identity_final_status"].eq("resolved_source").all()


def test_identity_no_comma_dataset_does_not_crash():
    frame = pd.DataFrame({
        "stage_id": ["a"], "etudiant": ["MARTIN"],
        "email": pd.array(["x.martin@efrei.net"], dtype="string"),
    })
    result = apply_identity_cleaning(frame, EMPTY_IDENTITY_OVERRIDES)
    assert result.loc[0, "nom"] == "MARTIN"
    assert pd.isna(result.loc[0, "prenom"])


def test_identity_canonical_without_first_name_clears_prenom():
    # Le canonique majoritaire ("MARTIN", sans virgule) l'emporte sur "MARTIN, JEAN" : le
    # prénom doit être explicitement vidé sur la ligne canonisée (bug (c) de l'audit).
    frame = pd.DataFrame({
        "stage_id": ["a", "b", "c"],
        "etudiant": ["MARTIN", "MARTIN", "MARTIN, JEAN"],
        "email": pd.array(["jean.martin@efrei.net"] * 3, dtype="string"),
    })
    result = apply_identity_cleaning(frame, EMPTY_IDENTITY_OVERRIDES)
    assert bool(result.loc[2, "identity_canonicalized"])
    assert result.loc[2, "nom"] == "MARTIN"
    assert pd.isna(result.loc[2, "prenom"])


# --- S-1 : conflit source/géocodage -----------------------------------------------------

def test_source_conflict_is_flagged_not_overwritten():
    df = pd.DataFrame({
        "stage_id": ["a"], "location_key": ["k1"],
        "pays_geocode": pd.array(["FR"], dtype="string"),
        "geocode_method": pd.array(["address_city_geocode"], dtype="string"),
        "pays_final": pd.array(["US"], dtype="string"),
    })
    out = correct_source_conflicts_from_geocode(df)
    assert out.loc[0, "pays_final"] == "US"
    assert bool(out.loc[0, "country_source_geocode_conflict"])


def test_source_conflict_not_flagged_when_geocode_imprecise():
    df = pd.DataFrame({
        "stage_id": ["a"], "location_key": ["k1"],
        "pays_geocode": pd.array(["FR"], dtype="string"),
        "geocode_method": pd.array(["city_geocode"], dtype="string"),  # homonyme possible
        "pays_final": pd.array(["US"], dtype="string"),
    })
    out = correct_source_conflicts_from_geocode(df)
    assert out.loc[0, "pays_final"] == "US"
    assert not bool(out.loc[0, "country_source_geocode_conflict"])


# --- S-4 : caches de géocodage corrompus -------------------------------------------------

def test_country_cache_duplicate_key_raises():
    df = pd.DataFrame({"stage_id": ["a"], "location_key": ["k1"],
                       "pays_final": pd.array([pd.NA], dtype="string"),
                       "country_resolution_method": pd.array([pd.NA], dtype="string"),
                       "country_resolution_confidence": pd.array([pd.NA], dtype="string")})
    cache = pd.DataFrame({"location_key": ["k1", "k1"], "pays_geocode": ["FR", "DE"],
                          "geocode_method": ["city_geocode", "city_geocode"], "geocode_query": ["q", "q"]})
    with pytest.raises(ValueError, match="dupliquées"):
        apply_country_geocode_cache(df, cache)


def test_load_cache_deduplicates_keys(tmp_path):
    path = tmp_path / "cache.csv"
    pd.DataFrame({
        "location_key": ["k1", "k1", "k2"],
        "pays_geocode": ["FR", "DE", "ES"],
        "geocode_method": ["city_geocode", "city_geocode", "city_geocode"],
        "geocode_query": ["q", "q", "q"],
    }).to_csv(path, index=False, encoding="utf-8-sig")
    cache = load_cache(path, ["location_key", "pays_geocode", "geocode_method", "geocode_query"])
    assert cache["location_key"].is_unique
    assert len(cache) == 2
    # keep="last" : DE l'emporte sur FR pour k1
    assert cache.loc[cache["location_key"].eq("k1"), "pays_geocode"].iloc[0] == "DE"


# --- S-3 : inférence de code postal sur support insuffisant -------------------------------

def test_postal_singleton_stays_unresolved_and_two_observations_is_accepted():
    frame = pd.DataFrame({
        "ville": ["Paris", "Paris", "Paris"],
        "adresse": [pd.NA, pd.NA, pd.NA],
        "pays": ["FR", "FR", "FR"],
        "postal_code_source_status": ["valid", "missing", "missing"],
        "code_postal_normalized_source": pd.array(["75001", pd.NA, pd.NA], dtype="string"),
        "code_postal_final": pd.array(["75001", pd.NA, pd.NA], dtype="string"),
        "postal_code_resolution_method": pd.array(["source", pd.NA, pd.NA], dtype="string"),
    })
    result = infer_postal_from_valid_source(frame)
    # une seule référence valide dans la ville -> support=1 -> pas d'inférence ville+pays
    still_unresolved = result.loc[1:, "code_postal_final"]
    assert still_unresolved.isna().all()

    frame2 = pd.DataFrame({
        "ville": ["Lyon", "Lyon", "Lyon"],
        "adresse": [pd.NA, pd.NA, pd.NA],
        "pays": ["FR", "FR", "FR"],
        "postal_code_source_status": ["valid", "valid", "missing"],
        "code_postal_normalized_source": pd.array(["69001", "69001", pd.NA], dtype="string"),
        "code_postal_final": pd.array(["69001", "69001", pd.NA], dtype="string"),
        "postal_code_resolution_method": pd.array(["source", "source", pd.NA], dtype="string"),
    })
    result2 = infer_postal_from_valid_source(frame2)
    assert result2.loc[2, "code_postal_final"] == "69001"
    assert result2.loc[2, "postal_code_inference_support"] == 2


# --- D-1 : overrides orphelins ------------------------------------------------------------

def test_country_override_orphan_stage_id_raises():
    df = pd.DataFrame({"stage_id": ["a"], "pays_final": pd.array([pd.NA], dtype="string"),
                       "country_resolution_method": pd.array([pd.NA], dtype="string"),
                       "country_resolution_confidence": pd.array([pd.NA], dtype="string"),
                       "country_reference_count": pd.array([pd.NA], dtype="Int64")})
    overrides = pd.DataFrame({"stage_id": ["perime"], "corrected_country": ["FR"]})
    with pytest.raises(ValueError, match="périmés"):
        apply_country_overrides(df, overrides)


def test_postal_override_orphan_stage_id_raises():
    df = pd.DataFrame({"stage_id": ["a"], "pays": pd.array(["FR"], dtype="string"),
                       "code_postal_final": pd.array([pd.NA], dtype="string"),
                       "postal_code_resolution_method": pd.array([pd.NA], dtype="string")})
    overrides = pd.DataFrame({"stage_id": ["perime"], "corrected_postal_code": ["75001"]})
    with pytest.raises(ValueError, match="périmés"):
        apply_postal_overrides(df, overrides)


def test_country_override_non_strict_skips_orphans():
    df = pd.DataFrame({"stage_id": ["a"], "pays_final": pd.array([pd.NA], dtype="string"),
                       "country_resolution_method": pd.array([pd.NA], dtype="string"),
                       "country_resolution_confidence": pd.array([pd.NA], dtype="string"),
                       "country_reference_count": pd.array([pd.NA], dtype="Int64")})
    overrides = pd.DataFrame({"stage_id": ["perime"], "corrected_country": ["FR"]})
    result = apply_country_overrides(df, overrides, strict=False)
    assert pd.isna(result.loc[0, "pays_final"])


# --- D-4 : réconciliation des paires candidates -------------------------------------------

def test_reconcile_merge_decisions_appends_new_pairs_without_overwriting():
    decisions = pd.DataFrame({
        "entreprise_1": ["a", "b"], "entreprise_2": ["b", "c"],
        "decision": ["merge", "distinct"], "entreprise_canonique": ["a", ""],
    })
    candidates = pd.DataFrame({
        "entreprise_1": ["b", "d"], "entreprise_2": ["a", "e"],  # 1ère paire déjà connue (ordre inversé)
    })
    result = reconcile_merge_decisions(candidates, decisions)
    assert len(result) == 3
    # décisions existantes jamais modifiées
    assert result.loc[result["entreprise_1"].eq("a"), "decision"].iloc[0] == "merge"
    new_row = result.loc[result["entreprise_1"].eq("d")]
    assert new_row["decision"].iloc[0] == ""
