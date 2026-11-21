"""Jeu de démonstration : identités fictives cohérentes, stages mélangés, overrides suivis.

Les noms de ce fichier sont inventés pour les tests.
"""

import pandas as pd

from stages_cleaning.identity import check_identity, classify_identity_variants
from stages_cleaning.provenance import build_stage_id
from stages_cleaning.synthetic import (
    STAGE_COLUMNS,
    apply_case,
    fake_address,
    leaked_values,
    make_synthetic,
    norm_token,
    remap_stage_overrides,
)


def _row(etudiant, email, entreprise, programme="Ingénieur 2", ville="Paris"):
    return {
        "programme": programme,
        "annee_academique": "2024-2025",
        "etudiant": etudiant,
        "type_stage": "Stage",
        "entreprise": entreprise,
        "adresse": "12 rue des Lilas",
        "code_postal": "75011",
        "ville": ville,
        "pays": "FR",
        "email": email,
        "intitule_poste": pd.NA,
        "libelle_stage": "Stage",
    }


def _raw():
    rows = [
        _row("BRUNELLE, ODILE", "odile.brunelle@efrei.net", "ACME"),
        _row("BRUNÉLLE,Odile", "odile.brunelle@efrei.net", "ACME"),  # accents et espaces
        _row("TAVERNIER, MAXENCE GUSTAVE", "maxence.gustave.tavernier@efrei.net", "Globex"),
        _row("TAVERNIER, MAXENCEGUSTAVE", "maxence.gustave.tavernier@efrei.net", "Globex"),
        _row("LE GOARNIG,Yanis", "yanis.le-goarnig@efrei.net", "Initech"),
        _row("FERRAGUT, ROMANE", "r.ferragut@efrei.net", "Umbrella"),
        _row("QUINTARD, NOE", "noe.quintard@efrei.net", "Hooli"),
        _row("QUINTARD, NOE", "noe.quintard@efrei.net", "Hooli"),  # doublon exact
        _row("SAUVANET, ILONA", "ilona.sauvanet@efrei.net", "Stark"),
        _row("DELORME, BASILE", "basile.delorme@efrei.net", "Wayne"),
    ]
    return pd.DataFrame(rows).astype("string")


def test_no_real_identity_survives():
    raw = _raw()
    fake = make_synthetic(raw, seed=1).frame
    assert leaked_values(raw, fake) == {"names": 0, "email_locals": 0}
    real_words = {"brunelle", "tavernier", "maxence", "goarnig", "ferragut", "quintard", "sauvanet"}
    text = " ".join(fake["etudiant"].str.lower()) + " " + " ".join(fake["email"].str.lower())
    assert not any(w in norm_token(text) for w in real_words)


def test_identity_anomalies_are_preserved():
    raw = _raw()
    fake = make_synthetic(raw, seed=1).frame
    for rows in ([0, 1], [2, 3]):
        assert classify_identity_variants(fake.loc[rows, "etudiant"]) == classify_identity_variants(
            raw.loc[rows, "etudiant"]
        )
    for i in range(len(raw)):
        assert check_identity(fake.loc[i, "etudiant"], fake.loc[i, "email"]) == check_identity(
            raw.loc[i, "etudiant"], raw.loc[i, "email"]
        )
    assert fake.duplicated().sum() == raw.duplicated().sum()
    assert fake.loc[4, "etudiant"].startswith("LE ")  # particule conservée


def test_case_and_accents_are_copied():
    assert apply_case("DUPONT", "martin") == "MARTIN"
    assert apply_case("Dupont", "martin") == "Martin"
    assert norm_token(apply_case("BRUNÉLLE", "lefort")) == "lefort"
    assert apply_case("BRUNÉLLE", "lefort") != "LEFORT"


def test_stages_are_moved_to_other_students():
    raw = _raw()
    fake = make_synthetic(raw, seed=3).frame
    moved = (fake["entreprise"] != raw["entreprise"]).sum()
    assert moved >= len(raw) - 2  # les doublons voyagent ensemble
    assert sorted(fake["entreprise"]) == sorted(raw["entreprise"])
    assert (fake["programme"] == raw["programme"]).all()


def test_addresses_get_new_street_numbers():
    assert fake_address("12 rue des Lilas", 1) != "12 rue des Lilas"
    assert fake_address("12 rue des Lilas", 1) == fake_address("12 rue des Lilas", 1)
    assert fake_address("rue sans numéro", 1) == "rue sans numéro"


def test_stage_overrides_follow_the_moved_stage():
    raw = _raw()
    result = make_synthetic(raw, seed=2)
    real_id = str(build_stage_id(raw).iloc[5])  # stage Umbrella
    overrides = pd.DataFrame({"stage_id": [real_id], "corrected_city": ["Lyon"], "reason": ["test"]})
    remapped = remap_stage_overrides(overrides, result.stage_id_map)
    new_ids = build_stage_id(result.frame)
    target = result.frame.loc[new_ids == remapped.loc[0, "stage_id"]]
    assert len(target) == 1
    assert target.iloc[0]["entreprise"] == "Umbrella"
    assert set(STAGE_COLUMNS) <= set(result.frame.columns)


def test_generation_is_deterministic():
    raw = _raw()
    a = make_synthetic(raw, seed=5).frame
    b = make_synthetic(raw, seed=5).frame
    pd.testing.assert_frame_equal(a, b)
