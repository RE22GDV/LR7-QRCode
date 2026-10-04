"""
Перехресна перевірка: розв'язок на C# (той самий файл, що й на Codewars)
проти реалізації на Python.

Тести автоматично пропускаються, якщо .NET SDK не встановлено.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from qrv1 import capacity, encode, kata_scan
from qrv1.image import matrix_to_text

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "csharp" / "QrScanner"

dotnet_required = pytest.mark.skipif(shutil.which("dotnet") is None,
                                     reason=".NET SDK не встановлено")


def _run(args: list[str]) -> str:
    proc = subprocess.run(["dotnet", "run", "--project", str(PROJECT), "--"] + args,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.rstrip("\n")


@dotnet_required
def test_csharp_selftest_passes() -> None:
    out = _run(["selftest"])
    assert "пройдено все" in out and "FAIL" not in out
    assert out.count("[OK]") == 9


@dotnet_required
def test_both_implementations_agree_on_random_codes(tmp_path: Path) -> None:
    rng = random.Random(77)
    matrices, texts = [], []
    for _ in range(200):
        level = rng.choice("LMQH")
        length = rng.randint(0, capacity(level, "byte"))
        text = "".join(chr(rng.randint(32, 126)) for _ in range(length))
        matrix = encode(text, level, 0).matrix
        assert kata_scan(matrix) == text
        matrices.append(matrix_to_text(matrix))
        texts.append(text)
    batch = tmp_path / "batch.txt"
    batch.write_text("\n\n".join(matrices) + "\n", encoding="utf-8")
    assert json.loads(_run(["scan-batch", str(batch)])) == texts
