#!/usr/bin/env python3
"""Diagnose: does this process have CGEvent posting permission?

If False — confirms Alacritty child-process permission bug.
If True  — permission exists but events are still dropped (different issue).
"""
from Quartz import (
    CGPreflightPostEventAccess,
    CGPreflightListenEventAccess,
)

post = CGPreflightPostEventAccess()
listen = CGPreflightListenEventAccess()

print(f"Post events:   {post}")
print(f"Listen events: {listen}")

if not post:
    print("\n⚠️  Post access DENIED — Alacritty permission bug confirmed.")
    print("   Fix: run from Terminal.app or SSH session instead.")
elif not listen:
    print("\n⚠️  Listen access DENIED (post OK) — unusual.")
else:
    print("\n✅ Both permissions granted — events should work.")
    print("   If keys still fail, the issue is elsewhere (PID targeting, etc).")
