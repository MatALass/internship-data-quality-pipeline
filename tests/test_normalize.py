import pandas as pd

from stages_cleaning.normalize import (
    is_iso_alpha2,
    normalize_address_key,
    normalize_city_key,
    normalize_country_code,
)


def test_country_name_is_mapped_to_iso2():
    assert normalize_country_code("France") == "FR"
    assert normalize_country_code("FRANCE") == "FR"


def test_obsolete_or_ambiguous_code_is_not_decided_by_generic_normalizer():
    assert pd.isna(normalize_country_code("CS"))


def test_invalid_country_is_missing():
    assert pd.isna(normalize_country_code("NOT_A_COUNTRY"))


def test_city_key_collapses_cedex_and_country_suffixes():
    assert normalize_city_key("Orly Aérogare Cedex") == "orly aerogare"
    assert normalize_city_key("Phnom Penh, Cambodge") == "phnom penh"


def test_address_key_collapses_accents_case_and_punctuation():
    assert normalize_address_key("12, Rue de l'École") == normalize_address_key("12 rue de l ecole")


def test_iso_validation():
    assert is_iso_alpha2("FR")
    assert not is_iso_alpha2("FRANCE")
