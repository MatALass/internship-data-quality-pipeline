import pandas as pd

from stages_cleaning.programme import (
    assign_major_canonical,
    enrich_programme_features,
    major_canonicalization_issues,
)


def test_swim_and_international_concepts_are_separate():
    frame = pd.DataFrame({
        "programme": ["Ingé 2 Paris [SWIM]", "Ingénieur 2 - Data Engineering", "Prépa 1"],
        "pays": ["FR", "DE", pd.NA],
        "type_stage": ["Stage technique", "SWIM", "Stage technique"],
    })
    result = enrich_programme_features(frame)
    assert result["is_swim_program"].tolist() == [True, False, False]
    assert result["is_swim_stage"].tolist() == [False, True, False]
    assert result["is_international_stage"].tolist()[:2] == [False, True]
    assert pd.isna(result.loc[2, "is_international_stage"])


def test_major_status_distinguishes_not_applicable_and_not_declared():
    frame = pd.DataFrame({
        "programme": ["Prépa 1", "Ingénieur 3 -", "Ingénieur 2 - Data Engineering"],
        "pays": ["FR", "FR", "FR"],
        "type_stage": ["Stage technique"] * 3,
    })
    result = enrich_programme_features(frame)
    assert result["major_status"].tolist() == ["not_applicable", "not_declared", "available"]


def test_major_canonical_renames_known_legacy_labels():
    frame = pd.DataFrame({"major": ["Ingénierie Cyber Sécurité", "Bio-Informatique", pd.NA]})
    result = assign_major_canonical(frame)
    assert result["major_canonical"].iloc[0] == "Cybersécurité & Réseaux"
    assert result["major_canonical"].iloc[1] == "Bio & Numérique"
    assert pd.isna(result["major_canonical"].iloc[2])
    assert result["major_canonical_status"].iloc[0] == "official"
    assert result["major_canonical_status"].iloc[1] == "official"
    assert pd.isna(result["major_canonical_status"].iloc[2])
    assert result["programme_groupe"].iloc[0] == "Technologie & Numérique"
    assert result["programme_groupe"].iloc[1] == "Data Science"
    assert pd.isna(result["programme_groupe"].iloc[2])


def test_major_canonical_keeps_discontinued_major_untouched():
    frame = pd.DataFrame({"major": ["Digital Transformation"]})
    result = assign_major_canonical(frame)
    assert result["major_canonical"].iloc[0] == "Digital Transformation"
    assert result["major_canonical_status"].iloc[0] == "kept_as_is"


def test_major_canonical_pending_review_is_never_emptied():
    frame = pd.DataFrame({"major": ["Business & Nouvelles Technologies"]})
    result = assign_major_canonical(frame)
    # La valeur brute est conservée telle quelle : pas de renommage forcé, pas de valeur vide.
    assert result["major_canonical"].iloc[0] == "Business & Nouvelles Technologies"
    assert result["major_canonical_status"].iloc[0] == "pending_review"
    assert result["programme_groupe"].iloc[0] == "Digital & Management"


def test_major_canonicalization_issues_is_empty_for_known_dataset():
    frame = pd.DataFrame({"major": ["Cybersécurité & Ethical Hacking", "Digital Transformation",
                                     "Business & Nouvelles Technologies", pd.NA]})
    result = assign_major_canonical(frame)
    assert major_canonicalization_issues(result).empty


def test_major_canonicalization_issues_flags_truly_unknown_labels():
    frame = pd.DataFrame({"major": ["Un Nouveau Libellé Jamais Vu"]})
    result = assign_major_canonical(frame)
    issues = major_canonicalization_issues(result)
    assert len(issues) == 1
