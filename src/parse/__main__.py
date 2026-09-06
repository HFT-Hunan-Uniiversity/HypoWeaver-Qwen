"""Command-line entry point for ``python -m src.parse``."""

from .jats import main


if __name__ == "__main__":
    raise SystemExit(main())
