#!/usr/bin/env python3
"""Thin Telegram-facing Cortex dispatcher entrypoint.

This wrapper keeps transport wiring independent from OpenClaw runtime setup.
It defaults dispatch profile to v1.5 unless explicitly overridden.
"""

from __future__ import annotations

import os
import runpy
from pathlib import Path


HERE = Path(__file__).resolve().parent
TARGET = HERE / "openclaw_agi_dispatch.py"


def main() -> int:
    os.environ.setdefault("CORTEX_DISPATCH_PROFILE", "v15")
    runpy.run_path(str(TARGET), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

