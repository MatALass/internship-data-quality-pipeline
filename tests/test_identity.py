import pandas as pd

from stages_cleaning.identity import (
    apply_identity_cleaning,
    check_identity,
    classify_identity_variants,
    split_identity,
)


def test_split_identity_resegments_concatenated_first_names_from_email():
    nom, prenom = split_identity("KOFFI, AKISSIPAULEMARIE", "akissi.paule.marie.koffi@efrei.net")
    assert nom == "KOFFI"
    assert prenom == "AKISSI"


def test_split_identity_handles_missing_value():
    assert split_identity(pd.NA, "x@y.fr") == (pd.NA, pd.NA)


def test_check_identity_accepts_hyphen_as_email_separator():
    assert check_identity("WEN, BO", "bo-wen@efrei.net") is None


def test_classify_secondary_first_names():
    assert classify_identity_variants(["DUPONT, ADRIEN", "DUPONT, ADRIEN JOSEPHCHARLES"]) == "prenoms_secondaires"


def test_classify_accents_and_spacing():
    assert classify_identity_variants(["ROSARIO, MARIE", "ROSÁRIO,MARIE"]) == "accents_espaces"


def test_classify_real_divergence():
    assert classify_identity_variants(["OKAFOR, SAMUEL", "OKAFORNWOSU, SAMUEL"]) == "divergence_reelle"


def test_real_divergence_is_never_canonicalized():
    frame = pd.DataFrame({
        "stage_id": ["a", "b"],
        "etudiant": ["OKAFOR, SAMUEL", "OKAFORNWOSU, SAMUEL"],
        "email": ["samuel.okafor@efrei.net", "samuel.okafor@efrei.net"],
    })
    overrides = pd.DataFrame(columns=["source_identity", "corrected_identity", "reason"])
    result = apply_identity_cleaning(frame, overrides)
    assert result["identity_variant_category"].eq("divergence_reelle").all()
    assert result["identity_requires_review"].all()
    assert not result["identity_canonicalized"].any()
    assert result["nom"].nunique() == 2
