#!/bin/bash
# A modified version of the Tobii setup script, purpose-built for Docker.
# This script performs only the necessary file installation steps.

set -e

# --- Configuration Variables from Original Script ---
RUNTIME_FILE_NAME=platform_runtime_TOBIIPROFUSIONC_UB22_x64_service
BIN_INSTALL_DIR=/opt/tobiipdk/TOBIIPROFUSIONC/bin

# The 'install' command is better than 'cp' as it sets ownership and permissions.
echo "I: [Docker Install] Installing runtime binary to ${BIN_INSTALL_DIR}"
mkdir -p ${BIN_INSTALL_DIR}
install -m 755 -g root -o root ${RUNTIME_FILE_NAME} ${BIN_INSTALL_DIR}

echo "I: [Docker Install] File installation complete."
exit 0