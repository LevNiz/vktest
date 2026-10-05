import subprocess
from unittest import mock

import pytest

from green_button_tapper.adb import Adb, AdbError, is_valid_package_name, parse_foreground_package


def completed(stdout=b"", returncode=0, stderr=b""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def adb():
    with mock.patch("shutil.which", return_value="/usr/bin/adb"):
        return Adb(serial="emulator-5554")


@pytest.mark.parametrize("name", ["com.example.app", "org.test.My_App2", "a.b"])
def test_valid_package_names(name):
    assert is_valid_package_name(name)


@pytest.mark.parametrize("name", ["", "app", "com.example;rm -rf /", "1com.app", "com..app", "com.app "])
def test_invalid_package_names(name):
    assert not is_valid_package_name(name)


@pytest.mark.parametrize(
    "output, expected",
    [
        ("  mCurrentFocus=Window{1a2b u0 com.example.app/com.example.app.MainActivity}", "com.example.app"),
        ("  mFocusedApp=ActivityRecord{4d5e u0 com.example.app/.MainActivity t42}", "com.example.app"),
        ("  mCurrentFocus=Window{1a2b u0 NotificationShade}\n"
         "  mFocusedApp=ActivityRecord{4d5e u0 com.android.launcher3/.Launcher t1}", "com.android.launcher3"),
        ("  mCurrentFocus=null", None),
        ("", None),
    ],
)
def test_parse_foreground_package(output, expected):
    assert parse_foreground_package(output) == expected


def test_missing_adb_binary():
    with mock.patch("shutil.which", return_value=None), pytest.raises(AdbError, match="adb"):
        Adb()


def test_serial_is_passed(adb):
    with mock.patch("subprocess.run", return_value=completed(b"device\n")) as run:
        adb.ensure_device()
    assert run.call_args.args[0] == ["/usr/bin/adb", "-s", "emulator-5554", "get-state"]


def test_ensure_device_error(adb):
    with mock.patch("subprocess.run", return_value=completed(returncode=1, stderr=b"no devices")):
        with pytest.raises(AdbError, match="Устройство не найдено"):
            adb.ensure_device()


def test_ensure_device_unauthorized(adb):
    with mock.patch("subprocess.run", return_value=completed(b"unauthorized\n")):
        with pytest.raises(AdbError, match="unauthorized"):
            adb.ensure_device()


def test_command_timeout(adb):
    with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 1)):
        with pytest.raises(AdbError, match="не завершилась"):
            adb.shell("echo")


def test_is_package_installed(adb):
    with mock.patch("subprocess.run", return_value=completed(b"package:/data/app/base.apk\n")):
        assert adb.is_package_installed("com.example.app")
    with mock.patch("subprocess.run", return_value=completed(b"")):
        assert not adb.is_package_installed("com.example.app")


def test_launch_via_resolved_activity(adb):
    responses = [
        completed(b"priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true\n"
                  b"com.example.app/.MainActivity\n"),
        completed(b"Starting: Intent { cmp=com.example.app/.MainActivity }\n"),
    ]
    with mock.patch("subprocess.run", side_effect=responses) as run:
        adb.launch_app("com.example.app")
    assert run.call_args.args[0][-1] == "am start -n com.example.app/.MainActivity"


def test_launch_reports_am_error(adb):
    responses = [
        completed(b"com.example.app/.MainActivity\n"),
        completed(b"Error: Activity class {com.example.app/.MainActivity} does not exist.\n"),
    ]
    with mock.patch("subprocess.run", side_effect=responses), pytest.raises(AdbError):
        adb.launch_app("com.example.app")


def test_launch_falls_back_to_monkey(adb):
    responses = [
        completed(b"No activity found\n"),
        completed(b"Events injected: 1\n"),
    ]
    with mock.patch("subprocess.run", side_effect=responses) as run:
        adb.launch_app("com.example.app")
    assert run.call_args.args[0][-1].startswith("monkey -p com.example.app")


def test_launch_without_launcher_activity(adb):
    responses = [
        completed(b"No activity found\n"),
        completed(b"** No activities found to run, monkey aborted.\n"),
    ]
    with mock.patch("subprocess.run", side_effect=responses), pytest.raises(AdbError, match="LAUNCHER"):
        adb.launch_app("com.example.app")


def test_screenshot_must_be_png(adb):
    with mock.patch("subprocess.run", return_value=completed(b"\x89PNG\r\n...")):
        assert adb.screenshot_png().startswith(b"\x89PNG")
    with mock.patch("subprocess.run", return_value=completed(b"")):
        with pytest.raises(AdbError):
            adb.screenshot_png()


def test_tap(adb):
    with mock.patch("subprocess.run", return_value=completed()) as run:
        adb.tap(540, 1575)
    assert run.call_args.args[0][-2:] == ["shell", "input tap 540 1575"]
