import pandas as pd
import pytest

from stages_cleaning.postal import (
    extract_embedded_postal_code,
    final_postal_status,
    fix_leading_zeros,
    is_suspicious_placeholder,
    normalize_postal_code,
    postal_code_status,
    prepare_postal_resolution,
    validate_postal_code,
)


@pytest.mark.parametrize(
    ("raw", "country", "expected"),
    [
        ("2100", "FR", "02100"), ("3111", "ES", "03111"), ("92 400", "FR", "92400"),
        ("92\xa0400", "FR", "92400"), ("7755O", "FR", "77550"), ("F-92058", "FR", "92058"),
        ("D-68766", "DE", "68766"), ("Taïwan 237", "TW", "237"), ("CH-2502", "CH", "2502"),
        ("L-2520", "LU", "2520"), ("H4C1P2", "CA", "H4C 1P2"), ("4750.841", "PT", "4750-841"),
        ("5470033", "JP", "547-0033"), ("NSW 2000", "AU", "2000"),
    ],
)
def test_normalize_postal_code(raw, country, expected):
    assert normalize_postal_code(raw, country) == expected


def test_fix_leading_zeros_does_not_modify_alphanumeric():
    assert fix_leading_zeros("H4C1P2", "CA") == "H4C1P2"


def test_validate_fr_and_au_formats():
    assert validate_postal_code("75015", "FR") is True
    assert validate_postal_code("750213", "FR") is False
    assert validate_postal_code("2000", "AU") is True


def test_po_box_is_not_a_postal_code():
    assert postal_code_status("BP 2374", "BP 2374", "FR") == "po_box_not_postal_code"


def test_extract_numeric_postal_code_from_address():
    assert extract_embedded_postal_code("142 rue du Chevaleret - 75013 Paris", "FR") == "75013"


def test_non_postal_text_signals_are_rejected():
    assert postal_code_status("GQGW+9WJ,", "GQGW+9WJ,", "KH", "Phnom Penh") == "plus_code_not_postal_code"
    assert postal_code_status("Phnom Penh", "PHNOM PENH", "KH", "Phnom Penh") == "city_name_not_postal_code"
    assert postal_code_status("Phnom Pehn", "PHNOM PEHN", "KH", "Phnom Penh") == "text_not_postal_code"


def test_placeholder_is_flagged_and_not_accepted_as_source():
    assert is_suspicious_placeholder("99999")
    assert postal_code_status("99999", "99999", pd.NA, "X") == "suspicious_placeholder"
    frame = pd.DataFrame({"code_postal": ["99999"], "pays": [pd.NA], "ville": ["X"]})
    result = prepare_postal_resolution(frame)
    assert pd.isna(result.loc[0, "code_postal_final"])


def test_final_status_distinguishes_validation_coverage():
    assert final_postal_status("75015", "FR") == "valid_country_pattern"
    assert final_postal_status("12345", pd.NA) == "unvalidated_country_missing"
    assert final_postal_status("12345", "KH") == "unvalidated_pattern_unsupported"
