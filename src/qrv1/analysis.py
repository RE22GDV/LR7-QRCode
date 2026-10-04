"""Аналітичні оцінки та моделі пошкоджень для експериментів.

Точні ймовірності рахуються в раціональних числах (``fractions``), без
симуляції: модель — k різних модулів даних, обраних рівноймовірно серед
208, інвертуються.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction
from math import comb

from . import layout, reed_solomon
from .decoder import QRDecodeError, decode, kata_scan
from .encoder import COUNT_BITS, QRCode, encode, place_codewords

BITS_PER_WORD = 8


# --- точні ймовірності -------------------------------------------------------

def kata_used_bits(length: int) -> int:
    """Скільки бітів даних реально впливає на відповідь kata-декодера.

    Індикатор режиму (4 біти) він не перевіряє, тож важать лише 8 бітів
    довжини та 8 бітів на кожен символ.
    """
    return COUNT_BITS["byte"] + 8 * length


def kata_success(k: int, length: int) -> Fraction:
    """P(kata-декодер не помітить k інверсій): усі вони поза використаними бітами."""
    used = kata_used_bits(length)
    return Fraction(comb(layout.DATA_MODULES - used, k), comb(layout.DATA_MODULES, k))


def words_hit_count(j: int, k: int) -> int:
    """Кількість способів обрати k модулів так, щоб зачепити рівно j заданих слів."""
    return sum((-1) ** i * comb(j, i) * comb(BITS_PER_WORD * (j - i), k) for i in range(j + 1))


def words_hit_distribution(k: int) -> list[Fraction]:
    """P(рівно j із 26 кодових слів зачеплено), j = 0 … 26."""
    total = comb(layout.DATA_MODULES, k)
    return [Fraction(comb(layout.CODEWORDS, j) * words_hit_count(j, k), total)
            for j in range(layout.CODEWORDS + 1)]


def rs_success(k: int, t: int) -> Fraction:
    """P(зачеплено не більше t кодових слів) — тоді декодер гарантовано виправляє."""
    return sum(words_hit_distribution(k)[:t + 1], Fraction(0))


# --- пошкодження матриці -----------------------------------------------------

def flip_modules(matrix, positions) -> list[list[int]]:
    out = [row[:] for row in matrix]
    for r, c in positions:
        out[r][c] ^= 1
    return out


def paint_modules(matrix, positions, value: int = 0) -> list[list[int]]:
    out = [row[:] for row in matrix]
    for r, c in positions:
        out[r][c] = value
    return out


def block(top: int, left: int, side: int) -> list[tuple[int, int]]:
    return [(r, c) for r in range(top, top + side) for c in range(left, left + side)
            if 0 <= r < layout.SIZE and 0 <= c < layout.SIZE]


def centered_block(side: int) -> list[tuple[int, int]]:
    start = (layout.SIZE - side) // 2
    return block(start, start, side)


def data_modules_in(positions) -> list[tuple[int, int]]:
    return [p for p in positions if p in layout.CODEWORD_OF_MODULE]


def codewords_touched(positions) -> set[int]:
    return {layout.CODEWORD_OF_MODULE[p] for p in positions if p in layout.CODEWORD_OF_MODULE}


@dataclass
class Outcome:
    correct: int = 0        # повернуто правильний текст
    failed: int = 0         # декодер повідомив про невдачу
    wrong: int = 0          # повернуто хибний текст без повідомлення про помилку

    def add(self, got: str | None, expected: str) -> None:
        if got is None:
            self.failed += 1
        elif got == expected:
            self.correct += 1
        else:
            self.wrong += 1

    @property
    def total(self) -> int:
        return self.correct + self.failed + self.wrong


def full_text(matrix, **kwargs) -> str | None:
    try:
        return decode(matrix, **kwargs).text
    except (QRDecodeError, IndexError, ValueError):
        return None


def kata_text(matrix) -> str | None:
    try:
        return kata_scan(matrix)
    except (IndexError, ValueError):
        return None


def simulate_random_flips(qr: QRCode, text: str, k: int, trials: int, rng: random.Random,
                          reserve: bool = True) -> tuple[Outcome, Outcome]:
    """(kata-декодер, повний декодер) після інверсії k випадкових модулів даних."""
    kata, full = Outcome(), Outcome()
    for _ in range(trials):
        damaged = flip_modules(qr.matrix, rng.sample(layout.DATA_POSITIONS, k))
        kata.add(kata_text(damaged), text)
        full.add(full_text(damaged, reserve=reserve), text)
    return kata, full


def simulate_blocks(qr: QRCode, text: str, side: int, trials: int, rng: random.Random,
                    paint: int = 0) -> tuple[Outcome, Outcome, list[int]]:
    """Квадратна пляма side × side у випадковому місці символу.

    Змінюються лише модулі даних під плямою (вважається, що сканер усе ще
    знайшов символ). Повертає результати декодування без знання позицій
    (помилки) та зі знанням (стирання) і кількість зачеплених слів.
    """
    as_errors, as_erasures, touched = Outcome(), Outcome(), []
    for _ in range(trials):
        top = rng.randrange(layout.SIZE - side + 1)
        left = rng.randrange(layout.SIZE - side + 1)
        covered = data_modules_in(block(top, left, side))
        damaged = paint_modules(qr.matrix, covered, paint)
        touched.append(len(codewords_touched(covered)))
        as_errors.add(full_text(damaged), text)
        as_erasures.add(full_text(damaged, erasure_modules=covered), text)
    return as_errors, as_erasures, touched


# --- цілеспрямована зміна повідомлення -------------------------------------------

@dataclass
class Forgery:
    original: QRCode
    target: QRCode
    differing: list[int]            # кодові слова, у яких коди відрізняються
    rewritten: list[int]            # слова, переписані на цільові
    matrix: list[list[int]]         # підроблений символ
    modules_changed: list[tuple[int, int]]


def forge(original_text: str, target_text: str, level: str = "H", mask: int = 0) -> Forgery:
    """Мінімально змінити символ так, щоб декодер прочитав інше повідомлення.

    Цільове кодове слово відрізняється від вихідного в d ≥ n − k + 1 позиціях.
    Досить переписати d − t із них: тоді прийняте слово на відстані t від
    цільового (декодер «виправить» його до цілі) і на відстані d − t > t
    від справжнього. Лишаються неторканими t слів із найбільшою кількістю
    відмінних бітів, щоб змінити якомога менше модулів.
    """
    original = encode(original_text, level, mask)
    target = encode(target_text, level, mask)
    a, b = original.codewords, target.codewords
    differing = [i for i in range(layout.CODEWORDS) if a[i] != b[i]]
    t = layout.LEVELS[level].correctable
    by_cost = sorted(differing, key=lambda i: bin(a[i] ^ b[i]).count("1"))
    rewritten = sorted(by_cost[:max(0, len(differing) - t)])
    mixed = [b[i] if i in rewritten else a[i] for i in range(layout.CODEWORDS)]
    matrix = place_codewords(mixed, level, mask)
    changed = [(r, c) for r in range(layout.SIZE) for c in range(layout.SIZE)
               if matrix[r][c] != original.matrix[r][c]]
    return Forgery(original, target, differing, rewritten, matrix, changed)


def tamper_data_only(original_text: str, target_text: str, level: str = "H", mask: int = 0):
    """Переписати лише інформаційні слова (без перерахунку корекції)."""
    original = encode(original_text, level, mask)
    target = encode(target_text, level, mask)
    k = layout.LEVELS[level].data_codewords
    mixed = target.data[:k] + original.ecc
    matrix = place_codewords(mixed, level, mask)
    changed = [(r, c) for r in range(layout.SIZE) for c in range(layout.SIZE)
               if matrix[r][c] != original.matrix[r][c]]
    return matrix, changed


def min_distance(level: str) -> int:
    """Мінімальна кодова відстань (n − k + 1) коду Ріда — Соломона рівня."""
    lv = layout.LEVELS[level]
    return lv.ecc_codewords + 1


def ecc_identity_check(level: str = "H", trials: int = 200, seed: int = 7) -> bool:
    """Код Ріда — Соломона лінійний: ECC(a ⊕ b) = ECC(a) ⊕ ECC(b)."""
    rng = random.Random(seed)
    n = layout.LEVELS[level].ecc_codewords
    k = layout.LEVELS[level].data_codewords
    for _ in range(trials):
        a = [rng.randrange(256) for _ in range(k)]
        b = [rng.randrange(256) for _ in range(k)]
        lhs = reed_solomon.encode([x ^ y for x, y in zip(a, b)], n)
        rhs = [x ^ y for x, y in zip(reed_solomon.encode(a, n), reed_solomon.encode(b, n))]
        if lhs != rhs:
            return False
    return True
