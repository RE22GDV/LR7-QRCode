"""Перетворення матриці на зображення та незалежна перевірка через OpenCV.

Pillow і OpenCV — необов'язкові залежності: ядро кодера й декодера
працює без них. Функції імпортують бібліотеки під час виклику.
"""

from __future__ import annotations

from . import layout

QUIET_ZONE = 4                  # світла рамка навколо символу за стандартом


def to_pixels(matrix, scale: int = 10, border: int = QUIET_ZONE):
    """Масив numpy uint8: 0 — темний модуль, 255 — світлий."""
    import numpy as np

    a = np.array(matrix, dtype=np.uint8)
    a = np.pad(a, border)
    img = np.where(a == 1, 0, 255).astype(np.uint8)
    return np.kron(img, np.ones((scale, scale), dtype=np.uint8))


def save_png(matrix, path, scale: int = 10, border: int = QUIET_ZONE) -> None:
    from PIL import Image

    Image.fromarray(to_pixels(matrix, scale, border)).save(path)


def opencv_available() -> bool:
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return True


def opencv_decode(matrix, scale: int = 10, detector: str = "classic") -> str | None:
    """Прочитати матрицю детектором OpenCV; None — код не прочитано.

    ``detector``: ``classic`` — cv2.QRCodeDetector, ``aruco`` —
    cv2.QRCodeDetectorAruco (інший алгоритм пошуку символу на зображенні).
    """
    import cv2

    engine = cv2.QRCodeDetectorAruco() if detector == "aruco" else cv2.QRCodeDetector()
    text, points, _ = engine.detectAndDecode(to_pixels(matrix, scale))
    if points is None or text == "":
        return None
    return text


def opencv_encode(text: str, level: str = "H", mode: str = "byte") -> list[list[int]]:
    """Матриця 21 × 21, згенерована кодером OpenCV (незалежна реалізація)."""
    import cv2

    params = cv2.QRCodeEncoder_Params()
    params.version = 1
    params.correction_level = getattr(cv2, f"QRCodeEncoder_CORRECT_LEVEL_{level}")
    params.mode = getattr(cv2, f"QRCodeEncoder_MODE_{mode.upper()}")
    img = cv2.QRCodeEncoder.create(params).encode(text)
    border = (img.shape[0] - layout.SIZE) // 2
    if img.shape[0] - 2 * border != layout.SIZE:
        raise ValueError(f"OpenCV створив символ {img.shape}, а не версію 1")
    core = img[border:border + layout.SIZE, border:border + layout.SIZE]
    return [[1 if v < 128 else 0 for v in row] for row in core.tolist()]


def matrix_from_text(text: str) -> list[list[int]]:
    """Матриця з рядків «0/1» або «#/.» (порожні рядки й пробіли ігноруються)."""
    rows = []
    for line in text.splitlines():
        cells = [ch for ch in line if ch in "01#."]
        if cells:
            rows.append([1 if ch in "1#" else 0 for ch in cells])
    return rows


def matrix_to_text(matrix, dark: str = "#", light: str = ".") -> str:
    return "\n".join("".join(dark if v else light for v in row) for row in matrix)
