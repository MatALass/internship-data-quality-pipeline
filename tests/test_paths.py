from pathlib import Path

import pytest

from stages_cleaning.paths import dataset_paths, network_enabled, resolve_dataset


def _make(root: Path, real: bool) -> Path:
    (root / "data" / "demo").mkdir(parents=True)
    (root / "data" / "demo" / "stages_demo_raw.csv").write_text("x", encoding="utf-8")
    if real:
        (root / "data" / "raw").mkdir(parents=True)
        (root / "data" / "raw" / "stages_efrei_raw.csv").write_text("x", encoding="utf-8")
    return root


def test_auto_prefers_real_export_when_present(tmp_path):
    assert resolve_dataset(_make(tmp_path, real=True), {}) == "real"


def test_auto_falls_back_to_demo(tmp_path):
    paths = dataset_paths(_make(tmp_path, real=False), {})
    assert paths.name == "demo"
    assert paths.location_overrides.parts[-2:] == ("demo", "location_overrides.csv")


def test_explicit_choice_and_errors(tmp_path):
    root = _make(tmp_path, real=False)
    assert dataset_paths(root, {"STAGES_DATASET": "demo"}).name == "demo"
    with pytest.raises(FileNotFoundError):
        dataset_paths(root, {"STAGES_DATASET": "real"})
    with pytest.raises(ValueError):
        resolve_dataset(root, {"STAGES_DATASET": "prod"})


def test_network_flag():
    assert network_enabled({}) is True
    assert network_enabled({"STAGES_RUN_NETWORK": "0"}) is False
