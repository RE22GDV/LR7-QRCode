"""Командний інтерфейс: ``python run.py <команда>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import layout
from .decoder import QRDecodeError, decode, kata_scan
from .encoder import CapacityError, capacity, encode
from .image import matrix_from_text, matrix_to_text

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "tests" / "codewars_cases.json"


def _read_matrix(path: str) -> list[list[int]]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return matrix_from_text(text)


def cmd_selftest(_args) -> int:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    failures = 0
    for case in cases:
        matrix = matrix_from_text("\n".join(case["matrix"]))
        got = kata_scan(matrix)
        ok = got == case["expected"]
        try:
            full = decode(matrix)
            standard = f"повний декодер: «{full.text}», рівень {full.level}, маска {full.mask}"
        except QRDecodeError:
            standard = "повний декодер: корекція не вдалася"
        failures += not ok
        print(f"[{'OK' if ok else 'FAIL'}] {case['source']:<9} {case['test']:<26} "
              f"-> {got!r:<10} | {standard}")
    print("пройдено все" if failures == 0 else f"FAIL: {failures}")
    return 0 if failures == 0 else 1


def cmd_scan(args) -> int:
    print(kata_scan(_read_matrix(args.file)))
    return 0


def cmd_decode(args) -> int:
    erasures = []
    for item in args.erase or []:
        r, c = (int(v) for v in item.split(","))
        erasures.append((r, c))
    try:
        result = decode(_read_matrix(args.file), erasure_modules=erasures)
    except QRDecodeError as exc:
        print(f"не прочитано: {exc}", file=sys.stderr)
        return 1
    print(result.text)
    print(f"рівень {result.level}, маска {result.mask}, "
          f"хибних бітів формату {result.format_distance}, "
          f"виправлено кодових слів: {result.errors_corrected} {result.corrected}",
          file=sys.stderr)
    return 0


def cmd_encode(args) -> int:
    try:
        qr = encode(args.text, args.level, args.mask, args.mode)
    except (CapacityError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print(matrix_to_text(qr.matrix, "██", "  ") if args.blocks else matrix_to_text(qr.matrix))
    print(f"рівень {qr.level}, маска {qr.mask}, режим {qr.mode}", file=sys.stderr)
    if args.png:
        from .image import save_png
        save_png(qr.matrix, args.png)
    return 0


def cmd_capacity(_args) -> int:
    print("рівень  дані  корекція  t  p  цифри  букв.-цифр.  байти")
    for name, lv in layout.LEVELS.items():
        print(f"{name:>6} {lv.data_codewords:>5} {lv.ecc_codewords:>9} {lv.correctable:>2} "
              f"{lv.reserve:>2} {capacity(name, 'numeric'):>6} "
              f"{capacity(name, 'alphanumeric'):>12} {capacity(name, 'byte'):>6}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="qrv1", description="QR-код версії 1 (ЛР7)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("selftest", help="контрольні матриці Codewars").set_defaults(fn=cmd_selftest)

    p = sub.add_parser("scan", help="kata-декодер (76 бітів, маска 0)")
    p.add_argument("file", help="файл із 21 рядком 0/1 або #/. ('-' — stdin)")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("decode", help="повний декодер з корекцією Ріда — Соломона")
    p.add_argument("file")
    p.add_argument("--erase", nargs="*", metavar="R,C", help="відомо пошкоджені модулі")
    p.set_defaults(fn=cmd_decode)

    p = sub.add_parser("encode", help="закодувати текст у QR версії 1")
    p.add_argument("text")
    p.add_argument("--level", default="H", choices=list(layout.LEVELS))
    p.add_argument("--mask", type=int, default=None, choices=range(8))
    p.add_argument("--mode", default="byte", choices=["byte", "alphanumeric", "numeric", "auto"])
    p.add_argument("--blocks", action="store_true", help="вивести суцільними блоками")
    p.add_argument("--png", help="зберегти зображення (потрібен Pillow)")
    p.set_defaults(fn=cmd_encode)

    sub.add_parser("capacity", help="місткість версії 1").set_defaults(fn=cmd_capacity)

    args = parser.parse_args(argv)
    return args.fn(args)
