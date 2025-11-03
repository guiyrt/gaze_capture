# Use debian base image
FROM python:3.10-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables to prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install System Dependencies
#   - dbus: for Tobii driver daemon
#   - x11-xserver-utils: to get screen information
#   - ffmpeg: screen recording
RUN apt-get update && apt-get install -y --no-install-recommends \
    dbus \
    x11-xserver-utils \
    ffmpeg \
    protobuf-compiler \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy Tobii driver
COPY drivers/2.13.2.0/ .
RUN ./setup.sh

# --- Set up Python Environment using pyproject.toml ---
WORKDIR /app

# Copy the files that define the Python environment
COPY . .
RUN protoc --python_out=src/gaze_capture protos/gaze.proto
RUN uv sync --locked

COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uv", "run", "gaze-capture"]