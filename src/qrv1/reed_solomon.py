"""Код Ріда — Соломона над GF(2^8) у варіанті стандарту QR (ISO/IEC 18004).

Твірний многочлен для ``nsym`` перевірних байтів:

    g(x) = (x − α^0)(x − α^1) … (x − α^(nsym−1)).

Кодер дописує до даних остачу від ділення D(x)·x^nsym на g(x).
Декодер виправляє помилки (невідомі позиції) та стирання (відомі
позиції): синдроми → модифіковані синдроми Форні → алгоритм
Берлекемпа — Мессі → пошук Ченя → формула Форні. Виправлення можливе,
якщо 2ν + e ≤ nsym − p, де ν — кількість помилок, e — стирань,
p — резерв перевірних байтів для захисту від хибного декодування
(у QR версії 1 p = 3, 2, 1, 1 для рівнів L, M, Q, H).

Позиції в кодовому слові рахуються зліва направо, як байти в символі:
байт з індексом i відповідає степеню n − 1 − i.
"""

from __future__ import annotations

from . import gf256 as gf


class RSDecodeError(ValueError):
    """Кодове слово неможливо виправити в заданих межах."""


def generator(nsym: int) -> list[int]:
    """Твірний многочлен g(x), старший коефіцієнт першим."""
    g = [1]
    for i in range(nsym):
        g = gf.poly_mul(g, [1, gf.alpha(i)])
    return g


def encode(data: list[int] | bytes, nsym: int) -> list[int]:
    """Перевірні байти для повідомлення ``data``."""
    _, remainder = gf.poly_divmod(list(data) + [0] * nsym, generator(nsym))
    return remainder


def syndromes(codeword: list[int] | bytes, nsym: int) -> list[int]:
    """S_j = R(α^j), j = 0 … nsym − 1. Усі нулі — слово кодове."""
    word = list(codeword)
    return [gf.poly_eval(word, gf.alpha(j)) for j in range(nsym)]


# --- допоміжні операції з многочленами «молодший коефіцієнт першим» ------

def _lf_mul(p: list[int], q: list[int]) -> list[int]:
    out = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a == 0:
            continue
        for j, b in enumerate(q):
            out[i + j] ^= gf.mul(a, b)
    return out


def _lf_eval(p: list[int], x: int) -> int:
    y = 0
    for c in reversed(p):
        y = gf.mul(y, x) ^ c
    return y


def _lf_derivative(p: list[int]) -> list[int]:
    # У полі характеристики 2 лишаються тільки непарні степені.
    return [p[i] if i % 2 == 1 else 0 for i in range(1, len(p))] or [0]


def _trim(p: list[int]) -> list[int]:
    while len(p) > 1 and p[-1] == 0:
        p = p[:-1]
    return p


def berlekamp_massey(seq: list[int]) -> tuple[list[int], int]:
    """Найкоротший РЗЗЗ, що породжує послідовність: (Λ(x) молодшим першим, L)."""
    c, b = [1], [1]
    length, shift, last = 0, 1, 1
    for n, s in enumerate(seq):
        delta = s
        for i in range(1, min(length, len(c) - 1) + 1):
            delta ^= gf.mul(c[i], seq[n - i])
        if delta == 0:
            shift += 1
            continue
        coef = gf.div(delta, last)
        updated = c + [0] * max(0, len(b) + shift - len(c))
        for i, bi in enumerate(b):
            updated[i + shift] ^= gf.mul(coef, bi)
        if 2 * length <= n:
            b, last = c, delta
            length = n + 1 - length
            shift = 1
        else:
            shift += 1
        c = updated
    return _trim(c), length


def decode(codeword: list[int] | bytes, nsym: int, erasures=(), reserve: int = 0
           ) -> tuple[list[int], list[int]]:
    """Виправити кодове слово.

    Повертає (виправлене слово, відсортовані позиції змінених байтів).
    ``erasures`` — індекси байтів із відомо ненадійним значенням.
    ``reserve`` — кількість перевірних байтів, які не витрачаються на
    виправлення (захист від хибного декодування).
    Якщо слово виправити не вдається, підіймає :class:`RSDecodeError`.
    """
    word = list(codeword)
    n = len(word)
    if n > gf.ORDER:
        raise ValueError("кодове слово довше за 255 байтів")
    if not 0 < nsym < n:
        raise ValueError("некоректна кількість перевірних байтів")
    budget = nsym - reserve
    erased = sorted(set(erasures))
    if any(not 0 <= p < n for p in erased):
        raise ValueError("позиція стирання поза кодовим словом")
    if len(erased) > budget:
        raise RSDecodeError("стирань більше, ніж дозволяє запас перевірних байтів")
    for p in erased:
        word[p] = 0

    synd = syndromes(word, nsym)
    if not any(synd):
        changed = [p for p in erased if word[p] != codeword[p]]
        return word, changed

    # Локатор стирань Γ(x) = ∏ (1 + X·x), X = α^(n−1−p).
    gamma = [1]
    for p in erased:
        gamma = _lf_mul(gamma, [1, gf.alpha(n - 1 - p)])
    e = len(erased)

    # Модифіковані синдроми Форні: внесок стирань вилучено.
    forney = []
    for j in range(e, nsym):
        value = 0
        for i in range(e + 1):
            value ^= gf.mul(gamma[i], synd[j - i])
        forney.append(value)

    lam, nu = berlekamp_massey(forney)
    if len(lam) - 1 != nu or 2 * nu + e > budget:
        raise RSDecodeError("помилок більше, ніж здатен виправити код")

    psi = _lf_mul(lam, gamma)                       # локатор помилок і стирань
    positions = [p for p in range(n) if _lf_eval(psi, gf.alpha(-(n - 1 - p))) == 0]
    if len(positions) != len(psi) - 1:
        raise RSDecodeError("корені локатора не збігаються з позиціями слова")

    omega = _lf_mul(synd, psi)[:nsym]               # Ω(x) = S(x)Ψ(x) mod x^nsym
    dpsi = _lf_derivative(psi)
    for p in positions:
        x_inv = gf.alpha(-(n - 1 - p))
        denominator = _lf_eval(dpsi, x_inv)
        if denominator == 0:
            raise RSDecodeError("нульова похідна локатора")
        magnitude = gf.div(gf.mul(gf.alpha(n - 1 - p), _lf_eval(omega, x_inv)), denominator)
        word[p] ^= magnitude

    if any(syndromes(word, nsym)):
        raise RSDecodeError("після виправлення синдроми ненульові")
    changed = [p for p in positions if word[p] != codeword[p]]
    return word, sorted(changed)
