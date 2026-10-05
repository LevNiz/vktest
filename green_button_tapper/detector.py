"""Computer-vision search for a green button on a screenshot.

Algorithm:
1. Convert the frame to HSV and keep pixels whose hue is green and which are
   saturated/bright enough (this drops white, gray, black and pale tints).
2. Close small gaps (anti-aliasing, text glyphs on the button) with morphology.
3. Take external contours and keep only "button-like" ones: not too small
   (icons, status-bar indicators), not too large (green backgrounds), solid
   (share of green pixels in the bounding box) and with a sane aspect ratio.
4. The biggest remaining candidate is the button.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class DetectorConfig:
    # OpenCV hue is 0..179 (degrees / 2). 35..85 ≈ 70°..170°: yellow-green to green-cyan.
    hue_min: int = 35
    hue_max: int = 85
    saturation_min: int = 80
    value_min: int = 60
    # Size limits relative to the screen.
    min_width_ratio: float = 0.04
    min_height_ratio: float = 0.015
    max_area_ratio: float = 0.40
    # Share of green pixels inside the bounding box: a filled rounded rectangle ≈ 0.9,
    # a circle (FAB) ≈ 0.785, minus the label text. Rejects outlines and sparse clutter.
    min_fill_ratio: float = 0.5
    max_aspect_ratio: float = 15.0


@dataclass(frozen=True)
class Button:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    @property
    def area(self) -> int:
        return self.width * self.height


def decode_png(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Не удалось декодировать скриншот")
    return image


def green_mask(image_bgr: np.ndarray, config: DetectorConfig = DetectorConfig()) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    lower = np.array([config.hue_min, config.saturation_min, config.value_min], dtype=np.uint8)
    upper = np.array([config.hue_max, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)   # remove speckle noise
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # heal edges / gaps
    return mask


def find_green_buttons(image_bgr: np.ndarray, config: DetectorConfig = DetectorConfig()) -> list[Button]:
    """All button-like green regions, largest first."""
    img_h, img_w = image_bgr.shape[:2]
    screen_area = img_h * img_w
    mask = green_mask(image_bgr, config)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    buttons: list[Button] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < img_w * config.min_width_ratio or h < img_h * config.min_height_ratio:
            continue
        if w * h > screen_area * config.max_area_ratio:
            continue
        if max(w, h) / min(w, h) > config.max_aspect_ratio:
            continue
        if cv2.countNonZero(mask[y : y + h, x : x + w]) / (w * h) < config.min_fill_ratio:
            continue
        buttons.append(Button(x, y, w, h))

    buttons.sort(key=lambda b: b.area, reverse=True)
    return buttons


def find_green_button(image_bgr: np.ndarray, config: DetectorConfig = DetectorConfig()) -> Button | None:
    buttons = find_green_buttons(image_bgr, config)
    return buttons[0] if buttons else None


def draw_detections(image_bgr: np.ndarray, buttons: list[Button]) -> np.ndarray:
    """Copy of the frame with candidates outlined (chosen one in red) — for debugging."""
    out = image_bgr.copy()
    for i, b in enumerate(buttons):
        color = (0, 0, 255) if i == 0 else (255, 0, 0)
        cv2.rectangle(out, (b.x, b.y), (b.x + b.width, b.y + b.height), color, 4)
        cv2.drawMarker(out, b.center, color, cv2.MARKER_CROSS, 40, 4)
    return out
