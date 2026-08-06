#!/usr/bin/env python3
"""Fail-closed tombstone for the removed unsafe phase recovery helper."""
import json
import sys


def main() -> None:
    result = {
        "error": (
            "recover_phase.py is disabled and never stages, commits, or pushes. "
            "Inspect records with coding_harness.py status/show, repair or continue "
            "through the normal full-plan workflow, and use approval-gated "
            "finalize-plan only after the complete plan is green."
        ),
        "error_type": "DisabledUnsafeHelper",
        "mutated": False,
    }
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
