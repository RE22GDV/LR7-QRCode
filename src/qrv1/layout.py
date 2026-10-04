"""Геометрія QR-коду версії 1 (21 × 21) за ISO/IEC 18004.

Матриця — список рядків, елемент ``matrix[row][col]``: 1 — темний модуль,
0 — світлий. Рядки й стовпці нумеруються з нуля від лівого верхнього кута.

Службові зони версії 1: три шукові візерунки з роздільниками (по 8 × 8
модулів), дві смуги синхронізації (рядок і стовпець 6), дві копії
службової інформації про формат (15 бітів кожна) та «темний модуль»
(рядок 13, стовпець 8). Вирівнювальних візерунків і блоку версії немає.
Решта 208 модулів несуть 26 кодових слів по 8 бітів.
"""

from __future__ import annotations

from dataclasses import dataclass

SIZE = 21
DATA_MODULES = 208
CODEWORDS = 26


@dataclass(frozen=True)
class Level:
    name: str
    format_bits: int        # двобітовий код рівня в службовій інформації
    data_codewords: int
    ecc_codewords: int
    correctable: int        # t — гарантована кількість виправних кодових слів
    reserve: int            # p — перевірні байти для захисту від хибного декодування


# Таблиці 7 і 9 ISO/IEC 18004:2015 для версії 1.
LEVELS = {
    "L": Level("L", 0b01, 19, 7, 2, 3),
    "M": Level("M", 0b00, 16, 10, 4, 2),
    "Q": Level("Q", 0b11, 13, 13, 6, 1),
    "H": Level("H", 0b10, 9, 17, 8, 1),
}
LEVEL_BY_BITS = {lv.format_bits: lv for lv in LEVELS.values()}


# --- службові зони ----------------------------------------------------------

def module_kind(row: int, col: int) -> str:
    """Призначення модуля: finder, separator, timing, format, dark або data."""
    for r0, c0 in ((0, 0), (0, SIZE - 7), (SIZE - 7, 0)):
        if r0 <= row < r0 + 7 and c0 <= col < c0 + 7:
            return "finder"
    in_top_left = row <= 7 and col <= 7
    in_top_right = row <= 7 and col >= SIZE - 8
    in_bottom_left = row >= SIZE - 8 and col <= 7
    if in_top_left or in_top_right or in_bottom_left:
        return "separator"
    if (row, col) == (SIZE - 8, 8):
        return "dark"
    if row == 6 or col == 6:            # зокрема (6, 8) і (8, 6) біля формату
        return "timing"
    if (row == 8 and (col <= 8 or col >= SIZE - 8)) or (col == 8 and (row <= 8 or row >= SIZE - 8)):
        return "format"
    return "data"


def is_function(row: int, col: int) -> bool:
    return module_kind(row, col) != "data"


def data_positions() -> list[tuple[int, int]]:
    """208 позицій модулів даних у порядку читання (зигзаг стовпцями по два).

    Читання починається з правого нижнього кута: спершу правий модуль пари,
    потім лівий, рядком вище — знову правий і лівий; дійшовши до краю,
    напрям змінюється, а пара стовпців зсувається на два ліворуч.
    Стовпець 6 (вертикальна смуга синхронізації) пропускається.
    """
    order = []
    upward = True
    for right in range(SIZE - 1, 0, -2):
        if right <= 6:
            right -= 1
        rows = range(SIZE - 1, -1, -1) if upward else range(SIZE)
        for row in rows:
            for col in (right, right - 1):
                if not is_function(row, col):
                    order.append((row, col))
        upward = not upward
    return order


DATA_POSITIONS = data_positions()
CODEWORD_OF_MODULE = {pos: i // 8 for i, pos in enumerate(DATA_POSITIONS)}
assert len(DATA_POSITIONS) == DATA_MODULES


# --- маски ------------------------------------------------------------------

MASKS = (
    lambda i, j: (i + j) % 2 == 0,
    lambda i, j: i % 2 == 0,
    lambda i, j: j % 3 == 0,
    lambda i, j: (i + j) % 3 == 0,
    lambda i, j: (i // 2 + j // 3) % 2 == 0,
    lambda i, j: (i * j) % 2 + (i * j) % 3 == 0,
    lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0,
    lambda i, j: ((i + j) % 2 + (i * j) % 3) % 2 == 0,
)
"""Умови восьми масок; i — рядок, j — стовпець. Якщо умова істинна,
модуль даних інвертується."""


def apply_mask(matrix: list[list[int]], mask: int) -> list[list[int]]:
    """Нова матриця з інвертованими за маскою модулями даних."""
    rule = MASKS[mask]
    out = [row[:] for row in matrix]
    for row, col in DATA_POSITIONS:
        if rule(row, col):
            out[row][col] ^= 1
    return out


# --- службова інформація про формат: код БЧХ (15, 5) ---------------------------

FORMAT_GENERATOR = 0b10100110111      # x^10 + x^8 + x^5 + x^4 + x^2 + x + 1
FORMAT_XOR = 0b101010000010010         # 0x5412: не допускає нульового слова


def format_word(level: str, mask: int) -> int:
    """15-бітове слово формату: 5 інформаційних бітів, 10 перевірних, XOR-маска."""
    data = (LEVELS[level].format_bits << 3) | mask
    remainder = data << 10
    for shift in range(14, 9, -1):
        if remainder >> shift & 1:
            remainder ^= FORMAT_GENERATOR << (shift - 10)
    return ((data << 10) | remainder) ^ FORMAT_XOR


FORMAT_WORDS = {format_word(lv, m): (lv, m) for lv in LEVELS for m in range(8)}

# Позиції бітів 0 … 14 (молодший перший) для двох копій слова формату.
FORMAT_COPY_1 = ([(i, 8) for i in range(6)] + [(7, 8), (8, 8), (8, 7)]
                 + [(8, 14 - i) for i in range(9, 15)])
FORMAT_COPY_2 = ([(8, SIZE - 1 - i) for i in range(8)]
                 + [(SIZE - 15 + i, 8) for i in range(8, 15)])


def read_format_bits(matrix: list[list[int]]) -> tuple[int, int]:
    def read(copy):
        return sum(matrix[r][c] << i for i, (r, c) in enumerate(copy))
    return read(FORMAT_COPY_1), read(FORMAT_COPY_2)


def decode_format(matrix: list[list[int]]) -> tuple[str, int, int]:
    """(рівень, маска, відстань Геммінга до найближчого коректного слова).

    Мінімальна відстань коду формату — 7, тож до трьох хибних бітів у
    кращій із двох копій виправляються однозначно.
    """
    best = None
    for word in read_format_bits(matrix):
        for valid, (level, mask) in FORMAT_WORDS.items():
            dist = bin(word ^ valid).count("1")
            if best is None or dist < best[2]:
                best = (level, mask, dist)
    return best


# --- побудова службових зон -----------------------------------------------

def function_template() -> list[list[int]]:
    """Матриця лише зі шуковими візерунками, синхронізацією й темним модулем."""
    m = [[0] * SIZE for _ in range(SIZE)]
    for r0, c0 in ((0, 0), (0, SIZE - 7), (SIZE - 7, 0)):
        for i in range(7):
            for j in range(7):
                ring = max(abs(i - 3), abs(j - 3))
                m[r0 + i][c0 + j] = 0 if ring == 2 else 1
    for k in range(8, SIZE - 8):
        m[6][k] = m[k][6] = 1 if k % 2 == 0 else 0
    m[SIZE - 8][8] = 1
    return m


def place_format(matrix: list[list[int]], level: str, mask: int) -> None:
    word = format_word(level, mask)
    for copy in (FORMAT_COPY_1, FORMAT_COPY_2):
        for i, (r, c) in enumerate(copy):
            matrix[r][c] = word >> i & 1


# --- штрафні бали для вибору маски (розділ 7.8.3 стандарту) ----------------------

def penalty(matrix: list[list[int]]) -> tuple[int, int, int, int]:
    """Штрафи N1 (серії), N2 (блоки 2 × 2), N3 (схожість на шуковий
    візерунок), N4 (баланс темних модулів) для всієї матриці 21 × 21."""
    lines = [list(r) for r in matrix] + [list(c) for c in zip(*matrix)]

    n1 = 0
    for line in lines:
        run = 1
        for a, b in zip(line, line[1:]):
            if a == b:
                run += 1
            else:
                if run >= 5:
                    n1 += 3 + run - 5
                run = 1
        if run >= 5:
            n1 += 3 + run - 5

    n2 = 0
    for r in range(SIZE - 1):
        for c in range(SIZE - 1):
            if matrix[r][c] == matrix[r][c + 1] == matrix[r + 1][c] == matrix[r + 1][c + 1]:
                n2 += 3

    patterns = ("10111010000", "00001011101")
    n3 = 0
    for line in lines:
        s = "".join(map(str, line))
        for p in patterns:
            n3 += 40 * sum(1 for k in range(len(s) - len(p) + 1) if s.startswith(p, k))

    dark = sum(map(sum, matrix))
    percent = 100 * dark / (SIZE * SIZE)
    n4 = 10 * int(abs(percent - 50) // 5)
    return n1, n2, n3, n4
