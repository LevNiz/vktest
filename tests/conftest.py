import cv2
import numpy as np
import pytest

SCREEN_W, SCREEN_H = 1080, 2400


def blank_screen(color_bgr=(255, 255, 255)) -> np.ndarray:
    img = np.zeros((SCREEN_H, SCREEN_W, 3), dtype=np.uint8)
    img[:] = color_bgr
    return img


def draw_button(img, x, y, w, h, color_bgr, text="OK"):
    cv2.rectangle(img, (x, y), (x + w, y + h), color_bgr, thickness=-1)
    cv2.putText(img, text, (x + w // 4, y + h // 2 + 15), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
    return img


def to_png(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


@pytest.fixture
def screen():
    return blank_screen()
