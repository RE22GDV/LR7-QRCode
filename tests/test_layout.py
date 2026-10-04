"""Геометрія версії 1: службові зони, порядок читання, маски, формат."""

from __future__ import annotations

import itertools
from collections import Counter

from qrv1 import layout


def test_module_kinds_cover_the_whole_symbol() -> None:
    kinds = Counter(layout.module_kind(r, c) for r in range(21) for c in range(21))
    assert kinds == {"finder": 147, "separator": 45, "timing": 10,
                     "format": 30, "dark": 1, "data": 208}


def test_reading_order_visits_every_data_module_once() -> None:
    order = layout.DATA_POSITIONS
    assert len(order) == len(set(order)) == 208
    assert all(not layout.is_function(r, c) for r, c in order)
    assert order[:4] == [(20, 20), (20, 19), (19, 20), (19, 19)]   # правий нижній кут, вгору
    assert all(c != 6 for _, c in order)


def test_reading_order_changes_direction_by_column_pair() -> None:
    order = layout.DATA_POSITIONS
    # Перша пара (20, 19) читається вгору до рядка 9, друга (18, 17) — вниз.
    assert order[23] == (9, 19) and order[24] == (9, 18)
    assert order[47] == (20, 17)


def test_each_codeword_occupies_eight_modules() -> None:
    sizes = Counter(layout.CODEWORD_OF_MODULE.values())
    assert sorted(sizes) == list(range(26)) and set(sizes.values()) == {8}


def test_format_words_form_a_distance_seven_code() -> None:
    words = list(layout.FORMAT_WORDS)
    assert len(words) == 32
    assert min(bin(a ^ b).count("1") for a, b in itertools.combinations(words, 2)) == 7
    assert format(layout.format_word("H", 0), "015b") == "001011010001001"
    assert format(layout.format_word("M", 5), "015b") == "100000011001110"


def test_format_survives_three_bit_errors_in_both_copies() -> None:
    m = layout.function_template()
    layout.place_format(m, "Q", 6)
    for r, c in (layout.FORMAT_COPY_1[0], layout.FORMAT_COPY_1[7], layout.FORMAT_COPY_1[14],
                 layout.FORMAT_COPY_2[2], layout.FORMAT_COPY_2[9], layout.FORMAT_COPY_2[13]):
        m[r][c] ^= 1
    assert layout.decode_format(m) == ("Q", 6, 3)


def test_mask_is_an_involution_and_spares_function_modules() -> None:
    base = layout.function_template()
    for mask in range(8):
        masked = layout.apply_mask(base, mask)
        assert layout.apply_mask(masked, mask) == base
        for r in range(21):
            for c in range(21):
                if layout.is_function(r, c):
                    assert masked[r][c] == base[r][c]


def test_mask_zero_matches_kata_definition() -> None:
    rule = layout.MASKS[0]
    assert all(rule(r, c) == ((r + c) % 2 == 0) for r in range(21) for c in range(21))


def test_level_table_of_version_one() -> None:
    for lv in layout.LEVELS.values():
        assert lv.data_codewords + lv.ecc_codewords == 26
        assert 2 * lv.correctable + lv.reserve == lv.ecc_codewords
    assert layout.LEVELS["H"].correctable == 8


def test_penalty_rules_on_simple_patterns() -> None:
    white = [[0] * 21 for _ in range(21)]
    n1, n2, n3, n4 = layout.penalty(white)
    assert n1 == 42 * (3 + 16) and n2 == 3 * 400 and n3 == 0 and n4 == 100
    chess = [[(r + c) % 2 for c in range(21)] for r in range(21)]
    assert layout.penalty(chess) == (0, 0, 0, 0)
