"""Entry point: launch an app over adb, find a green button on screen and tap it."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

import cv2

from .adb import DEFAULT_COMMAND_TIMEOUT, Adb, AdbError, is_valid_package_name
from .detector import Button, decode_png, draw_detections, find_green_buttons

log = logging.getLogger("green_button_tapper")

EXIT_TAPPED = 0
EXIT_NOT_FOUND = 1
EXIT_ERROR = 3  # 2 is reserved by argparse for usage errors

DEFAULT_TIMEOUT = 10.0
DEFAULT_POLL_INTERVAL = 0.3
TAP_TIMEOUT = 3.0  # the tap must not be skipped just because the search used up the budget


class Deadline:
    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._end = clock() + seconds

    def remaining(self) -> float:
        return max(0.0, self._end - self._clock())

    def expired(self) -> bool:
        return self.remaining() <= 0

    def cmd_timeout(self) -> float:
        """Per-command timeout: never longer than what is left of the overall budget."""
        return min(DEFAULT_COMMAND_TIMEOUT, self.remaining())


def find_and_tap(
    adb: Adb,
    package: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    restart: bool = False,
    debug_image: Path | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Button | None:
    """Launch `package` and poll the screen until a green button is found and tapped.

    Returns the tapped button, or None if none appeared within `timeout` seconds.
    Raises AdbError for environment problems (no device, no such package, ...).
    """
    deadline = Deadline(timeout, clock)

    adb.ensure_device(timeout=deadline.cmd_timeout())
    if not adb.is_package_installed(package, timeout=deadline.cmd_timeout()):
        raise AdbError(f"Пакет '{package}' не установлен на устройстве.")

    if restart:
        adb.force_stop(package, timeout=deadline.cmd_timeout())
    adb.launch_app(package, timeout=deadline.cmd_timeout())
    log.info("Приложение %s запущено, ищу зелёную кнопку...", package)

    last_frame = None
    attempt = 0
    while not deadline.expired():
        attempt += 1
        try:
            # Don't analyse the launcher / previous app while ours is still starting.
            foreground = adb.foreground_package(timeout=deadline.cmd_timeout())
            if foreground is not None and foreground != package:
                log.debug("Попытка %d: на переднем плане %s, жду %s", attempt, foreground, package)
            else:
                last_frame = decode_png(adb.screenshot_png(timeout=deadline.cmd_timeout()))
                buttons = find_green_buttons(last_frame)
                log.debug("Попытка %d: кандидатов %d", attempt, len(buttons))
                if buttons:
                    button = buttons[0]
                    _save_debug(debug_image, last_frame, buttons)
                    adb.tap(*button.center, timeout=TAP_TIMEOUT)
                    return button
        except (AdbError, ValueError) as exc:
            # Transient failures (e.g. screencap during an activity transition) — just retry.
            log.debug("Попытка %d не удалась: %s", attempt, exc)
        sleep(min(poll_interval, deadline.remaining()))

    if last_frame is not None:
        _save_debug(debug_image, last_frame, [])
    return None


def _save_debug(path: Path | None, frame, buttons: list[Button]) -> None:
    if path is None:
        return
    cv2.imwrite(str(path), draw_detections(frame, buttons))
    log.info("Отладочный скриншот сохранён: %s", path)


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("значение должно быть > 0")
    return number


def _package_name(value: str) -> str:
    if not is_valid_package_name(value):
        raise argparse.ArgumentTypeError(f"'{value}' не похоже на имя Android-пакета (например, com.example.app)")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tap_green_button",
        description="Запускает Android-приложение через ADB, находит на экране зелёную кнопку и нажимает её.",
    )
    parser.add_argument("package", type=_package_name, help="имя пакета приложения, например com.example.app")
    parser.add_argument("-s", "--serial", help="серийный номер устройства (если подключено несколько)")
    parser.add_argument(
        "-t", "--timeout", type=_positive_float, default=DEFAULT_TIMEOUT,
        help=f"общий таймаут в секундах (по умолчанию {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument(
        "--restart", action="store_true",
        help="перед запуском принудительно остановить приложение (am force-stop), чтобы открыть его с начального экрана",
    )
    parser.add_argument("--adb", default="adb", help="путь к исполняемому файлу adb (по умолчанию ищется в PATH)")
    parser.add_argument("--debug-image", type=Path, help="сохранить скриншот с подсвеченной найденной кнопкой")
    parser.add_argument("-v", "--verbose", action="store_true", help="подробный лог")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s" if args.verbose else "%(message)s",
        stream=sys.stderr,
    )

    try:
        adb = Adb(serial=args.serial, adb_path=args.adb)
        button = find_and_tap(
            adb, args.package, timeout=args.timeout, restart=args.restart, debug_image=args.debug_image
        )
    except AdbError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return 130

    if button is None:
        print(f"Зелёная кнопка не найдена в приложении {args.package} за {args.timeout:g} c.")
        return EXIT_NOT_FOUND

    x, y = button.center
    print(f"Зелёная кнопка найдена ({button.width}x{button.height} px) и нажата в точке ({x}, {y}).")
    return EXIT_TAPPED
