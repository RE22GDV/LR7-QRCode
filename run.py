#!/usr/bin/env python3
"""Запуск без встановлення пакета: ``python run.py <команда>``."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from qrv1.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
