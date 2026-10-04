"""Поле GF(2^8) і код Ріда — Соломона."""

from __future__ import annotations

import random

import pytest

from qrv1 import gf256 as gf
from qrv1 import reed_solomon as rs


def test_field_tables_are_consistent() -> None:
    assert gf.EXP[0] == 1 and gf.EXP[255] == 1
    assert sorted(gf.EXP[:255]) == list(range(1, 256))        # α породжує всю групу
    for a in range(1, 256):
        assert gf.mul(a, gf.inverse(a)) == 1
        assert gf.EXP[gf.LOG[a]] == a


def test_multiplication_is_distributive() -> None:
    rng = random.Random(1)
    for _ in range(2000):
        a, b, c = (rng.randrange(256) for _ in range(3))
        assert gf.mul(a, b ^ c) == gf.mul(a, b) ^ gf.mul(a, c)
        assert gf.mul(a, b) == gf.mul(b, a)


def test_division_inverts_multiplication() -> None:
    rng = random.Random(2)
    for _ in range(2000):
        a, b = rng.randrange(256), rng.randrange(1, 256)
        assert gf.div(gf.mul(a, b), b) == a
    with pytest.raises(ZeroDivisionError):
        gf.div(1, 0)


def test_generator_has_expected_roots() -> None:
    g = rs.generator(17)
    assert len(g) == 18 and g[0] == 1
    for i in range(17):
        assert gf.poly_eval(g, gf.alpha(i)) == 0
    assert gf.poly_eval(g, gf.alpha(17)) != 0


def test_known_ecc_of_kata_example() -> None:
    # «Hi», рівень H: інформаційні слова та перевірні байти з тестів kata (Python).
    data = bytes.fromhex("40 24 86 90 ec 11 ec 11 ec")
    ecc = bytes.fromhex("fa ff 3c af 8a cd a9 0c 57 ee de 27 57 3a d5 54 46")
    assert bytes(rs.encode(data, 17)) == ecc
    assert not any(rs.syndromes(data + ecc, 17))


@pytest.mark.parametrize("nsym", [7, 10, 13, 17])
def test_corrects_errors_up_to_half_of_check_symbols(nsym: int) -> None:
    rng = random.Random(nsym)
    for _ in range(150):
        data = [rng.randrange(256) for _ in range(26 - nsym)]
        word = data + rs.encode(data, nsym)
        errors = rng.sample(range(26), nsym // 2)
        bad = word[:]
        for p in errors:
            bad[p] ^= rng.randrange(1, 256)
        fixed, changed = rs.decode(bad, nsym)
        assert fixed == word and changed == sorted(errors)


@pytest.mark.parametrize("nsym", [7, 17])
def test_erasures_cost_half_as_much_as_errors(nsym: int) -> None:
    rng = random.Random(100 + nsym)
    for _ in range(150):
        data = [rng.randrange(256) for _ in range(26 - nsym)]
        word = data + rs.encode(data, nsym)
        e = rng.randrange(nsym + 1)
        v = (nsym - e) // 2
        positions = rng.sample(range(26), e + v)
        bad = word[:]
        for p in positions:
            bad[p] ^= rng.randrange(1, 256)
        fixed, _ = rs.decode(bad, nsym, erasures=positions[:e])
        assert fixed == word


def test_reserve_limits_correction_capacity() -> None:
    data = list(range(9))
    word = data + rs.encode(data, 17)
    bad = word[:]
    for p in range(8):
        bad[p] ^= 0x55
    assert rs.decode(bad, 17, reserve=1)[0] == word          # 2·8 ≤ 17 − 1
    bad[8] ^= 0x55
    with pytest.raises(rs.RSDecodeError):                     # 9 помилок — забагато
        rs.decode(bad, 17, reserve=1)
    with pytest.raises(rs.RSDecodeError):
        rs.decode(word, 17, erasures=range(17), reserve=1)    # 17 стирань > 16


def test_clean_word_is_returned_unchanged() -> None:
    data = [7] * 9
    word = data + rs.encode(data, 17)
    assert rs.decode(word, 17) == (word, [])


def test_matches_independent_reedsolo_library() -> None:
    reedsolo = pytest.importorskip("reedsolo")
    rng = random.Random(3)
    for _ in range(300):
        nsym = rng.choice([7, 10, 13, 17])
        data = bytes(rng.randrange(256) for _ in range(26 - nsym))
        ours = bytes(rs.encode(data, nsym))
        theirs = bytes(reedsolo.RSCodec(nsym).encode(data))[len(data):]
        assert ours == theirs
