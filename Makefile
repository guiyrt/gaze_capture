# Makefile for the Gaze Capture project
# Manages dependencies, runs the application, and handles Docker tasks.

# --- Variables ---
# Use the virtual environment created by 'uv init'
VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python
SRC_DIR := src/gaze_capture

# --- Core Commands ---
.PHONY: help
help:
	@echo "Gaze Capture Project Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make install         - Create virtual env and install all dependencies from uv.lock"
	@echo "  make lock            - Update uv.lock from pyproject.toml dependencies"
	@echo "  make run             - Run the main application natively from the virtual env"
	@echo "  make format          - Auto-format code with ruff and black (requires dev deps)"
	@echo "  make lint            - Check code for style issues and errors (requires dev deps)"
	@echo "  make docker-build    - Build the Docker image"
	@echo "  make run-docker      - Run the application using the launcher script and Docker Compose"
	@echo "  make clean           - Remove virtual env, lock file, and Python cache files"


# --- Dependency Management (UV) ---
.PHONY: protoc
protoc:
	protoc --python_out=${SRC_DIR} protos/gaze.proto

.PHONY: dummy
dummy:
	docker compose run --rm recorder uv run gaze-capture --dummy
