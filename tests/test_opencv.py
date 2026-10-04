"""Незалежна перевірка через OpenCV (тести пропускаються без opencv-python)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")

from qrv1 import decode, encode, layout  # noqa: E402
from qrv1.encoder import place_codewords  # noqa: E402
from qrv1.image import matrix_from_text, opencv_decode, opencv_encode  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests" / "codewars_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[f"{c['source']}-{c['expected']}" for c in CASES])
def test_opencv_reads_only_standard_valid_samples(case) -> None:
    got = opencv_decode(matrix_from_text("\n".join(case["matrix"])))
    assert (got == case["expected"]) == case["standard_valid"]


@pytest.mark.parametrize("level", list("LMQH"))
def test_opencv_reads_our_codes(level: str) -> None:
    for mask in range(8):
        assert opencv_decode(encode("Warrior", level, mask).matrix) == "Warrior"


def _opencv_n4(matrix) -> int:
    # Правило 4 у qrcode_encoder.cpp OpenCV 4.x: межі 45 і 55 %, ціле ділення.
    percent = sum(map(sum, matrix)) * 100 // (21 * 21)
    return (min(abs(percent - 45), abs(percent - 55)) // 5) * 10


@pytest.mark.parametrize("text", ["Hi", "Warrior", "T3st", "T!st", "Hello"])
@pytest.mark.parametrize("level", list("LMQH"))
def test_our_decoder_reads_opencv_codes(text: str, level: str) -> None:
    theirs = opencv_encode(text, level)
    result = decode(theirs)
    assert result.text == text and result.level == level
    ours = encode(text, level, result.mask)
    assert ours.matrix == theirs                         # за тієї самої маски — біт у біт
    opencv_rule, standard_rule = [], []
    for mask in range(8):
        m = place_codewords(ours.codewords, level, mask)
        n1, n2, n3, n4 = layout.penalty(m)
        opencv_rule.append(n1 + n2 + n3 + _opencv_n4(m))
        standard_rule.append(n1 + n2 + n3 + n4)
    best = {min(range(8), key=lambda m: (s[m], m)) for s in (opencv_rule, standard_rule)}
    # OpenCV 4.13 обирає маску за своїм правилом N4; якщо його виправлять,
    # вибір має збігтися зі стандартним правилом.
    assert result.mask in best
