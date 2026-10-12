.PHONY: setup dev test build
setup:
	cd backend && uv sync
	cd frontend && npm ci
dev:
	python3 scripts/dev.py
test:
	cd backend && uv run pytest -q
build:
	cd frontend && npm run build
