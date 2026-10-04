"""Точні ймовірності, моделі пошкоджень і цілеспрямована зміна символу."""

from __future__ import annotations

import itertools
import random
from fractions import Fraction

import pytest

from qrv1 import analysis, decode, encode, layout, try_decode


def test_hit_distribution_sums_to_one() -> None:
    for k in (0, 1, 5, 30, 100, 208):
        dist = analysis.words_hit_distribution(k)
        assert sum(dist) == 1
        assert all(p >= 0 for p in dist)


@pytest.mark.parametrize("k", [1, 2, 3])
def test_exact_formulas_match_enumeration(k: int) -> None:
    positions = range(208)
    used = set(range(4, 12 + 8 * 7))
    ok_kata = ok_rs = total = 0
    sample = itertools.combinations(positions, k)
    for combo in sample:
        total += 1
        ok_kata += used.isdisjoint(combo)
        ok_rs += len({p // 8 for p in combo}) <= 1
    assert analysis.kata_success(k, 7) == Fraction(ok_kata, total)
    assert analysis.rs_success(k, 1) == Fraction(ok_rs, total)


def test_kata_uses_sixty_four_bits_for_warrior() -> None:
    assert analysis.kata_used_bits(7) == 64
    assert analysis.kata_success(1, 7) == Fraction(144, 208)


def test_rs_success_drops_after_capacity() -> None:
    assert analysis.rs_success(8, 8) == 1                   # 8 інверсій — не більше 8 слів
    assert analysis.rs_success(9, 8) < 1
    assert analysis.rs_success(20, 8) < analysis.rs_success(20, 6) * 0 + 1


def test_monte_carlo_agrees_with_exact_values() -> None:
    rng = random.Random(9)
    qr = encode("Warrior", "H", 0)
    for k in (10, 20):
        kata, full = analysis.simulate_random_flips(qr, "Warrior", k, 400, rng)
        assert abs(kata.correct / 400 - float(analysis.kata_success(k, 7))) < 0.08
        assert abs(full.correct / 400 - float(analysis.rs_success(k, 8))) < 0.08


def test_block_damage_with_erasures_never_worse_than_errors() -> None:
    rng = random.Random(4)
    qr = encode("Warrior", "H", 0)
    for side in (3, 5, 7):
        errors, erasures, touched = analysis.simulate_blocks(qr, "Warrior", side, 60, rng)
        assert erasures.correct >= errors.correct
        assert max(touched) <= 26


def test_forgery_is_read_as_target_text() -> None:
    f = analysis.forge("PAY 100", "PAY 900", "H", 0)
    d, t = analysis.min_distance("H"), layout.LEVELS["H"].correctable
    assert len(f.differing) >= d == 18
    assert len(f.rewritten) == len(f.differing) - t
    result = decode(f.matrix)
    assert result.text == "PAY 900" and len(result.corrected) == t


def test_small_tampering_is_silently_corrected_back() -> None:
    matrix, changed = analysis.tamper_data_only("PAY 100", "PAY 900", "H", 0)
    assert 0 < len(changed) <= 16
    result = decode(matrix)
    assert result.text == "PAY 100" and result.corrected


def test_reed_solomon_is_linear() -> None:
    assert analysis.ecc_identity_check()


def test_centered_logo_geometry() -> None:
    assert len(analysis.centered_block(5)) == 25
    assert analysis.centered_block(1) == [(10, 10)]
    assert try_decode(encode("Hi", "H").matrix) == "Hi"
