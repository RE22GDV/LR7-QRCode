"""Кодер, повний декодер і kata-декодер на контрольних матрицях Codewars."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from qrv1 import CapacityError, capacity, decode, encode, kata_scan, layout, try_decode
from qrv1.decoder import parse_segments, read_codewords
from qrv1.encoder import data_codewords
from qrv1.image import matrix_from_text

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests" / "codewars_cases.json").read_text(encoding="utf-8"))["cases"]
IDS = [f"{c['source']}-{c['expected']}" for c in CASES]


def _matrix(case) -> list[list[int]]:
    return matrix_from_text("\n".join(case["matrix"]))


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_kata_scan_reads_every_sample(case) -> None:
    assert kata_scan(_matrix(case)) == case["expected"]


@pytest.mark.parametrize("case", [c for c in CASES if c["standard_valid"]],
                         ids=[i for c, i in zip(CASES, IDS) if c["standard_valid"]])
def test_encoder_reproduces_valid_samples_bit_for_bit(case) -> None:
    assert encode(case["expected"], "H", 0).matrix == _matrix(case)
    result = decode(_matrix(case))
    assert (result.text, result.level, result.mask, result.corrected) == (case["expected"], "H", 0, [])


def test_csharp_samples_differ_only_in_check_bytes() -> None:
    by_text = {}
    for case in CASES:
        by_text.setdefault(case["expected"], {})[case["source"]] = _matrix(case)
    for text in ("Hi", "Warrior", "T3st", "T!st"):
        cs, py = by_text[text]["csharp"], by_text[text]["python"]
        assert layout.decode_format(cs) == layout.decode_format(py) == ("H", 0, 0)
        a, b = read_codewords(cs, 0), read_codewords(py, 0)
        assert a[:9] == b[:9]                                   # дані однакові
        assert [i for i in range(26) if a[i] != b[i]] == list(range(10, 25))
        assert try_decode(cs) is None                           # 15 хибних слів > 8
        assert kata_scan(cs) == text                            # але kata їх не перевіряє


def test_capacity_table_matches_standard() -> None:
    expected = {"L": (41, 25, 17), "M": (34, 20, 14), "Q": (27, 16, 11), "H": (17, 10, 7)}
    for level, numbers in expected.items():
        assert tuple(capacity(level, m) for m in ("numeric", "alphanumeric", "byte")) == numbers


def test_eight_characters_do_not_fit_level_h() -> None:
    encode("Warrior", "H", 0)
    with pytest.raises(CapacityError):
        encode("Warriors", "H", 0)
    encode("Warriors", "Q", 0)


def test_padding_follows_standard() -> None:
    assert data_codewords("Hi", "H") == [0x40, 0x24, 0x86, 0x90, 0xEC, 0x11, 0xEC, 0x11, 0xEC]


@pytest.mark.parametrize("text,mode", [("01234567", "numeric"), ("1", "numeric"),
                                       ("HELLO WORLD"[:10], "alphanumeric"), ("A", "alphanumeric"),
                                       ("Привіт", "byte"), ("a~b", "byte")])
def test_round_trip_in_every_mode(text, mode) -> None:
    for level in "LMQH":
        try:
            qr = encode(text, level, mode=mode)
        except CapacityError:
            continue
        result = decode(qr.matrix)
        assert result.text == text and result.segments[0][0] == mode and result.mask == qr.mask


def test_auto_mask_has_minimal_penalty() -> None:
    from qrv1.encoder import place_codewords
    qr = encode("Warrior", "H")
    scores = [sum(layout.penalty(place_codewords(qr.codewords, "H", m))) for m in range(8)]
    assert scores[qr.mask] == min(scores)


def test_full_decoder_corrects_eight_damaged_codewords() -> None:
    rng = random.Random(5)
    qr = encode("Warrior", "H", 0)
    for _ in range(100):
        words = rng.sample(range(26), 8)
        damaged = [row[:] for row in qr.matrix]
        for i, (r, c) in enumerate(layout.DATA_POSITIONS):
            if i // 8 in words and rng.random() < 0.6:
                damaged[r][c] ^= 1
        result = decode(damaged)
        assert result.text == "Warrior" and set(result.corrected) <= set(words)


def test_erasures_recover_sixteen_codewords() -> None:
    qr = encode("Warrior", "H", 0)
    lost = [p for p in layout.DATA_POSITIONS if layout.CODEWORD_OF_MODULE[p] < 16]
    damaged = [row[:] for row in qr.matrix]
    for r, c in lost:
        damaged[r][c] = 0
    assert try_decode(damaged) is None
    assert decode(damaged, erasure_modules=lost).text == "Warrior"


def test_kata_scan_ignores_everything_except_length_and_text() -> None:
    case = next(c for c in CASES if c["expected"] == "Warrior" and c["source"] == "python")
    base = _matrix(case)
    used = set(layout.DATA_POSITIONS[4:12 + 8 * 7])
    for r in range(21):
        for c in range(21):
            m = [row[:] for row in base]
            m[r][c] ^= 1
            try:
                got = kata_scan(m)
            except ValueError:
                got = None
            assert (got == "Warrior") == ((r, c) not in used)


def test_parse_segments_rejects_unknown_mode() -> None:
    from qrv1.decoder import QRDecodeError
    with pytest.raises(QRDecodeError):
        parse_segments([0b10000000] + [0] * 8)          # режим кандзі не підтримано
