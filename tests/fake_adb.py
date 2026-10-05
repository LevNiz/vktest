#!/usr/bin/env python3
"""Minimal stand-in for the `adb` binary, used by the end-to-end tests.

Emulates a device with one installed package (com.example.app) whose screen
is the PNG at $FAKE_ADB_SCREEN. Every invocation is appended to $FAKE_ADB_LOG.
"""

import os
import sys

PKG = "com.example.app"

args = sys.argv[1:]
if args[:1] == ["-s"]:
    args = args[2:]

with open(os.environ["FAKE_ADB_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")

match args:
    case ["get-state"]:
        print("device")
    case ["exec-out", "screencap", "-p"]:
        with open(os.environ["FAKE_ADB_SCREEN"], "rb") as f:
            sys.stdout.buffer.write(f.read())
    case ["shell", cmd]:
        if cmd == f"pm path {PKG}":
            print(f"package:/data/app/{PKG}/base.apk")
        elif cmd.startswith("cmd package resolve-activity") and cmd.endswith(PKG):
            print("priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true")
            print(f"{PKG}/.MainActivity")
        elif cmd.startswith("am start"):
            print(f"Starting: Intent {{ cmp={PKG}/.MainActivity }}")
        elif cmd.startswith("dumpsys window"):
            print(f"  mCurrentFocus=Window{{1a2b3c u0 {PKG}/{PKG}.MainActivity}}")
        elif cmd.startswith(("input tap", "pm path")):
            pass
        else:
            sys.exit(f"fake adb: unsupported shell command: {cmd}")
    case _:
        sys.exit(f"fake adb: unsupported command: {args}")
