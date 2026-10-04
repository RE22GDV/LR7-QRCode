"""Кодер QR-коду версії 1: текст → матриця 21 × 21.

Підтримано числовий, буквено-цифровий і байтовий режими, усі чотири
рівні корекції та вісім масок. Без явної маски обирається маска з
найменшою сумою штрафів (розділ 7.8.3 ISO/IEC 18004).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import layout, reed_solomon

MODE_INDICATOR = {"numeric": 0b0001, "alphanumeric": 0b0010, "byte": 0b0100}
COUNT_BITS = {"numeric": 10, "alphanumeric": 9, "byte": 8}      # версії 1–9
ALPHANUMERIC = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
PAD_BYTES = (0xEC, 0x11)


class CapacityError(ValueError):
    """Повідомлення не вміщується в QR версії 1 обраного рівня."""


@dataclass
class QRCode:
    matrix: list[list[int]]
    level: str
    mask: int
    mode: str
    data: list[int]         # інформаційні кодові слова
    ecc: list[int]          # перевірні кодові слова

    @property
    def codewords(self) -> list[int]:
        return self.data + self.ecc


def _bits(value: int, width: int) -> list[int]:
    return [value >> (width - 1 - i) & 1 for i in range(width)]


def pick_mode(text: str) -> str:
    if text.isdigit() and text.isascii():
        return "numeric"
    if all(ch in ALPHANUMERIC for ch in text):
        return "alphanumeric"
    return "byte"


def segment_bits(payload: str | bytes, mode: str) -> list[int]:
    """Біти сегмента: індикатор режиму, лічильник символів і дані."""
    if mode == "byte":
        raw = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        bits = _bits(MODE_INDICATOR[mode], 4) + _bits(len(raw), COUNT_BITS[mode])
        for b in raw:
            bits += _bits(b, 8)
        return bits
    text = payload.decode("ascii") if isinstance(payload, bytes) else payload
    bits = _bits(MODE_INDICATOR[mode], 4) + _bits(len(text), COUNT_BITS[mode])
    if mode == "numeric":
        if not (text.isdigit() and text.isascii()):
            raise ValueError("числовий режим допускає лише цифри 0–9")
        for k in range(0, len(text), 3):
            group = text[k:k + 3]
            bits += _bits(int(group), {3: 10, 2: 7, 1: 4}[len(group)])
    elif mode == "alphanumeric":
        if any(ch not in ALPHANUMERIC for ch in text):
            raise ValueError("символ поза набором буквено-цифрового режиму")
        for k in range(0, len(text), 2):
            pair = text[k:k + 2]
            if len(pair) == 2:
                bits += _bits(45 * ALPHANUMERIC.index(pair[0]) + ALPHANUMERIC.index(pair[1]), 11)
            else:
                bits += _bits(ALPHANUMERIC.index(pair), 6)
    else:
        raise ValueError(f"невідомий режим {mode!r}")
    return bits


def data_codewords(payload: str | bytes, level: str = "H", mode: str = "byte") -> list[int]:
    """Інформаційні кодові слова: сегмент, термінатор, вирівнювання, заповнювачі."""
    capacity = 8 * layout.LEVELS[level].data_codewords
    bits = segment_bits(payload, mode)
    if len(bits) > capacity:
        raise CapacityError(
            f"потрібно {len(bits)} бітів, а версія 1-{level} вміщує {capacity}")
    bits += [0] * min(4, capacity - len(bits))          # термінатор 0000
    bits += [0] * (-len(bits) % 8)                       # до межі байта
    words = [int("".join(map(str, bits[k:k + 8])), 2) for k in range(0, len(bits), 8)]
    k = 0
    while len(words) < capacity // 8:
        words.append(PAD_BYTES[k % 2])
        k += 1
    return words


def place_codewords(codewords: list[int], level: str, mask: int) -> list[list[int]]:
    """Розмістити 26 кодових слів, накласти маску й записати формат."""
    if len(codewords) != layout.CODEWORDS:
        raise ValueError("версія 1 містить рівно 26 кодових слів")
    matrix = layout.function_template()
    for i, (row, col) in enumerate(layout.DATA_POSITIONS):
        matrix[row][col] = codewords[i // 8] >> (7 - i % 8) & 1
    matrix = layout.apply_mask(matrix, mask)
    layout.place_format(matrix, level, mask)
    return matrix


def choose_mask(codewords: list[int], level: str) -> int:
    scores = [sum(layout.penalty(place_codewords(codewords, level, m))) for m in range(8)]
    return min(range(8), key=lambda m: (scores[m], m))


def encode(payload: str | bytes, level: str = "H", mask: int | None = None,
           mode: str = "byte") -> QRCode:
    """Закодувати повідомлення в QR версії 1.

    ``mode="auto"`` обирає найкомпактніший режим із трьох підтримуваних.
    ``mask=None`` обирає маску з найменшим штрафом.
    """
    if level not in layout.LEVELS:
        raise ValueError(f"невідомий рівень корекції {level!r}")
    if mode == "auto":
        mode = "byte" if isinstance(payload, bytes) else pick_mode(payload)
    data = data_codewords(payload, level, mode)
    ecc = reed_solomon.encode(data, layout.LEVELS[level].ecc_codewords)
    if mask is None:
        mask = choose_mask(data + ecc, level)
    if not 0 <= mask <= 7:
        raise ValueError("номер маски — від 0 до 7")
    return QRCode(place_codewords(data + ecc, level, mask), level, mask, mode, data, ecc)


def capacity(level: str, mode: str) -> int:
    """Найбільша кількість символів версії 1 для рівня й режиму."""
    bits = 8 * layout.LEVELS[level].data_codewords - 4 - COUNT_BITS[mode]
    if mode == "byte":
        return bits // 8
    if mode == "alphanumeric":
        return 2 * (bits // 11) + (1 if bits % 11 >= 6 else 0)
    if mode == "numeric":
        rest = bits % 10
        return 3 * (bits // 10) + (2 if rest >= 7 else 1 if rest >= 4 else 0)
    raise ValueError(f"невідомий режим {mode!r}")
