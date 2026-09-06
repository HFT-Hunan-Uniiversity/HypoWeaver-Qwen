"""Command-line entry point for dependency-free coverage semantic validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

try:
    from .validator import validate_certificate, validate_file
except ImportError:  # Direct execution: python src/coverage/validate_coverage_certificate.py
    from validator import validate_certificate, validate_file


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate coverage-certificate arithmetic and cross-field semantics. "
            "Run JSON Schema validation separately for structure."
        )
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="certificate JSON file(s); use - to read one certificate from stdin",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="emit one machine-readable JSON result array",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    results: list[dict[str, object]] = []
    all_valid = True
    for path in args.files:
        if str(path) == "-":
            try:
                certificate = json.load(sys.stdin)
            except (UnicodeError, json.JSONDecodeError) as exc:
                errors = [f"cannot read JSON certificate from stdin: {exc}"]
            else:
                errors = validate_certificate(certificate)
        else:
            _, errors = validate_file(path)
        valid = not errors
        all_valid = all_valid and valid
        results.append({"path": str(path), "valid": valid, "errors": errors})

    if args.json_output:
        json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for result in results:
            status = "VALID" if result["valid"] else "INVALID"
            print(f"{status} {result['path']}")
            for error in result["errors"]:
                print(f"  - {error}")
    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
