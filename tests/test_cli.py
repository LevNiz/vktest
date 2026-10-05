from unittest import mock

import pytest

from green_button_tapper import cli
from green_button_tapper.adb import AdbError

from .conftest import blank_screen, draw_button, to_png

PKG = "com.example.app"


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeAdb:
    """Simulates a device: `frames` are returned by successive screenshots."""

    def __init__(self, frames, *, installed=True, foreground=None, clock=None):
        self.frames = list(frames)
        self.installed = installed
        self.foreground = foreground or [PKG]
        self.clock = clock
        self.taps = []
        self.launched = []
        self.stopped = []

    def ensure_device(self, timeout):
        pass

    def is_package_installed(self, package, timeout):
        return self.installed

    def force_stop(self, package, timeout):
        self.stopped.append(package)

    def launch_app(self, package, timeout):
        self.launched.append(package)

    def foreground_package(self, timeout):
        return self.foreground.pop(0) if len(self.foreground) > 1 else self.foreground[0]

    def screenshot_png(self, timeout):
        if self.clock:
            self.clock.now += 0.2  # screencap is not instantaneous
        frame = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
        if isinstance(frame, Exception):
            raise frame
        return frame

    def tap(self, x, y, timeout):
        self.taps.append((x, y))


def green_frame():
    return to_png(draw_button(blank_screen(), 240, 1500, 600, 150, (80, 175, 76)))


def empty_frame():
    return to_png(blank_screen())


def run(adb, clock, **kwargs):
    return cli.find_and_tap(adb, PKG, clock=clock, sleep=clock.sleep, **kwargs)


def test_taps_button_immediately():
    clock = FakeClock()
    adb = FakeAdb([green_frame()], clock=clock)
    button = run(adb, clock)
    assert button is not None
    assert adb.launched == [PKG]
    assert adb.taps == [(540, 1575)]


def test_waits_for_button_to_appear():
    clock = FakeClock()
    adb = FakeAdb([empty_frame(), empty_frame(), AdbError("transient"), green_frame()], clock=clock)
    assert run(adb, clock) is not None
    assert len(adb.taps) == 1
    assert clock.now < 10


def test_skips_frames_while_app_is_not_in_foreground():
    clock = FakeClock()
    adb = FakeAdb([green_frame()], foreground=["com.android.launcher3", "com.android.launcher3", PKG], clock=clock)
    assert run(adb, clock) is not None
    assert len(adb.frames) == 1  # screenshot was taken only once our app had focus


def test_not_found_respects_timeout():
    clock = FakeClock()
    adb = FakeAdb([empty_frame()], clock=clock)
    assert run(adb, clock, timeout=10) is None
    assert adb.taps == []
    assert 10 <= clock.now < 10.5


def test_package_not_installed():
    clock = FakeClock()
    adb = FakeAdb([green_frame()], installed=False, clock=clock)
    with pytest.raises(AdbError, match="не установлен"):
        run(adb, clock)
    assert adb.launched == []


def test_restart_force_stops_first():
    clock = FakeClock()
    adb = FakeAdb([green_frame()], clock=clock)
    run(adb, clock, restart=True)
    assert adb.stopped == [PKG]


def test_debug_image_is_saved(tmp_path):
    clock = FakeClock()
    path = tmp_path / "debug.png"
    run(FakeAdb([green_frame()], clock=clock), clock, debug_image=path)
    assert path.exists()


# ---------------------------------------------------------------- main()

def test_main_success(capsys):
    with mock.patch.object(cli, "Adb"), mock.patch.object(cli, "find_and_tap") as fat:
        fat.return_value = cli.Button(240, 1500, 600, 150)
        assert cli.main([PKG]) == cli.EXIT_TAPPED
    assert "нажата в точке (540, 1575)" in capsys.readouterr().out


def test_main_not_found(capsys):
    with mock.patch.object(cli, "Adb"), mock.patch.object(cli, "find_and_tap", return_value=None):
        assert cli.main([PKG]) == cli.EXIT_NOT_FOUND
    assert "не найдена" in capsys.readouterr().out


def test_main_adb_error(capsys):
    with mock.patch.object(cli, "Adb", side_effect=AdbError("нет adb")):
        assert cli.main([PKG]) == cli.EXIT_ERROR
    assert "нет adb" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [[], ["not-a-package"], [PKG, "--timeout", "0"]])
def test_main_rejects_bad_arguments(argv):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2
