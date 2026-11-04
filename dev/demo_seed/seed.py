"""Preflight by default; explicitly back up/reset/reseed the Windows host stack."""

import argparse
import sys
from pathlib import Path

from environment import Environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Checkout containing the configured host stack; defaults to this checkout.",
    )
    parser.add_argument(
        "--app-origin",
        default="https://localhost:8443",
        help="Browser origin used in sample logo URLs and local notification links.",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--reset",
        action="store_true",
        help="Stop the host stack, back it up, replace local data, restart and verify.",
    )
    action.add_argument(
        "--verify",
        action="store_true",
        help="Read the APIs to verify the last saved seed; no reset.",
    )
    args = parser.parse_args()
    ctx = Environment(args.root, args.app_origin)
    ctx.preflight()
    if args.verify:
        from verify import verify

        verify(ctx)
        return
    if not args.reset:
        print("Preflight passed. No services stopped and no data/configuration changed.")
        print(
            "Explicit --reset will replace local TeleLink accounts, application "
            "rows, document/branding objects, queues and Redis database 0 after a "
            "validated backup."
        )
        return
    # Import all seed dependencies before stopping anything.
    from coverage import finish
    from dataset import seed
    from verify import verify

    ctx.stop()
    try:
        ctx.take_backup()
    except Exception:
        ctx.start()
        raise
    try:
        seed(ctx)
        finish(ctx)
    except Exception:
        print(
            "Reseed failed; services remain stopped. "
            f"Restore instructions: dev/demo_seed/README.md. Backup: {ctx.backup}",
            file=sys.stderr,
        )
        raise
    ctx.start()
    verify(ctx)
    print(f"Demo reset complete. Sign out and sign in again. Report: {ctx.state / 'README.md'}")


if __name__ == "__main__":
    main()
