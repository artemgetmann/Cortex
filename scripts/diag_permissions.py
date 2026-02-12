#!/usr/bin/env python3
"""Diagnose whether this exact Python process can inject input on macOS."""

from __future__ import annotations

import os
import platform
import subprocess
import sys

from ApplicationServices import AXIsProcessTrusted  # type: ignore
from Quartz import (  # type: ignore
    CGPreflightListenEventAccess,
    CGPreflightPostEventAccess,
    CGPreflightScreenCaptureAccess,
)


def _parent_command() -> str:
    ppid = os.getppid()
    try:
        result = subprocess.run(
            ["ps", "-o", "command=", "-p", str(ppid)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            cmd = result.stdout.strip()
            if cmd:
                return cmd
        return f"(ps failed: rc={result.returncode}, stderr={result.stderr.strip()})"
    except Exception as exc:
        return f"(ps unavailable: {exc})"


def main() -> int:
    post = bool(CGPreflightPostEventAccess())
    listen = bool(CGPreflightListenEventAccess())
    screen = bool(CGPreflightScreenCaptureAccess())
    ax = bool(AXIsProcessTrusted())

    print("═══ macOS Automation Permission Diagnostic ═══")
    print(f"Platform: {platform.platform()}")
    print(f"PID:      {os.getpid()}")
    print(f"PPID:     {os.getppid()}")
    print(f"Python:   {sys.executable}")
    print(f"Parent:   {_parent_command()}")
    print("")
    print(f"Screen capture access: {screen}")
    print(f"Post events access:    {post}")
    print(f"Listen events access:  {listen}")
    print(f"Accessibility (AX):    {ax}")

    if post and ax:
        print("\n✅ This process should be able to send keyboard/mouse events.")
        return 0

    print("\n❌ This process is NOT trusted for input injection.")
    print("Fix checklist:")
    print("1) System Settings -> Privacy & Security -> Accessibility")
    print("2) Enable your terminal/IDE app (Terminal, iTerm, VS Code, Alacritty, etc.)")
    print("3) If still failing, also add this exact Python binary:")
    print(f"   {sys.executable}")
    print("4) Fully quit/reopen both terminal app and FL Studio")
    print("5) Re-run this script from the same shell you'll use for the agent")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
