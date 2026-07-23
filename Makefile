.PHONY: help sync init-db run clean

# Default target: show help menu
all: help

help:
	@echo "Available commands:"
	@echo "  make sync      - Install and sync virtual environment packages using uv"
	@echo "  make init-db   - Check/create database and build database tables"
	@echo "  make run       - Launch FastAPI application dev server with auto-reload"
	@echo "  make clean     - Remove virtual environment (.venv) and byte caches"

# Sync virtualenv packages
sync:
	uv sync

# Run database setup and create tables
init-db:
	uv run python init_db.py

# Start FastAPI application server
run:
	uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Clean build and temporary cache files
clean:
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
