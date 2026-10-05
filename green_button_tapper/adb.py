"""Thin wrapper around the `adb` command-line tool.

Only plain adb/shell commands are used (am, cmd package, screencap, input):
no Appium, uiautomator or other UI-automation frameworks.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

log = logging.getLogger(__name__)

DEFAULT_COMMAND_TIMEOUT = 5.0

# Android package name: at least two dot-separated segments, each starting with a letter.
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")

# e.g. "mCurrentFocus=Window{1a2b3c u0 com.example.app/com.example.app.MainActivity}"
#      "mFocusedApp=ActivityRecord{4d5e6f u0 com.example.app/.MainActivity t42}"
_FOCUS_RE = re.compile(r"\b(?:mCurrentFocus|mFocusedApp)=.*?\s([A-Za-z][\w.]*)/")


class AdbError(RuntimeError):
    """Any failure while talking to the device through adb."""


def is_valid_package_name(name: str) -> bool:
    return bool(PACKAGE_RE.match(name))


class Adb:
    def __init__(self, serial: str | None = None, adb_path: str = "adb") -> None:
        resolved = shutil.which(adb_path)
        if resolved is None:
            raise AdbError(
                f"Не найден исполняемый файл adb ('{adb_path}'). "
                "Установите Android platform-tools и добавьте их в PATH."
            )
        self._adb = resolved
        self._serial = serial

    # ------------------------------------------------------------------ low level

    def _run(self, *args: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> bytes:
        cmd = [self._adb]
        if self._serial:
            cmd += ["-s", self._serial]
        cmd += list(args)
        log.debug("$ %s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=max(timeout, 0.1), check=False)
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"Команда adb не завершилась за {timeout:.1f} c: {' '.join(args)}") from exc
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise AdbError(f"adb {' '.join(args)} завершилась с кодом {result.returncode}: {stderr}")
        return result.stdout

    def shell(self, command: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> str:
        return self._run("shell", command, timeout=timeout).decode(errors="replace")

    # ------------------------------------------------------------------ device

    def ensure_device(self, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> None:
        """Fail fast with a clear message if no (authorized) device is reachable."""
        try:
            state = self._run("get-state", timeout=timeout).decode().strip()
        except AdbError as exc:
            raise AdbError(
                "Устройство не найдено. Проверьте подключение, включённую отладку по USB "
                "и вывод `adb devices` (при нескольких устройствах укажите --serial)."
                f"\nДетали: {exc}"
            ) from exc
        if state != "device":
            raise AdbError(f"Устройство в состоянии '{state}', ожидалось 'device'.")

    # ------------------------------------------------------------------ apps

    def is_package_installed(self, package: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> bool:
        # `pm path` prints "package:/data/app/..." for installed packages and nothing otherwise.
        try:
            output = self.shell(f"pm path {package}", timeout=timeout)
        except AdbError:
            return False
        return "package:" in output

    def resolve_launch_activity(self, package: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> str | None:
        """Return "pkg/.Activity" of the launcher activity, or None if it can't be resolved."""
        try:
            output = self.shell(
                f"cmd package resolve-activity --brief -a android.intent.action.MAIN "
                f"-c android.intent.category.LAUNCHER {package}",
                timeout=timeout,
            )
        except AdbError:
            return None  # `cmd package` is unavailable on very old Android versions
        for line in reversed(output.splitlines()):
            line = line.strip()
            if line.startswith(f"{package}/"):
                return line
        return None

    def launch_app(self, package: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> None:
        component = self.resolve_launch_activity(package, timeout=timeout)
        if component:
            output = self.shell(f"am start -n {component}", timeout=timeout)
            # `am start` exits with 0 even on failure, so the output has to be checked.
            if "Error" in output or "Exception" in output:
                raise AdbError(f"Не удалось запустить {component}: {output.strip()}")
            log.debug("Started %s", component)
            return

        # Fallback: ask the system to fire the LAUNCHER intent for the package.
        output = self.shell(
            f"monkey -p {package} -c android.intent.category.LAUNCHER 1", timeout=timeout
        )
        if "No activities found" in output or "aborted" in output.lower():
            raise AdbError(f"У пакета {package} нет запускаемой (LAUNCHER) activity.")
        log.debug("Started %s via monkey", package)

    def force_stop(self, package: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> None:
        self.shell(f"am force-stop {package}", timeout=timeout)

    def foreground_package(self, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> str | None:
        """Package of the currently focused window, or None if it can't be determined."""
        try:
            output = self.shell(
                "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'", timeout=timeout
            )
        except AdbError:
            return None
        return parse_foreground_package(output)

    # ------------------------------------------------------------------ screen

    def screenshot_png(self, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> bytes:
        # exec-out returns raw binary stdout (`shell` may mangle line endings on old devices).
        data = self._run("exec-out", "screencap", "-p", timeout=timeout)
        if not data.startswith(b"\x89PNG"):
            raise AdbError("screencap вернул не PNG-изображение (экран защищён FLAG_SECURE?).")
        return data

    def tap(self, x: int, y: int, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> None:
        self.shell(f"input tap {x} {y}", timeout=timeout)


def parse_foreground_package(dumpsys_output: str) -> str | None:
    for line in dumpsys_output.splitlines():
        match = _FOCUS_RE.search(line)
        if match:
            return match.group(1)
    return None
