# We use the official uv image which includes python and uv
FROM ghcr.io/astral-sh/uv:python3.10-bookworm-slim AS builder

# Configuration
ENV UV_COMPILE_BYTECODE=1 
ENV UV_LINK_MODE=copy 
ENV UV_NO_DEV=1
WORKDIR /app

# Copy files needed to install dependencies
COPY pyproject.toml uv.lock README.md ./
COPY aware-protos/ ./aware-protos/

# Install dependencies (this layer will be cached)
RUN uv sync --frozen --no-install-project --no-editable

# Copy source code and install project
COPY src/ ./src
RUN uv sync --frozen --no-editable


# -- Runtime --
FROM python:3.10-slim-bookworm

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install System Dependencies
#   - dbus: for Tobii driver daemon
RUN apt-get update && apt-get install -y --no-install-recommends \
    dbus \
    python3-tk \
    gosu \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy Tobii driver
COPY drivers/2.13.2.0/ .
RUN ./setup.sh

COPY entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["aware-command-center"]