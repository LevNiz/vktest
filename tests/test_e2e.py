"""End-to-end: run main.py as a real process against a fake `adb` executable."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import blank_screen, draw_button, to_png

ROOT = Path(__file__).resolve().parent.parent
FAKE_ADB = Path(__file__).resolve().parent / "fake_adb.py"


@pytest.fixture
def run_main(tmp_path):
    log = tmp_path / "adb.log"
    screen = tmp_path / "screen.png"

    def run(image, *extra):
        screen.write_bytes(to_png(image))
        env = {**os.environ, "FAKE_ADB_LOG": str(log), "FAKE_ADB_SCREEN": str(screen)}
        proc = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), *extra, "--adb", str(FAKE_ADB)],
            capture_output=True, text=True, env=env, timeout=30,
        )
        calls = log.read_text().splitlines() if log.exists() else []
        return proc, calls

    return run


def test_button_found_and_tapped(run_main):
    image = draw_button(blank_screen(), 240, 1500, 600, 150, (80, 175, 76), text="CONTINUE")
    proc, calls = run_main(image, "com.example.app")
    assert proc.returncode == 0, proc.stderr
    assert "нажата в точке (540, 1575)" in proc.stdout
    assert "shell am start -n com.example.app/.MainActivity" in calls
    assert calls[-1] == "shell input tap 540 1575"


def test_button_not_found(run_main):
    proc, calls = run_main(blank_screen(), "com.example.app", "--timeout", "1")
    assert proc.returncode == 1, proc.stderr
    assert "Зелёная кнопка не найдена" in proc.stdout
    assert not any("input tap" in c for c in calls)


def test_package_not_installed(run_main):
    proc, _ = run_main(blank_screen(), "com.missing.app")
    assert proc.returncode == 3
    assert "не установлен" in proc.stderr
