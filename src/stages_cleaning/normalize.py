from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd
import pycountry

COUNTRY_ALIASES = {
    "FRANCE": "FR",
    "FRA": "FR",
    "UK": "GB",
    "UNITED KINGDOM": "GB",
}

CITY_COUNTRY_SUFFIXES = {
    "cambodia", "cambodge", "france", "morocco", "maroc", "laos",
    "sri lanka", "switzerland", "suisse",
}


def strip_accents(value: Any) -> str:
    if pd.isna(value):
        return ""
    return unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()


def normalize_text_key(value: Any) -> str:
    text = strip_accents(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_address_key(value: Any) -> str:
    """Clé de rapprochement d'adresse ; ne remplace jamais la valeur affichée."""
    return normalize_text_key(value)


def normalize_city_for_geocoding(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    text = re.sub(r"(?i)\bc[eé]?dex\b.*$", "", text)
    text = re.sub(r"(?i)\bcdx\b.*$", "", text)
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text)
    text = text.replace("/", " ")
    text = re.sub(r"\s+", " ", text).strip(" ,-;")
    return text or pd.NA


def normalize_city_key(value: Any) -> str:
    cleaned = normalize_city_for_geocoding(value)
    if pd.isna(cleaned):
        return ""
    key = normalize_text_key(cleaned)
    for suffix in sorted(CITY_COUNTRY_SUFFIXES, key=len, reverse=True):
        if key.endswith(f" {suffix}"):
            key = key[: -(len(suffix) + 1)].strip()
            break
    return key


def normalize_country_code(value: Any) -> Any:
    """Convertit une valeur pays en ISO-3166 alpha-2 sans règle propre au dataset."""
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if not text:
        return pd.NA
    upper = strip_accents(text).upper().strip()
    if upper in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[upper]
    if re.fullmatch(r"[A-Z]{2}", upper):
        country = pycountry.countries.get(alpha_2=upper)
        return country.alpha_2 if country else pd.NA
    try:
        return pycountry.countries.lookup(text).alpha_2
    except LookupError:
        try:
            return pycountry.countries.lookup(upper).alpha_2
        except LookupError:
            return pd.NA


def is_iso_alpha2(value: Any) -> bool:
    if pd.isna(value):
        return False
    code = str(value).strip().upper()
    return bool(re.fullmatch(r"[A-Z]{2}", code) and pycountry.countries.get(alpha_2=code))
