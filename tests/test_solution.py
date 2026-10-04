"""Самодостатній Python-розв'язок для Codewars (solution/codewars_solution.py)."""

from __future__ import annotations

import importlib.util
import json
import random
from pathlib import Path

import pytest

from qrv1 import capacity, encode, kata_scan
from qrv1.image import matrix_from_text

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests" / "codewars_cases.json").read_text(encoding="utf-8"))["cases"]

_spec = importlib.util.spec_from_file_location("codewars_solution",
                                               ROOT / "solution" / "codewars_solution.py")
solution = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(solution)


@pytest.mark.parametrize("case", CASES, ids=[f"{c['source']}-{c['expected']}" for c in CASES])
def test_solution_reads_samples(case) -> None:
    assert solution.scanner(matrix_from_text("\n".join(case["matrix"]))) == case["expected"]


def test_solution_returns_plain_str() -> None:
    result = solution.scanner(matrix_from_text("\n".join(CASES[0]["matrix"])))
    assert type(result) is str


def test_solution_agrees_with_library_on_random_codes() -> None:
    rng = random.Random(20261004)
    for _ in range(500):
        level = rng.choice("LMQH")
        length = rng.randint(0, capacity(level, "byte"))
        text = "".join(chr(rng.randint(32, 126)) for _ in range(length))
        matrix = encode(text, level, 0).matrix
        assert solution.scanner(matrix) == kata_scan(matrix) == text


def test_solution_needs_mask_zero() -> None:
    # Інша маска — інші біти: kata-розв'язок навмисно розрахований лише на маску 0.
    matrix = encode("Warrior", "H", 3).matrix
    try:
        got = solution.scanner(matrix)
    except (IndexError, ValueError):
        got = None
    assert got != "Warrior"
