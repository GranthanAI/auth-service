.PHONY: help sync init-db run clean infra infra-down test get-otp

# Default target: show help menu
all: help

help:
	@echo "Available commands:"
	@echo "  make sync       - Install and sync virtual environment packages using uv"
	@echo "  make infra      - Start local Redis, Zookeeper, and Kafka containers (local PGSQL is used)"
	@echo "  make infra-down - Stop local Redis, Zookeeper, and Kafka containers"
	@echo "  make init-db    - Check/create database and build database tables"
	@echo "  make run        - Launch FastAPI application dev server with auto-reload"
	@echo "  make get-otp    - Get latest active verification OTP for an email (e.g. make get-otp EMAIL=user@example.com)"
	@echo "  make test       - Run unit tests using pytest"
	@echo "  make clean      - Remove virtual environment (.venv) and byte caches"

# Sync virtualenv packages
sync:
	uv sync

# Start docker infrastructure containers (shares Redis/Kafka from conversation-service)
infra:
	docker compose -f ../conversation-service/docker-compose.yml up -d

# Stop docker infrastructure containers
infra-down:
	docker compose -f ../conversation-service/docker-compose.yml down

# Run database setup and create tables
init-db:
	uv run python init_db.py

# Start FastAPI application server
run:
	uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# Retrieve active OTP code for testing
get-otp:
	uv run python get_otp.py --email $(or $(EMAIL),testuser@example.com)

# Run tests
test:
	uv run pytest

# Clean build and temporary cache files
clean:
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

