import pandas as pd
import pytest

from stages_cleaning.company import (
    apply_company_canonicalization,
    assign_company_family,
    build_company_candidates,
    company_quality,
    enrich_company_normalization,
    get_company_family,
    normalize_company_name,
    validate_decisions,
)


def test_normalize_company_name_strips_legal_forms_and_accents():
    assert normalize_company_name("SAS Électricité de France") == "edf"
    assert normalize_company_name("BNP Paribas SA") == "bnp paribas"
    assert normalize_company_name("  ") is pd.NA
    assert pd.isna(normalize_company_name(pd.NA))


def test_normalize_company_name_handles_spaced_legal_forms_and_registration_numbers():
    assert normalize_company_name("Entreprise Test S A S U SIRET 12345678901234") == "entreprise test"


def test_company_quality_classifies_edge_cases():
    assert company_quality(pd.NA) == "missing"
    assert company_quality("sas") == "legal_form_only"
    assert company_quality("fonction publique") == "generic_label"
    assert company_quality("x") == "suspicious"
    assert company_quality("bnp paribas") == "ok"


def test_enrich_company_normalization_adds_expected_columns():
    frame = pd.DataFrame({"entreprise": ["BNP Paribas SA", "SAS", pd.NA]})
    result = enrich_company_normalization(frame)
    assert result["entreprise_normalisee"].tolist() == ["bnp paribas", "sas", pd.NA]
    assert result["entreprise_qualite"].tolist() == ["ok", "legal_form_only", "missing"]


def test_build_company_candidates_finds_near_duplicates_above_threshold():
    frame = pd.DataFrame({
        "entreprise_normalisee": ["bnp paribas", "bnp paribas cib", "orange", "orange"],
        "entreprise_qualite": ["ok", "ok", "ok", "ok"],
    })
    candidates = build_company_candidates(frame, min_similarity=0.5)
    assert not candidates.empty
    assert set(candidates["suggestion"]).issubset({"merge_probable", "review", "weak_candidate"})


def test_build_company_candidates_empty_with_fewer_than_two_companies():
    frame = pd.DataFrame({"entreprise_normalisee": ["orange"], "entreprise_qualite": ["ok"]})
    candidates = build_company_candidates(frame)
    assert candidates.empty


def test_validate_decisions_rejects_unknown_values():
    with pytest.raises(ValueError):
        validate_decisions(pd.DataFrame({"decision": ["merge", "keep_both"]}))


def test_apply_company_canonicalization_only_merges_approved_pairs():
    frame = pd.DataFrame({
        "entreprise_normalisee": ["bnp paribas", "bnp paribas cib", "orange sa", "orange business"],
        "entreprise_qualite": ["ok", "ok", "ok", "ok"],
    })
    decisions = pd.DataFrame({
        "entreprise_1": ["bnp paribas", "orange sa"],
        "entreprise_2": ["bnp paribas cib", "orange business"],
        "decision": ["merge", "review"],
        "entreprise_canonique": ["bnp paribas", pd.NA],
    })
    result = apply_company_canonicalization(frame, decisions)
    assert result.loc[0, "entreprise_canonique"] == "bnp paribas"
    assert result.loc[1, "entreprise_canonique"] == "bnp paribas"
    # "review" n'est pas "merge" : aucune fusion ne doit avoir lieu.
    assert result.loc[2, "entreprise_canonique"] == "orange sa"
    assert result.loc[3, "entreprise_canonique"] == "orange business"


def test_apply_company_canonicalization_prefers_manual_canonical_over_frequency():
    frame = pd.DataFrame({
        "entreprise_normalisee": ["orange sa", "orange"],
        "entreprise_qualite": ["ok", "ok"],
    })
    decisions = pd.DataFrame({
        "entreprise_1": ["orange sa"],
        "entreprise_2": ["orange"],
        "decision": ["merge"],
        "entreprise_canonique": ["orange"],
    })
    result = apply_company_canonicalization(frame, decisions)
    assert set(result["entreprise_canonique"]) == {"orange"}


def test_get_company_family_matches_known_prefix_and_falls_back_to_value():
    assert get_company_family("bnp paribas cib") == "bnp paribas"
    assert get_company_family("une entreprise inconnue") == "une entreprise inconnue"
    assert pd.isna(get_company_family(pd.NA))


def test_assign_company_family_adds_column():
    frame = pd.DataFrame({"entreprise_canonique": ["thales six gts", "petite structure inconnue"]})
    result = assign_company_family(frame)
    assert result["entreprise_famille"].tolist() == ["thales", "petite structure inconnue"]
