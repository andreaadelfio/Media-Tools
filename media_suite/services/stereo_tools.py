from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


def translate_image(image: np.ndarray, dx: int, dy: int) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )


def blend(img_a: np.ndarray, img_b: np.ndarray, alpha: float = 0.5, mode: str = "alpha") -> np.ndarray:
    if mode == "alpha":
        return cv2.addWeighted(img_a, alpha, img_b, 1 - alpha, 0)
    if mode == "add":
        return cv2.add(img_a, img_b)
    if mode == "diff":
        return cv2.absdiff(img_a, img_b)
    raise ValueError("mode non valido")


def parse_point(raw_point: str) -> tuple[int, int]:
    parts = [segment.strip() for segment in raw_point.split(",")]
    if len(parts) != 2:
        raise ValueError("Il punto deve avere formato x,y")
    return int(parts[0]), int(parts[1])


def create_overlay(
    left_path: Path,
    right_path: Path,
    left_point: tuple[int, int],
    right_point: tuple[int, int],
    output_dir: Path,
    mode: str = "alpha",
    alpha: float = 0.5,
) -> dict:
    img_left = cv2.imread(str(left_path), cv2.IMREAD_COLOR)
    img_right = cv2.imread(str(right_path), cv2.IMREAD_COLOR)
    if img_left is None or img_right is None:
        raise ValueError("Immagine sinistra o destra non leggibile.")
    if img_left.shape[:2] != img_right.shape[:2]:
        img_right = cv2.resize(img_right, (img_left.shape[1], img_left.shape[0]), interpolation=cv2.INTER_LINEAR)

    dx = left_point[0] - right_point[0]
    dy = left_point[1] - right_point[1]
    aligned = translate_image(img_right, dx, dy)
    blended = blend(img_left, aligned, alpha=alpha, mode=mode)

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"overlay_{timestamp}.png"
    cv2.imwrite(str(output_path), blended)
    return {"output": str(output_path), "translation": {"dx": dx, "dy": dy}}
