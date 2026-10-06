"""
Обчислювальні експерименти лабораторної роботи.

    python experiments/run_experiments.py            # усі експерименти
    python experiments/run_experiments.py --quick    # скорочений прогін

Результати:
    docs/results/experiments.json   — усі виміряні величини
    docs/results/summary.md         — зведена таблиця
    docs/figures/*.png              — рисунки (+ pdf/ — версії без заголовків)

Ймовірності для випадкових пошкоджень обчислюються точно (комбінаторно),
а симуляція з фіксованим зерном слугує незалежною перевіркою, тож прогін
відтворюється число в число. Час виконання, звісно, залежить від машини.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

from qrv1 import analysis, capacity, decode, encode, kata_scan, layout  # noqa: E402
from qrv1.decoder import read_codewords  # noqa: E402
from qrv1.encoder import place_codewords  # noqa: E402
from qrv1.image import (matrix_from_text, opencv_available, opencv_decode,  # noqa: E402
                        opencv_encode)

SEED = 20261004

# --------------------------------------------------------------------------- #
#  Оформлення: категорійні слоти 1–3 (синій, помаранчевий, бірюзовий)
# --------------------------------------------------------------------------- #

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2de"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
S4 = "#8a63d2"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
    "axes.titlesize": 12, "axes.titleweight": "semibold", "axes.labelsize": 9.5,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": INK_2, "ytick.color": INK_2, "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5, "legend.frameon": False, "legend.fontsize": 9,
    "lines.linewidth": 2.0, "font.size": 10,
})

FIG = ROOT / "docs" / "figures"
RES = ROOT / "docs" / "results"
CASES = json.loads((ROOT / "tests" / "codewars_cases.json").read_text(encoding="utf-8"))["cases"]


def _n(v: float, d: int = 2) -> str:
    return ("%.*f" % (d, v)).replace(".", ",")


def plural(n: int, one: str, few: str, many: str) -> str:
    """Узгодження з числівником: 1 модуль, 2 модулі, 5 модулів."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def _finish(ax, note: str | None = None, note_y: float = -0.17) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if note:
        ax.text(0.995, note_y, note, transform=ax.transAxes, ha="right", va="top",
                fontsize=7.5, color=INK_2)


def cpu_name() -> str:
    """Назва процесора (у Windows — з WMI, інакше — з platform)."""
    if sys.platform == "win32":
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "(Get-CimInstance Win32_Processor).Name"],
                                 capture_output=True, text=True, timeout=30).stdout.strip()
            if out:
                return " ".join(out.split())
        except (OSError, subprocess.SubprocessError):
            pass
    return platform.processor() or platform.machine()


def save(fig, name: str) -> str:
    """Із заголовком — для README; без заголовка (pdf/) — для звіту."""
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / name, dpi=200, bbox_inches="tight")
    (FIG / "pdf").mkdir(parents=True, exist_ok=True)
    if fig._suptitle is not None:
        fig.suptitle("")
    fig.savefig(FIG / "pdf" / name, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("    рисунок -> docs/figures/%s (+ pdf/)" % name)
    return "docs/figures/" + name


def _matrix(case) -> list[list[int]]:
    return matrix_from_text("\n".join(case["matrix"]))


def draw_symbol(ax, matrix, title: str | None = None, border: int = 1,
                highlight=(), highlight_color: str = S2, title_color: str = INK) -> None:
    """Символ QR на осях: темні модулі чорні, з тонкою світлою рамкою."""
    n = len(matrix)
    ax.imshow([[1] * (n + 2 * border)] * (n + 2 * border), cmap="gray", vmin=0, vmax=1,
              extent=(-border - 0.5, n + border - 0.5, n + border - 0.5, -border - 0.5))
    rgb = [[(0.05, 0.05, 0.05) if v else (1, 1, 1) for v in row] for row in matrix]
    ax.imshow(rgb, extent=(-0.5, n - 0.5, n - 0.5, -0.5), interpolation="nearest")
    for r, c in highlight:
        ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, fill=False, ec=highlight_color, lw=1.6))
    ax.set_xlim(-border - 0.5, n + border - 0.5)
    ax.set_ylim(n + border - 0.5, -border - 0.5)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    if title:
        ax.set_title(title, fontsize=9.5, color=title_color, fontweight="semibold")


def _ocv(matrix) -> dict:
    if not opencv_available():
        return {"classic": None, "aruco": None}
    return {"classic": opencv_decode(matrix), "aruco": opencv_decode(matrix, detector="aruco")}


# --------------------------------------------------------------------------- #
#  1. Анатомія символу «Warrior» і 76 бітів kata
# --------------------------------------------------------------------------- #

def exp_anatomy() -> dict:
    print("[1] Анатомія символу версії 1")
    qr = encode("Warrior", "H", 0)
    kinds = {}
    for r in range(21):
        for c in range(21):
            k = layout.module_kind(r, c)
            kinds[k] = kinds.get(k, 0) + 1

    fields = (["mode"] * 4 + ["length"] * 8 + ["text"] * 56 + ["terminator"] * 4
              + ["ecc"] * (208 - 72))
    colors = {"finder": "#3d3d3a", "separator": "#f1f0ec", "timing": "#9a9893",
              "format": S2, "dark": "#000000",
              "mode": S4, "length": S3, "text": S1, "terminator": "#a9c8ef", "ecc": "#f6c9b3"}

    def hexrgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    grid = [[hexrgb(colors[layout.module_kind(r, c)]) if layout.is_function(r, c) else None
             for c in range(21)] for r in range(21)]
    for i, (r, c) in enumerate(layout.DATA_POSITIONS):
        base = hexrgb(colors[fields[i]])
        if fields[i] == "ecc" and (i // 8) % 2:
            base = tuple(0.88 * v for v in base)
        if fields[i] == "text" and ((i - 12) // 8) % 2:
            base = tuple(0.68 * v for v in base)
        grid[r][c] = base

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 5.4), gridspec_kw={"width_ratios": [1, 1.08]})
    draw_symbol(axes[0], qr.matrix, "а) символ «Warrior» (рівень H, маска 0)", border=2)

    ax = axes[1]
    ax.imshow(grid, extent=(-0.5, 20.5, 20.5, -0.5), interpolation="nearest")
    for k in range(22):
        ax.axhline(k - 0.5, color="white", lw=0.4)
        ax.axvline(k - 0.5, color="white", lw=0.4)
    # шлях читання: ламана, розірвана там, де шлях перескакує службові зони
    seg = [layout.DATA_POSITIONS[0]]
    for prev, cur in zip(layout.DATA_POSITIONS, layout.DATA_POSITIONS[1:]):
        if max(abs(prev[0] - cur[0]), abs(prev[1] - cur[1])) > 1:
            ax.plot([p[1] for p in seg], [p[0] for p in seg], color=INK, lw=0.7, alpha=0.75)
            seg = []
        seg.append(cur)
    ax.plot([p[1] for p in seg], [p[0] for p in seg], color=INK, lw=0.7, alpha=0.75)
    ax.annotate("", xy=(19.6, 16.2), xytext=(19.6, 20.2),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.6))
    ax.text(20.9, 20.6, "старт", fontsize=7.5, color=INK, ha="left", va="center")
    for w in range(26):
        pts = [p for i, p in enumerate(layout.DATA_POSITIONS) if i // 8 == w]
        mr = sum(p[0] for p in pts) / 8
        mc = sum(p[1] for p in pts) / 8
        # номер — на модулі самого слова, найближчому до його центру
        rr, cc = min(pts, key=lambda p: (p[0] - mr) ** 2 + (p[1] - mc) ** 2)
        cc = sum(p[1] for p in pts if p[0] == rr) / sum(1 for p in pts if p[0] == rr)
        ax.text(cc, rr, str(w), ha="center", va="center", fontsize=6.6, color="white",
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.12", fc=(0, 0, 0, 0.45), ec="none"))
    ax.set_xlim(-0.5, 21.6)
    ax.set_ylim(20.5, -0.5)
    ax.set_xticks(range(0, 21, 4))
    ax.set_yticks(range(0, 21, 4))
    ax.grid(False)
    ax.set_title("б) призначення модулів і порядок читання", fontsize=9.5, fontweight="semibold")
    legend = [Patch(color=colors[k], label=v) for k, v in (
        ("mode", "режим 0100 (4 біти)"), ("length", "довжина 7 (8 бітів)"),
        ("text", "текст: 7 байтів"), ("terminator", "термінатор 0000"),
        ("ecc", "17 байтів корекції"), ("format", "формат: рівень і маска"),
        ("finder", "шукові візерунки"), ("separator", "роздільники"),
        ("timing", "синхронізація"), ("dark", "темний модуль"))]
    fig.legend(handles=legend, loc="lower center", ncol=5, fontsize=8, bbox_to_anchor=(0.5, -0.06))
    fig.suptitle("Рисунок 1 — Будова QR-коду версії 1 і шлях читання бітів", fontsize=12,
                 fontweight="semibold")
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    path = save(fig, "fig1_anatomy.png")

    bits = "".join(str(b) for b in
                   [qr.matrix[r][c] ^ ((r + c) % 2 == 0) for r, c in layout.DATA_POSITIONS[:76]])
    return {
        "figure": path,
        "module_kinds": kinds,
        "first_76_bits": bits,
        "fields": {"mode": bits[:4], "length": bits[4:12],
                   "text": [bits[12 + 8 * i:20 + 8 * i] for i in range(7)],
                   "terminator": bits[68:72], "ecc_head": bits[72:76]},
        "data_codewords": qr.data,
        "ecc_codewords": qr.ecc,
        "codeword_modules": 8,
    }


# --------------------------------------------------------------------------- #
#  2. Аудит тестових матриць Codewars
# --------------------------------------------------------------------------- #

def exp_samples() -> dict:
    print("[2] Тестові матриці Codewars: kata, повний декодер, OpenCV")
    rows = []
    py = {c["expected"]: _matrix(c) for c in CASES if c["source"] == "python"}
    for case in CASES:
        m = _matrix(case)
        try:
            full = decode(m)
            full_text, corrected = full.text, len(full.corrected)
        except Exception:
            full_text, corrected = None, None
        diff = None
        if case["source"] == "csharp":
            a, b = read_codewords(m, 0), read_codewords(py[case["expected"]], 0)
            diff = [i for i in range(26) if a[i] != b[i]]
        level, mask, dist = layout.decode_format(m)
        rows.append({
            "source": case["source"], "test": case["test"], "expected": case["expected"],
            "kata": kata_scan(m), "full": full_text, "corrected": corrected,
            "format": [level, mask, dist], "opencv": _ocv(m),
            "codewords_differing_from_python": diff,
            "encoder_identical": encode(case["expected"], "H", 0).matrix == m,
        })

    fig, axes = plt.subplots(3, 3, figsize=(8.6, 9.4))
    order = ([r for r in rows if r["source"] == "csharp"] + [r for r in rows if r["source"] == "python"]
             + [r for r in rows if r["source"] == "statement"])
    pos = [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 1), (2, 2)]
    by_key = {(r["source"], r["expected"]): r for r in rows}
    layout_cells = [("csharp", "Hi"), ("csharp", "Warrior"), ("csharp", "T3st"),
                    ("python", "Hi"), ("python", "Warrior"), ("python", "T3st"),
                    ("csharp", "T!st"), ("python", "T!st"), ("statement", "Hello")]
    for (src, text), ax in zip(layout_cells, axes.flat):
        r = by_key[(src, text)]
        m = _matrix(next(c for c in CASES if c["source"] == src and c["expected"] == text))
        ok = r["full"] == text
        label = {"csharp": "C#", "python": "Python", "statement": "умова"}[src]
        draw_symbol(ax, m, f"{label}: «{text}»", border=1,
                    title_color=INK)
        status = ("kata ✓   Ріда — Соломона ✓   OpenCV ✓" if ok and r["opencv"]["classic"] == text
                  else "kata ✓   Ріда — Соломона ✗   OpenCV ✗")
        ax.text(10, 22.6, status, ha="center", va="top", fontsize=7.6,
                color=S3 if ok else S2, fontweight="semibold")
        for s in ax.spines.values():
            s.set_visible(True)
            s.set_edgecolor(S3 if ok else S2)
            s.set_linewidth(2.2)
    del order, pos
    fig.suptitle("Рисунок 2 — Пробні матриці Codewars (C#, Python) і приклад з умови",
                 fontsize=12, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.96), h_pad=2.4)
    path = save(fig, "fig2_samples.png")
    return {"figure": path, "cases": rows}


def exp_csharp_diff() -> dict:
    print("[3] Різниця між C#- і Python-матрицями «Warrior»")
    cs = _matrix(next(c for c in CASES if c["source"] == "csharp" and c["expected"] == "Warrior"))
    py = _matrix(next(c for c in CASES if c["source"] == "python" and c["expected"] == "Warrior"))
    diff = [(r, c) for r in range(21) for c in range(21) if cs[r][c] != py[r][c]]
    words = sorted({layout.CODEWORD_OF_MODULE[p] for p in diff})
    fig, axes = plt.subplots(1, 3, figsize=(10.6, 4.0))
    draw_symbol(axes[0], py, "а) тест Python (коректний)", border=1)
    draw_symbol(axes[1], cs, "б) тест C#", border=1)
    ax = axes[2]
    pale = [[(0.93, 0.93, 0.91) if layout.is_function(r, c) else (1, 1, 1) for c in range(21)]
            for r in range(21)]
    for i, (r, c) in enumerate(layout.DATA_POSITIONS):
        if i // 8 in words:
            pale[r][c] = (0.99, 0.90, 0.85)
    for r, c in diff:
        pale[r][c] = tuple(int(S2[i:i + 2], 16) / 255 for i in (1, 3, 5))
    ax.imshow(pale, extent=(-0.5, 20.5, 20.5, -0.5), interpolation="nearest")
    for k in range(22):
        ax.axhline(k - 0.5, color=GRID, lw=0.4)
        ax.axvline(k - 0.5, color=GRID, lw=0.4)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_title(f"в) {len(diff)} різних модулів, слова {words[0]}–{words[-1]}", fontsize=9.5,
                 fontweight="semibold")
    fig.suptitle("Рисунок 3 — Тести C# відрізняються лише байтами корекції", fontsize=12,
                 fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    path = save(fig, "fig3_csharp_diff.png")
    a, b = read_codewords(cs, 0), read_codewords(py, 0)
    return {"figure": path, "modules_differing": len(diff), "codewords_differing": words,
            "csharp_codewords": a, "python_codewords": b}


# --------------------------------------------------------------------------- #
#  4. Випадкові пошкодження модулів
# --------------------------------------------------------------------------- #

def exp_random_errors(rng: random.Random, quick: bool) -> dict:
    print("[4] Випадкові інверсії модулів даних: точні ймовірності та симуляція")
    ks = list(range(0, 41))
    trials = 300 if quick else 2000
    exact = {"kata": [float(analysis.kata_success(k, 7)) for k in ks]}
    for name, lv in layout.LEVELS.items():
        exact[name] = [float(analysis.rs_success(k, lv.correctable)) for k in ks]
    qr = encode("Warrior", "H", 0)
    mc_ks = list(range(0, 41, 2))
    mc = []
    for k in mc_ks:
        kata, full = analysis.simulate_random_flips(qr, "Warrior", k, trials, rng)
        mc.append({"k": k, "trials": trials,
                   "kata": vars(kata), "full_h": vars(full)})
        print(f"    k={k:2d}: kata {kata.correct / trials:6.1%} (тихо хибних {kata.wrong})  "
              f"повний H {full.correct / trials:6.1%} (хибних {full.wrong})")

    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.1))
    ax = axes[0]
    ax.plot(ks, exact["kata"], color=INK_2, ls="--", label="kata: без корекції")
    for name, color, ls in (("L", S4, ":"), ("M", S3, "-."), ("Q", S2, "--"), ("H", S1, "-")):
        t = layout.LEVELS[name].correctable
        ax.plot(ks, exact[name], color=color, ls=ls, label=f"рівень {name} (t = {t})")
    ax.plot(mc_ks, [p["kata"]["correct"] / p["trials"] for p in mc], "o", color=INK_2, ms=4)
    ax.plot(mc_ks, [p["full_h"]["correct"] / p["trials"] for p in mc], "o", color=S1, ms=4,
            label="симуляція")
    ax.set_xlabel("кількість інвертованих модулів даних k (із 208)")
    ax.set_ylabel("частка правильно прочитаних")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("а) успіх читання")
    ax.set_xlim(-0.8, 24.8)
    ax.legend(loc="upper right", fontsize=8)
    _finish(ax)

    ax = axes[1]
    ax.plot(mc_ks, [p["kata"]["wrong"] / p["trials"] for p in mc], "o-", color=INK_2, ms=4,
            label="kata: хибний текст без попередження")
    ax.plot(mc_ks, [p["full_h"]["failed"] / p["trials"] for p in mc], "s-", color=S1, ms=4,
            label="повний декодер: помилку виявлено")
    ax.plot(mc_ks, [p["full_h"]["wrong"] / p["trials"] for p in mc], "^-", color=S2, ms=4,
            label="повний декодер: хибний текст")
    ax.set_xlabel("кількість інвертованих модулів даних k")
    ax.set_ylabel("частка спроб")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("б) що отримує користувач у разі невдачі")
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 0.06), fontsize=8)
    _finish(ax, f"симуляція: {trials} спроб на точку, зерно {SEED}")
    fig.suptitle("Рисунок 4 — Випадкові пошкодження: kata-декодер і код Ріда — Соломона",
                 fontsize=12, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    path = save(fig, "fig4_random_errors.png")

    def threshold(curve, level=0.5):
        for k, p in zip(ks, curve):
            if p < level:
                return k
        return None

    return {"figure": path, "k": ks, "exact": exact, "simulation": mc,
            "k_half": {name: threshold(curve) for name, curve in exact.items()},
            "exact_points": {str(k): {"kata": exact["kata"][ks.index(k)], "H": exact["H"][ks.index(k)]}
                             for k in (8, 16, 24, 32, 40)}}


def exp_miscorrection() -> dict:
    """Аналітична оцінка ймовірності хибного декодування випадкового слова."""
    from math import comb
    out = {}
    for name, lv in layout.LEVELS.items():
        sphere = sum(comb(26, i) * 255 ** i for i in range(lv.correctable + 1))
        # частка випадкових слів, які потрапляють у кулю радіуса t довкола якогось кодового слова
        out[name] = {"t": lv.correctable, "reserve": lv.reserve,
                     "bound": sphere / 256 ** lv.ecc_codewords}
        no_reserve = (lv.ecc_codewords) // 2
        sphere2 = sum(comb(26, i) * 255 ** i for i in range(no_reserve + 1))
        out[name]["t_without_reserve"] = no_reserve
        out[name]["bound_without_reserve"] = sphere2 / 256 ** lv.ecc_codewords
    return out


# --------------------------------------------------------------------------- #
#  5. Плями та логотип: помилки проти стирань
# --------------------------------------------------------------------------- #

def exp_blocks(rng: random.Random, quick: bool) -> dict:
    print("[5] Квадратні плями: невідомі позиції (помилки) і відомі (стирання)")
    qr = encode("Warrior", "H", 0)
    sides = list(range(1, 15))
    trials = 200 if quick else 1000
    rows = []
    for s in sides:
        err, era, touched = analysis.simulate_blocks(qr, "Warrior", s, trials, rng)
        rows.append({"side": s, "trials": trials, "errors": vars(err), "erasures": vars(era),
                     "touched_mean": sum(touched) / len(touched), "touched_max": max(touched)})
        print(f"    s={s:2d}: помилки {err.correct / trials:6.1%}  стирання {era.correct / trials:6.1%}"
              f"  слів зачеплено в середньому {sum(touched) / len(touched):5.2f}")

    logo = []
    for s in range(1, 16, 2):
        covered = analysis.centered_block(s)
        data_cov = analysis.data_modules_in(covered)
        # Логотип закриває модулі даних; службові візерунки лишаються видимими.
        painted = analysis.paint_modules(qr.matrix, data_cov, 0)
        logo.append({
            "side": s, "modules": len(covered), "data_modules": len(data_cov),
            "share_of_symbol": len(covered) / 441,
            "codewords_touched": len(analysis.codewords_touched(covered)),
            "codewords_wrong": len({layout.CODEWORD_OF_MODULE[p] for p in data_cov
                                    if qr.matrix[p[0]][p[1]] != 0}),
            "ours_errors": analysis.full_text(painted),
            "ours_erasures": analysis.full_text(painted, erasure_modules=data_cov),
            "opencv": _ocv(painted),
        })

    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.1))
    ax = axes[0]
    ax.plot(sides, [r["errors"]["correct"] / r["trials"] for r in rows], "o-", color=S1, ms=4,
            label="позиції невідомі (помилки)")
    ax.plot(sides, [r["erasures"]["correct"] / r["trials"] for r in rows], "s-", color=S3, ms=4,
            label="позиції відомі (стирання)")
    ax.set_xlabel("сторона плями s, модулів")
    ax.set_ylabel("частка правильно прочитаних")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("а) успіх читання, рівень H")
    ax.legend(loc="lower left", fontsize=8.5)
    _finish(ax)
    ax = axes[1]
    ax.plot(sides, [r["touched_mean"] for r in rows], "o-", color=S2, ms=4,
            label="зачеплено кодових слів (середнє)")
    ax.axhline(8, color=S1, ls="--", lw=1.4, label="t = 8 помилок")
    ax.axhline(14, color=S3, ls="--", lw=1.4, label="14 стирань (p = 3)")
    ax.set_xlabel("сторона плями s, модулів")
    ax.set_ylabel("кодових слів із 26")
    ax.set_title("б) скільки слів зачіпає пляма")
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 0.52), fontsize=8.5)
    _finish(ax, f"{trials} випадкових положень на точку; пляма біла, змінює лише модулі даних")
    fig.suptitle("Рисунок 5 — Суцільні пошкодження: виправлення помилок і стирань",
                 fontsize=12, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    path = save(fig, "fig5_blocks.png")

    # Рисунок логотипа: найбільший квадрат, який читають обидва декодери, і більший.
    both = [r for r in logo if r["ours_errors"] == "Warrior" and r["opencv"]["classic"] == "Warrior"]
    only_erasures = [r for r in logo if r["ours_errors"] != "Warrior" and r["ours_erasures"] == "Warrior"]
    picks = [both[-1]["side"] if both else 3]
    if only_erasures:
        picks.append(only_erasures[0]["side"])
    fig, axes = plt.subplots(1, len(picks) + 1, figsize=(3.5 * (len(picks) + 1), 4.0))
    draw_symbol(axes[0], qr.matrix, "а) без логотипа", border=2)
    for ax, s, letter in zip(axes[1:], picks, "бв"):
        r = next(x for x in logo if x["side"] == s)
        covered = analysis.centered_block(s)
        draw_symbol(ax, analysis.paint_modules(qr.matrix, analysis.data_modules_in(covered), 0),
                    f"{letter}) логотип {s} × {s}: "
                    + plural(r["codewords_touched"], "слово", "слова", "слів") + " із 26",
                    border=2)
        ax.add_patch(Rectangle((covered[0][1] - 0.5, covered[0][0] - 0.5), s, s, fill=False,
                               ec=S2, lw=1.8, ls="--"))
        ok = lambda v: "✓" if v == "Warrior" else "✗"  # noqa: E731
        ax.text(10, 23.2, f"помилки {ok(r['ours_errors'])}   стирання {ok(r['ours_erasures'])}   "
                          f"OpenCV {ok(r['opencv']['classic'])}",
                ha="center", va="top", fontsize=8, color=INK_2)
    fig.suptitle("Рисунок 6 — Логотип у центрі символу рівня H", fontsize=12, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    logo_path = save(fig, "fig6_logo.png")
    return {"figure": path, "logo_figure": logo_path, "sides": rows, "logo": logo,
            "logo_pictured": picks}


# --------------------------------------------------------------------------- #
#  6. Маски та штрафи
# --------------------------------------------------------------------------- #

def exp_masks() -> dict:
    print("[6] Маски: штрафні бали для «Warrior», рівень H")
    qr = encode("Warrior", "H", 0)
    scores = []
    for m in range(8):
        mat = place_codewords(qr.codewords, "H", m)
        n = layout.penalty(mat)
        dark = sum(map(sum, mat))
        scores.append({"mask": m, "N1": n[0], "N2": n[1], "N3": n[2], "N4": n[3], "total": sum(n),
                       "dark_share": dark / 441})
    best = min(scores, key=lambda s: (s["total"], s["mask"]))["mask"]
    ocv_mask = None
    if opencv_available():
        ocv_mask = decode(opencv_encode("Warrior", "H")).mask

    fig = plt.figure(figsize=(10.6, 5.3))
    gs = fig.add_gridspec(2, 8, height_ratios=[1, 2.1], hspace=0.22)
    for m in range(8):
        ax = fig.add_subplot(gs[0, m])
        draw_symbol(ax, place_codewords(qr.codewords, "H", m), f"маска {m}", border=1,
                    title_color=S1 if m == best else (S2 if m == 0 else INK))
    ax = fig.add_subplot(gs[1, :])
    bottom = [0] * 8
    for key, color, label in (("N1", S1, "N1: серії ≥ 5"), ("N2", S3, "N2: блоки 2 × 2"),
                              ("N3", S2, "N3: схожість на шуковий візерунок"),
                              ("N4", S4, "N4: баланс темних модулів")):
        vals = [s[key] for s in scores]
        ax.bar(range(8), vals, bottom=bottom, color=color, label=label, width=0.62)
        bottom = [b + v for b, v in zip(bottom, vals)]
    for m, s in enumerate(scores):
        ax.text(m, s["total"] + 8, str(s["total"]), ha="center", va="bottom", fontsize=8.5,
                color=INK, fontweight="semibold" if m == best else "normal")
    ax.set_xticks(range(8), [f"{m}" + (" (kata)" if m == 0 else "") + (" ★" if m == best else "")
                             for m in range(8)])
    ax.set_ylabel("штрафні бали")
    ax.set_xlabel("номер маски (★ — найменший штраф)")
    ax.set_ylim(0, max(s["total"] for s in scores) * 1.15)
    ax.legend(ncol=2, fontsize=8, loc="upper left")
    _finish(ax)
    fig.suptitle("Рисунок 7 — Вісім масок одного повідомлення та їхні штрафи", fontsize=12,
                 fontweight="semibold")
    path = save(fig, "fig7_masks.png")
    return {"figure": path, "scores": scores, "best_mask": best, "opencv_mask": ocv_mask}


def exp_interop() -> dict:
    print("[7] Сумісність з OpenCV")
    if not opencv_available():
        return {"available": False}
    texts = ["Hi", "Warrior", "T3st", "T!st", "Hello", "QR", "12345", "HELLO WORLD"]
    ours_total = classic_ok = aruco_ok = any_ok = 0
    failures = []
    for lv in "LMQH":
        for m in range(8):
            for t in texts:
                try:
                    q = encode(t, lv, m, mode="auto")
                except Exception:
                    continue
                ours_total += 1
                c = opencv_decode(q.matrix) == t
                a = opencv_decode(q.matrix, detector="aruco") == t
                classic_ok += c
                aruco_ok += a
                any_ok += c or a
                if not c:
                    failures.append({"level": lv, "mask": m, "text": t, "mode": q.mode, "aruco": a})
    theirs_total = theirs_read = identical = 0
    mask_mismatch = []
    for lv in "LMQH":
        for t in texts:
            for mode in ("byte", "auto"):
                try:
                    mm = opencv_encode(t, lv, mode)
                except Exception:
                    continue
                theirs_total += 1
                r = decode(mm)
                theirs_read += r.text == t
                ours = encode(t, lv, None, "byte" if mode == "byte" else "auto")
                if ours.matrix == mm:
                    identical += 1
                else:
                    same_mask = encode(t, lv, r.mask, "byte" if mode == "byte" else "auto")
                    mask_mismatch.append({"level": lv, "text": t, "mode": mode,
                                          "opencv_mask": r.mask, "our_mask": ours.mask,
                                          "identical_with_same_mask": same_mask.matrix == mm})
    print(f"    наші → OpenCV: {classic_ok}/{ours_total} (Aruco {aruco_ok}); "
          f"OpenCV → наші: {theirs_read}/{theirs_total}, ідентичних {identical}")
    return {"available": True, "ours_to_opencv": {"total": ours_total, "classic": classic_ok,
                                                  "aruco": aruco_ok, "any": any_ok,
                                                  "classic_failures": failures},
            "opencv_to_ours": {"total": theirs_total, "read": theirs_read, "identical": identical,
                               "mask_mismatch": mask_mismatch}}


# --------------------------------------------------------------------------- #
#  8. Цілеспрямована зміна: корекція помилок ≠ захист від підробки
# --------------------------------------------------------------------------- #

def exp_forgery() -> dict:
    print("[8] Підміна «PAY 100» → «PAY 900»")
    small, small_changed = analysis.tamper_data_only("PAY 100", "PAY 900", "H", 0)
    small_res = decode(small)
    f = analysis.forge("PAY 100", "PAY 900", "H", 0)
    forged_res = decode(f.matrix)
    fresh = encode("PAY 900", "H", 0)
    fig, axes = plt.subplots(1, 3, figsize=(10.6, 4.3))
    draw_symbol(axes[0], f.original.matrix, "а) оригінал «PAY 100»", border=1)
    draw_symbol(axes[1], small, "б) змінено " + plural(len(small_changed), "модуль", "модулі", "модулів"),
                border=1, highlight=small_changed)
    draw_symbol(axes[2], f.matrix, "в) змінено " + plural(len(f.modules_changed), "модуль", "модулі", "модулів"),
                border=1, highlight=f.modules_changed)
    o1, o2 = _ocv(small), _ocv(f.matrix)
    axes[1].text(10, 22.4, f"декодер: «{small_res.text}», виправлено "
                           + plural(len(small_res.corrected), "слово", "слова", "слів") + "\n"
                           f"OpenCV: «{o1['classic']}»", ha="center", va="top", fontsize=8.2, color=INK_2)
    axes[2].text(10, 22.4, f"декодер: «{forged_res.text}», виправлено "
                           + plural(len(forged_res.corrected), "слово", "слова", "слів") + "\n"
                           f"OpenCV: «{o2['classic']}»", ha="center", va="top", fontsize=8.2, color=S2)
    fig.suptitle("Рисунок 8 — Код Ріда — Соломона повертає оригінал або приймає підробку",
                 fontsize=12, fontweight="semibold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    path = save(fig, "fig8_forgery.png")
    return {
        "figure": path,
        "min_distance": analysis.min_distance("H"), "t": layout.LEVELS["H"].correctable,
        "codewords_differing": f.differing, "codewords_rewritten": f.rewritten,
        "forged_modules_changed": len(f.modules_changed),
        "forged_decoded": forged_res.text, "forged_corrected": forged_res.corrected,
        "forged_opencv": o2,
        "small_modules_changed": len(small_changed),
        "small_codewords_changed": sorted(analysis.codewords_touched(small_changed)),
        "small_decoded": small_res.text, "small_corrected": small_res.corrected,
        "small_opencv": o1,
        "fresh_vs_original_modules": sum(fresh.matrix[r][c] != f.original.matrix[r][c]
                                         for r in range(21) for c in range(21)),
    }


# --------------------------------------------------------------------------- #
#  9. Дві мови: час kata-декодера
# --------------------------------------------------------------------------- #

def exp_platform(quick: bool) -> dict:
    print("[9] Порівняння реалізацій: C# і Python")
    import importlib.util
    spec = importlib.util.spec_from_file_location("sol", ROOT / "solution" / "codewars_solution.py")
    sol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sol)
    matrices = [_matrix(c) for c in CASES]
    valid = [_matrix(c) for c in CASES if c["standard_valid"]]

    def bench(fn, items, n, repeats=5):
        samples = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            for i in range(n):
                fn(items[i % len(items)])
            samples.append((time.perf_counter() - t0) * 1e9 / n)
        samples.sort()
        return {"median_ns": samples[len(samples) // 2], "all_ns": samples, "n": n}

    n = 2000 if quick else 20000
    py_solution = bench(sol.scanner, matrices, n)
    py_kata = bench(kata_scan, matrices, n)
    py_full = bench(decode, valid, n // 4)
    damaged = []
    rng = random.Random(SEED)
    for m in valid:
        damaged.append(analysis.flip_modules(m, rng.sample(layout.DATA_POSITIONS, 30)))
    py_full_damaged = bench(lambda m: analysis.full_text(m), damaged, n // 4)

    cs = None
    if shutil.which("dotnet"):
        proc = subprocess.run(["dotnet", "run", "-c", "Release", "--project",
                               str(ROOT / "csharp" / "QrScanner"), "--", "bench",
                               str(20000 if quick else 200000)],
                              capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
                              timeout=600)
        if proc.returncode == 0:
            cs = json.loads(proc.stdout.strip().splitlines()[-1])
    platform_results = json.loads((RES / "platform_results.json").read_text(encoding="utf-8"))

    labels, values, colors = [], [], []
    if cs:
        labels.append("C#: Scanner\n(розв’язок kata)")
        values.append(cs["ns_per_scan_median"] / 1000)
        colors.append(S4)
    for lab, res, col in (("Python: scanner\n(розв’язок kata)", py_solution, S1),
                          ("Python: повний\nдекодер, без помилок", py_full, S3),
                          ("Python: повний\nдекодер, 30 інверсій", py_full_damaged, S2)):
        labels.append(lab)
        values.append(res["median_ns"] / 1000)
        colors.append(col)
    fig, ax = plt.subplots(figsize=(8.4, 3.8))
    bars = ax.bar(range(len(values)), values, color=colors, width=0.6)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.12, _n(v, 1) + " мкс", ha="center",
                va="bottom", fontsize=8.5)
    ax.set_yscale("log")
    ax.set_xticks(range(len(values)), labels, fontsize=8.5)
    ax.set_ylabel("мікросекунд на один символ")
    ax.set_ylim(min(values) / 2, max(values) * 4)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    fig.suptitle("Рисунок 9 — Час декодування одного символу (медіана п’яти повторів)",
                 fontsize=12, fontweight="semibold")
    cpu = cpu_name()
    _finish(ax, f"{cpu}; Python {platform.python_version()}"
                + (f"; .NET {cs['dotnet']}, збірка Release" if cs else ""), note_y=-0.24)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    path = save(fig, "fig9_platform.png")
    return {"figure": path, "python_solution": py_solution, "python_kata_scan": py_kata,
            "python_full_decode": py_full, "python_full_decode_damaged": py_full_damaged,
            "csharp": cs, "codewars": platform_results["runs"],
            "machine": {"python": platform.python_version(), "platform": platform.platform(),
                        "processor": cpu}}


def capacity_table() -> dict:
    return {name: {"data": lv.data_codewords, "ecc": lv.ecc_codewords, "t": lv.correctable,
                   "p": lv.reserve, "numeric": capacity(name, "numeric"),
                   "alphanumeric": capacity(name, "alphanumeric"), "byte": capacity(name, "byte")}
            for name, lv in layout.LEVELS.items()}


# --------------------------------------------------------------------------- #

def write_summary(results: dict) -> None:
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "experiments.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    L = ["# Зведені результати експериментів", "",
         "Згенеровано автоматично: `python experiments/run_experiments.py`", "",
         "## Пробні матриці Codewars", "",
         "| Джерело | Тест | Очікувано | kata | Повний декодер | OpenCV |", "|---|---|---|---|---|---|"]
    for r in results["samples"]["cases"]:
        L.append(f"| {r['source']} | {r['test']} | {r['expected']} | {r['kata']} | "
                 f"{r['full'] or 'не виправлено'} | {r['opencv']['classic'] or 'не прочитано'} |")
    L += ["", "## Місткість версії 1", "", "| Рівень | Дані | Корекція | t | p | Цифри | Букв.-цифр. | Байти |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, c in results["capacity"].items():
        L.append(f"| {name} | {c['data']} | {c['ecc']} | {c['t']} | {c['p']} | {c['numeric']} | "
                 f"{c['alphanumeric']} | {c['byte']} |")
    L += ["", "## Випадкові інверсії (точні ймовірності успіху, «Warrior»)", "",
          "| k | kata | L | M | Q | H |", "|---:|---:|---:|---:|---:|---:|"]
    ex = results["random_errors"]
    for k in (2, 4, 8, 12, 16, 20, 30, 40):
        i = ex["k"].index(k)
        L.append(f"| {k} | " + " | ".join(f"{ex['exact'][n][i]:.4f}" for n in ("kata", "L", "M", "Q", "H")) + " |")
    L += ["", "## Плями (рівень H)", "", "| s | помилки | стирання | слів зачеплено |", "|---:|---:|---:|---:|"]
    for r in results["blocks"]["sides"]:
        L.append(f"| {r['side']} | {r['errors']['correct'] / r['trials']:.3f} | "
                 f"{r['erasures']['correct'] / r['trials']:.3f} | {r['touched_mean']:.2f} |")
    fg = results["forgery"]
    L += ["", "## Підміна «PAY 100» → «PAY 900»", "",
          f"- змінено лише інформаційні слова: {fg['small_modules_changed']} модулів → декодер повернув «{fg['small_decoded']}»",
          f"- цілеспрямована підробка: переписано {len(fg['codewords_rewritten'])} слів, "
          f"{fg['forged_modules_changed']} модулів → декодер прочитав «{fg['forged_decoded']}»"]
    (RES / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n    зведення -> docs/results/summary.md")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    rng = random.Random(SEED)
    t0 = time.perf_counter()
    results = {
        "seed": SEED,
        "quick": args.quick,
        "anatomy": exp_anatomy(),
        "samples": exp_samples(),
        "csharp_diff": exp_csharp_diff(),
        "random_errors": exp_random_errors(rng, args.quick),
        "miscorrection": exp_miscorrection(),
        "blocks": exp_blocks(rng, args.quick),
        "masks": exp_masks(),
        "interop": exp_interop(),
        "forgery": exp_forgery(),
        "capacity": capacity_table(),
        "platform": exp_platform(args.quick),
    }
    results["elapsed_s"] = round(time.perf_counter() - t0, 1)
    write_summary(results)
    print(f"готово за {results['elapsed_s']} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
