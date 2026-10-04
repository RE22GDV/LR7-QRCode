"""Декодери QR версії 1: спрощений (як у kata) і повний (з корекцією помилок).

``kata_scan`` повторює алгоритм умови Codewars: маска 0, байтовий режим,
читаються лише перші 76 бітів, корекція помилок не виконується.

``decode`` працює як справжній сканер для версії 1: читає службову
інформацію (рівень і маску), знімає маску, збирає всі 26 кодових слів,
виправляє помилки й стирання кодом Ріда — Соломона і розбирає сегменти
числового, буквено-цифрового та байтового режимів.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import layout, reed_solomon
from .encoder import ALPHANUMERIC, COUNT_BITS

KATA_BITS = 76                  # 4 + 8 + 8·8: режим, довжина, до восьми байтів
MODE_NAMES = {0b0001: "numeric", 0b0010: "alphanumeric", 0b0100: "byte"}


class QRDecodeError(ValueError):
    """Код неможливо прочитати."""


def _check(matrix) -> list[list[int]]:
    if len(matrix) != layout.SIZE or any(len(row) != layout.SIZE for row in matrix):
        raise QRDecodeError("очікується матриця 21 × 21 (QR версії 1)")
    return [[1 if v else 0 for v in row] for row in matrix]


def _to_int(bits) -> int:
    value = 0
    for b in bits:
        value = (value << 1) | b
    return value


def unmasked_bits(matrix, mask: int = 0) -> list[int]:
    """Усі 208 бітів даних у порядку читання зі знятою маскою."""
    rule = layout.MASKS[mask]
    return [matrix[r][c] ^ (1 if rule(r, c) else 0) for r, c in layout.DATA_POSITIONS]


def read_codewords(matrix, mask: int) -> list[int]:
    bits = unmasked_bits(_check(matrix), mask)
    return [_to_int(bits[k:k + 8]) for k in range(0, layout.DATA_MODULES, 8)]


def kata_scan(matrix) -> str:
    """Алгоритм задачі Codewars: маска 0, байтовий режим, без корекції помилок.

    Умова обмежується першими 76 бітами (до восьми символів). Тут, як і в
    розв'язках з каталогу ``solution/``, читається стільки бітів, скільки
    вимагає поле довжини, тож так само читаються й довші повідомлення
    рівнів L, M і Q за маски 0. Індикатор режиму не перевіряється.
    """
    bits = unmasked_bits(_check(matrix), 0)
    length = _to_int(bits[4:12])
    if 12 + 8 * length > len(bits):
        raise QRDecodeError("поле довжини виходить за межі символу")
    return "".join(chr(_to_int(bits[12 + 8 * k:20 + 8 * k])) for k in range(length))


@dataclass
class DecodeResult:
    text: str
    level: str
    mask: int
    format_distance: int                    # хибних бітів у кращій копії формату
    codewords: list[int]                    # прочитані (до виправлення)
    corrected: list[int] = field(default_factory=list)   # індекси виправлених слів
    segments: list[tuple[str, str]] = field(default_factory=list)

    @property
    def errors_corrected(self) -> int:
        return len(self.corrected)


def parse_segments(data: list[int], byte_encoding: str = "auto") -> list[tuple[str, str]]:
    """Розібрати потік бітів інформаційних кодових слів на сегменти."""
    bits = [b for word in data for b in ((word >> (7 - i)) & 1 for i in range(8))]
    pos = 0
    segments = []

    def take(n):
        nonlocal pos
        if pos + n > len(bits):
            raise QRDecodeError("потік даних обірвано посеред сегмента")
        chunk = bits[pos:pos + n]
        pos += n
        return _to_int(chunk)

    while len(bits) - pos >= 4:
        indicator = take(4)
        if indicator == 0:
            break                                   # термінатор
        mode = MODE_NAMES.get(indicator)
        if mode is None:
            raise QRDecodeError(f"режим {indicator:04b} не підтримано")
        count = take(COUNT_BITS[mode])
        if mode == "byte":
            raw = bytes(take(8) for _ in range(count))
            if byte_encoding == "auto":
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
            else:
                text = raw.decode(byte_encoding)
        elif mode == "numeric":
            digits = []
            for k in range(0, count, 3):
                n = min(3, count - k)
                digits.append(str(take({3: 10, 2: 7, 1: 4}[n])).zfill(n))
            text = "".join(digits)
        else:
            chars = []
            for k in range(0, count, 2):
                if count - k >= 2:
                    v = take(11)
                    chars += [ALPHANUMERIC[v // 45], ALPHANUMERIC[v % 45]]
                else:
                    chars.append(ALPHANUMERIC[take(6)])
            text = "".join(chars)
        segments.append((mode, text))
    return segments


def decode(matrix, *, correct: bool = True, erasure_modules=(), reserve: bool = True,
           byte_encoding: str = "auto") -> DecodeResult:
    """Повне декодування QR версії 1.

    ``erasure_modules`` — позиції (рядок, стовпець) модулів, які відомо
    пошкоджені (наприклад, закриті логотипом); вони стають стираннями
    відповідних кодових слів. ``reserve=False`` дозволяє витратити на
    виправлення й резервні байти p (поза вимогами стандарту).
    """
    m = _check(matrix)
    level_name, mask, distance = layout.decode_format(m)
    if distance > 3:
        raise QRDecodeError("службову інформацію про формат не розпізнано")
    level = layout.LEVELS[level_name]
    words = read_codewords(m, mask)
    corrected: list[int] = []
    if correct:
        erasures = sorted({layout.CODEWORD_OF_MODULE[p] for p in erasure_modules
                           if p in layout.CODEWORD_OF_MODULE})
        try:
            fixed, corrected = reed_solomon.decode(
                words, level.ecc_codewords, erasures,
                reserve=level.reserve if reserve else 0)
        except reed_solomon.RSDecodeError as exc:
            raise QRDecodeError(f"корекція не вдалася: {exc}") from exc
    else:
        fixed = words
    segments = parse_segments(fixed[:level.data_codewords], byte_encoding)
    return DecodeResult("".join(t for _, t in segments), level_name, mask, distance,
                        words, corrected, segments)


def try_decode(matrix, **kwargs) -> str | None:
    """Текст або None, якщо код не прочитано."""
    try:
        return decode(matrix, **kwargs).text
    except QRDecodeError:
        return None
