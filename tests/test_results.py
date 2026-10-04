"""Узгодженість збережених результатів (docs/results/experiments.json) з розрахунками."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qrv1 import analysis, layout

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs" / "results" / "experiments.json"

pytestmark = pytest.mark.skipif(not PATH.exists(), reason="експерименти ще не запускалися")


@pytest.fixture(scope="module")
def results() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_exact_curves_match_formulas(results) -> None:
    ex = results["random_errors"]
    for i, k in enumerate(ex["k"]):
        assert ex["exact"]["kata"][i] == pytest.approx(float(analysis.kata_success(k, 7)))
        for name, lv in layout.LEVELS.items():
            assert ex["exact"][name][i] == pytest.approx(float(analysis.rs_success(k, lv.correctable)))


def test_simulation_agrees_with_exact_values(results) -> None:
    ex = results["random_errors"]
    for point in ex["simulation"]:
        k, n = point["k"], point["trials"]
        i = ex["k"].index(k)
        tolerance = 4 * (0.25 / n) ** 0.5 + 1e-9          # чотири стандартні похибки
        assert abs(point["kata"]["correct"] / n - ex["exact"]["kata"][i]) < tolerance
        assert abs(point["full_h"]["correct"] / n - ex["exact"]["H"][i]) < tolerance
        assert point["full_h"]["wrong"] == 0                # хибного тексту не з'явилося


def test_samples_audit(results) -> None:
    cases = results["samples"]["cases"]
    assert all(c["kata"] == c["expected"] for c in cases)
    for c in cases:
        valid = c["source"] != "csharp"
        assert (c["full"] == c["expected"]) == valid
        assert c["encoder_identical"] == valid
        if c["source"] == "csharp":
            assert c["codewords_differing_from_python"] == list(range(10, 25))
    assert results["csharp_diff"]["codewords_differing"] == list(range(10, 25))


def test_anatomy_bits(results) -> None:
    a = results["anatomy"]
    assert a["fields"]["mode"] == "0100" and a["fields"]["length"] == "00000111"
    assert "".join(chr(int(b, 2)) for b in a["fields"]["text"]) == "Warrior"
    assert sum(a["module_kinds"].values()) == 441 and a["module_kinds"]["data"] == 208


def test_erasures_never_worse_than_errors(results) -> None:
    for row in results["blocks"]["sides"]:
        assert row["erasures"]["correct"] >= row["errors"]["correct"]
        assert row["errors"]["wrong"] == 0


def test_forgery_numbers(results) -> None:
    f = results["forgery"]
    assert len(f["codewords_differing"]) >= f["min_distance"] == 18
    assert len(f["codewords_rewritten"]) == len(f["codewords_differing"]) - f["t"]
    assert f["forged_decoded"] == "PAY 900" and f["small_decoded"] == "PAY 100"


def test_capacity_table(results) -> None:
    assert results["capacity"]["H"] == {"data": 9, "ecc": 17, "t": 8, "p": 1,
                                        "numeric": 17, "alphanumeric": 10, "byte": 7}
