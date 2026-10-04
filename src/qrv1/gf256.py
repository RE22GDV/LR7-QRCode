"""Арифметика скінченного поля GF(2^8), у якому працює код Ріда — Соломона QR.

Поле побудовано за примітивним многочленом x^8 + x^4 + x^3 + x^2 + 1
(0x11D), твірний елемент α = 2. Додавання й віднімання — XOR, множення
й ділення — через таблиці степенів і логарифмів.

Многочлени зберігаються списками коефіцієнтів **від старшого степеня до
молодшого**: [1, 3, 2] означає x^2 + 3x + 2.
"""

from __future__ import annotations

PRIMITIVE = 0x11D
ORDER = 255                     # кількість ненульових елементів поля

EXP = [0] * (2 * ORDER)         # EXP[i] = α^i, подвоєна для множення без mod
LOG = [0] * 256                 # LOG[α^i] = i; LOG[0] не визначено

_x = 1
for _i in range(ORDER):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= PRIMITIVE
for _i in range(ORDER, 2 * ORDER):
    EXP[_i] = EXP[_i - ORDER]
del _x, _i


def mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("ділення на нуль у GF(256)")
    if a == 0:
        return 0
    return EXP[(LOG[a] - LOG[b]) % ORDER]


def inverse(a: int) -> int:
    return div(1, a)


def power(a: int, n: int) -> int:
    """a^n для цілого n (від'ємні степені — через обернений елемент)."""
    if a == 0:
        if n <= 0:
            raise ZeroDivisionError("0 у недодатному степені")
        return 0
    return EXP[(LOG[a] * n) % ORDER]


def alpha(n: int) -> int:
    """α^n для будь-якого цілого n."""
    return EXP[n % ORDER]


# --- многочлени (старший коефіцієнт першим) -------------------------------

def poly_add(p: list[int], q: list[int]) -> list[int]:
    size = max(len(p), len(q))
    out = [0] * size
    for i, c in enumerate(p):
        out[i + size - len(p)] ^= c
    for i, c in enumerate(q):
        out[i + size - len(q)] ^= c
    return out


def poly_scale(p: list[int], k: int) -> list[int]:
    return [mul(c, k) for c in p]


def poly_mul(p: list[int], q: list[int]) -> list[int]:
    out = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a == 0:
            continue
        for j, b in enumerate(q):
            out[i + j] ^= mul(a, b)
    return out


def poly_eval(p: list[int], x: int) -> int:
    """Значення многочлена в точці x за схемою Горнера."""
    y = 0
    for c in p:
        y = mul(y, x) ^ c
    return y


def poly_divmod(dividend: list[int], divisor: list[int]) -> tuple[list[int], list[int]]:
    """Ділення многочленів із остачею (синтетичне ділення)."""
    out = list(dividend)
    lead = divisor[0]
    for i in range(len(dividend) - len(divisor) + 1):
        coef = out[i]
        if coef == 0:
            continue
        if lead != 1:
            coef = div(coef, lead)
            out[i] = coef
        for j in range(1, len(divisor)):
            out[i + j] ^= mul(divisor[j], coef)
    sep = len(dividend) - len(divisor) + 1
    return out[:sep], out[sep:]
