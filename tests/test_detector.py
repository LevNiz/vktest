import cv2
import pytest

from green_button_tapper.detector import decode_png, find_green_button, find_green_buttons

from .conftest import blank_screen, draw_button, to_png

MATERIAL_GREEN = (80, 175, 76)  # #4CAF50 in BGR
DARK_GREEN = (60, 142, 56)      # #388E3C
LIME_GREEN = (74, 195, 139)     # #8BC34A
PURE_GREEN = (0, 255, 0)


@pytest.mark.parametrize("color", [MATERIAL_GREEN, DARK_GREEN, LIME_GREEN, PURE_GREEN])
def test_finds_green_button_with_text(screen, color):
    draw_button(screen, 240, 1500, 600, 150, color)
    button = find_green_button(screen)
    assert button is not None
    assert button.center == pytest.approx((540, 1575), abs=3)


@pytest.mark.parametrize(
    "color",
    [(243, 150, 33), (54, 67, 244), (0, 152, 255), (128, 128, 128), (0, 0, 0), (200, 230, 200)],
    ids=["blue", "red", "orange", "gray", "black", "pale-green"],
)
def test_ignores_non_green_buttons(screen, color):
    draw_button(screen, 240, 1500, 600, 150, color)
    assert find_green_button(screen) is None


def test_empty_screen(screen):
    assert find_green_button(screen) is None


def test_ignores_small_green_icon(screen):
    cv2.circle(screen, (60, 40), 12, PURE_GREEN, -1)  # e.g. a status-bar indicator
    assert find_green_button(screen) is None


def test_ignores_green_background():
    assert find_green_button(blank_screen(MATERIAL_GREEN)) is None


def test_ignores_thin_green_line(screen):
    cv2.rectangle(screen, (0, 800), (1080, 806), MATERIAL_GREEN, -1)
    assert find_green_button(screen) is None


def test_ignores_green_outline_only(screen):
    cv2.rectangle(screen, (240, 1500), (840, 1650), MATERIAL_GREEN, thickness=8)
    assert find_green_button(screen) is None


def test_finds_round_fab(screen):
    cv2.circle(screen, (900, 2100), 90, MATERIAL_GREEN, -1)
    button = find_green_button(screen)
    assert button is not None
    assert button.center == pytest.approx((900, 2100), abs=3)


def test_picks_largest_of_several(screen):
    draw_button(screen, 100, 300, 300, 120, MATERIAL_GREEN)
    draw_button(screen, 100, 1200, 800, 180, MATERIAL_GREEN)
    buttons = find_green_buttons(screen)
    assert len(buttons) == 2
    assert buttons[0].center == pytest.approx((500, 1290), abs=3)


def test_green_among_other_colors(screen):
    draw_button(screen, 100, 400, 800, 150, (243, 150, 33))
    draw_button(screen, 100, 800, 800, 150, (54, 67, 244))
    draw_button(screen, 100, 1200, 800, 150, MATERIAL_GREEN)
    button = find_green_button(screen)
    assert button is not None
    assert button.center == pytest.approx((500, 1275), abs=3)


def test_decode_png_roundtrip(screen):
    draw_button(screen, 240, 1500, 600, 150, MATERIAL_GREEN)
    assert find_green_button(decode_png(to_png(screen))) is not None


def test_decode_png_rejects_garbage():
    with pytest.raises(ValueError):
        decode_png(b"not a png")
