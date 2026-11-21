from __future__ import annotations

import re
import ssl
from pathlib import Path
from typing import Callable, Iterable

import certifi
import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim


def location_key(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    cols = list(columns)
    return frame[cols].fillna("").astype("string").agg(" | ".join, axis=1)


def unique_mapping_with_support(reference: pd.DataFrame, keys: list[str], value_col: str) -> pd.DataFrame:
    """Mapping des clés non ambiguës avec nombre d'observations de support."""
    ref = reference.dropna(subset=keys + [value_col]).copy()
    grouped = ref.groupby(keys, dropna=False)[value_col]
    stats = grouped.agg(target="first", n_values=lambda s: s.nunique(dropna=True), support="size")
    return stats.loc[stats["n_values"].eq(1), ["target", "support"]]


def apply_mapping(frame: pd.DataFrame, keys: list[str], mapping: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if len(keys) == 1:
        key_values = frame[keys[0]]
    else:
        key_values = pd.MultiIndex.from_frame(frame[keys])
    candidate = pd.Series(key_values.map(mapping["target"]), index=frame.index, dtype="string")
    support = pd.Series(key_values.map(mapping["support"]), index=frame.index, dtype="Int64")
    return candidate, support


def load_cache(path: str | Path, columns: list[str], key_col: str = "location_key") -> pd.DataFrame:
    path = Path(path)
    if path.exists():
        cache = pd.read_csv(path, dtype="string", encoding="utf-8-sig", keep_default_na=False).replace("", pd.NA)
    else:
        cache = pd.DataFrame(columns=columns)
    for col in columns:
        if col not in cache.columns:
            cache[col] = pd.NA
    cache = cache[columns]
    if key_col in cache.columns:
        # Un cache édité/concaténé à la main peut contenir des doublons ; une clé dupliquée
        # multiplierait silencieusement des lignes lors des jointures how="left".
        cache = cache.drop_duplicates(key_col, keep="last").reset_index(drop=True)
    return cache


def save_cache(cache: pd.DataFrame, path: str | Path, key_col: str = "location_key") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cache.drop_duplicates(key_col, keep="last").to_csv(path, index=False, encoding="utf-8-sig")


def build_geocoder(user_agent: str, min_delay_seconds: float = 1.0) -> Callable:
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    geolocator = Nominatim(user_agent=user_agent, timeout=10, ssl_context=ssl_context)
    return RateLimiter(
        geolocator.geocode,
        min_delay_seconds=min_delay_seconds,
        max_retries=2,
        error_wait_seconds=5,
        # swallow_exceptions=True transformait toute panne réseau en résultat None,
        # ensuite mis en cache comme "not_found" définitif (jamais retenté).
        swallow_exceptions=False,
    )



UNIT_NOISE = re.compile(r"(?i)\b(unit|suite|bureau|floor|andar|étage|etage|apt|appartement|niveau|piso)\b[^,]*")


def simplified_address_queries(address, city) -> list[tuple[str, str]]:
    """Construit des variantes d'adresse conservatrices sans repli sur la ville seule."""
    if pd.isna(address) or pd.isna(city):
        return []
    queries: list[tuple[str, str]] = []
    cleaned = UNIT_NOISE.sub("", str(address)).strip(" ,.-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned and cleaned.casefold() != str(address).casefold():
        queries.append((f"{cleaned}, {city}", "address_simplified_geocode"))
    for part in re.split(r"[;,/]|\bET\b", str(address), flags=re.IGNORECASE):
        part = part.strip(" ,.-")
        if len(part) >= 5:
            queries.append((f"{part}, {city}", "address_segment_geocode"))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for query, method in queries:
        if query not in seen:
            seen.add(query)
            unique.append((query, method))
    return unique

def complete_country_cache(
    locations: pd.DataFrame,
    cache_path: str | Path,
    run_network: bool = False,
) -> pd.DataFrame:
    """Complète le cache pays pour des colonnes adresse/code_postal/ville.

    En mode hors réseau, retourne simplement le cache disponible. Cette fonction
    centralise la mécanique Nominatim utilisée par le notebook pays.
    """
    from .postal import is_suspicious_placeholder

    cols = ["location_key", "pays_geocode", "geocode_method", "geocode_query"]
    cache = load_cache(cache_path, cols)
    todo = locations.drop_duplicates("location_key")
    todo = todo[~todo["location_key"].isin(cache["location_key"])].copy()
    if not run_network or todo.empty:
        return cache

    geocode = build_geocoder("student-country-cleaning-project")
    results = []
    network_failed = False
    for _, row in todo.iterrows():
        address, cp, city = row.get("adresse"), row.get("code_postal"), row.get("ville")
        queries = []
        if pd.notna(cp) and pd.notna(city) and not is_suspicious_placeholder(cp):
            queries.append((f"{cp}, {city}", "postal_code_city_geocode"))
        if pd.notna(address) and pd.notna(city):
            queries.append((f"{address}, {city}", "address_city_geocode"))
        if pd.notna(city):
            queries.append((str(city), "city_geocode"))
        country, method, query_used = pd.NA, "not_found", pd.NA
        try:
            for query, method_name in queries:
                loc = geocode(query, addressdetails=True, exactly_one=True, language="en")
                code = loc.raw.get("address", {}).get("country_code") if loc else None
                if code:
                    country, method, query_used = code.upper(), method_name, query
                    break
        except Exception as exc:  # noqa: BLE001 — une panne réseau ne doit JAMAIS être cachée comme not_found
            print(f"Géocodage interrompu ({type(exc).__name__}: {exc}) ; "
                  f"{len(results)} résultat(s) conservé(s), le reste sera retenté au prochain run.")
            network_failed = True
            break
        results.append({
            "location_key": row["location_key"],
            "pays_geocode": country,
            "geocode_method": method,
            "geocode_query": query_used,
        })
    if results:
        cache = pd.concat([cache, pd.DataFrame(results)], ignore_index=True)
        save_cache(cache, cache_path)
    if network_failed:
        print("⚠ Géocodage pays incomplet : relancer le notebook une fois le réseau rétabli.")
    return load_cache(cache_path, cols)


def complete_postal_cache(
    locations: pd.DataFrame,
    cache_path: str | Path,
    normalize_postal,
    validate_postal,
    run_network: bool = False,
) -> pd.DataFrame:
    """Complète le cache code postal avec contrainte pays."""
    cols = ["location_key", "postal_code_geocode", "geocode_method", "geocode_query"]
    cache = load_cache(cache_path, cols)
    todo = locations.drop_duplicates("location_key")
    todo = todo[~todo["location_key"].isin(cache["location_key"])].copy()
    if not run_network or todo.empty:
        return cache

    geocode = build_geocoder("student-postal-code-cleaning-project")
    results = []
    network_failed = False
    for _, row in todo.iterrows():
        address, city, country = row.get("adresse"), row.get("ville"), row.get("pays")
        queries = []
        if pd.notna(address) and pd.notna(city):
            queries.append((f"{address}, {city}", "address_city_geocode"))
        if pd.notna(address):
            queries.append((str(address), "address_geocode"))
        queries.extend(simplified_address_queries(address, city))
        postcode, method, query_used = pd.NA, "not_found", pd.NA
        try:
            for query, method_name in queries:
                loc = geocode(
                    query,
                    addressdetails=True,
                    exactly_one=True,
                    language="en",
                    country_codes=str(country).lower() if pd.notna(country) else None,
                )
                raw_postcode = loc.raw.get("address", {}).get("postcode") if loc else None
                if raw_postcode:
                    candidate = normalize_postal(raw_postcode, country)
                    if validate_postal(candidate, country) is not False:
                        postcode, method, query_used = candidate, method_name, query
                        break
        except Exception as exc:  # noqa: BLE001
            print(f"Géocodage interrompu ({type(exc).__name__}: {exc}) ; "
                  f"{len(results)} résultat(s) conservé(s), le reste sera retenté au prochain run.")
            network_failed = True
            break
        results.append({
            "location_key": row["location_key"],
            "postal_code_geocode": postcode,
            "geocode_method": method,
            "geocode_query": query_used,
        })
    if results:
        cache = pd.concat([cache, pd.DataFrame(results)], ignore_index=True)
        save_cache(cache, cache_path)
    if network_failed:
        print("⚠ Géocodage CP incomplet : relancer le notebook une fois le réseau rétabli.")
    return load_cache(cache_path, cols)
