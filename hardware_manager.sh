#!/bin/bash

# This script creates and applies a udev rule to create a stable,
# persistent device name for a Tobii Pro Fusion eye tracker.

# Exit immediately if any command fails
set -e

# Tobii Pro Fusion udev rule
RULE_CONTENT=$(cat <<'EOF'
# Rule for any Tobii Pro Fusion Eye Tracker
SUBSYSTEM=="usb", ATTRS{idVendor}=="2104", ATTRS{idProduct}=="0604", MODE="0666", SYMLINK+="udev/tobii_pro_fusion"
EOF
)

# The path to the udev rule file
RULE_FILE_PATH="/etc/udev/rules.d/99-tobii-devices-symlink.rules"

DEV_UDEV_DIR="/dev/udev"

# Check for root privileges
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run with sudo." >&2
    exit 1
fi

# Idempotency check: create or update the rule file only if needed
NEEDS_UPDATE=false
if [ ! -f "$RULE_FILE_PATH" ]; then
    echo "Rule file not found. A new one will be created."
    NEEDS_UPDATE=true
else
    # File exists, check if its content matches what we want.
    CURRENT_CONTENT=$(cat "$RULE_FILE_PATH")
    if [ "$CURRENT_CONTENT" != "$RULE_CONTENT" ]; then
        echo "Rule file content is outdated. It will be updated."
        NEEDS_UPDATE=true
    else
        echo "Rule file is already up to date. No changes needed."
    fi
fi

# Write the rule if an update is needed
if [ "$NEEDS_UPDATE" = true ]; then
    echo "Writing new rule to $RULE_FILE_PATH..."
    echo "$RULE_CONTENT" | tee "$RULE_FILE_PATH" > /dev/null

    echo "Reloading udev rules..."
    udevadm control --reload-rules

    echo "Triggering udev to apply new rules to connected devices..."
    udevadm trigger

    echo "Rule applied successfully."
fi

# List active Tobii devices
if [ -d "$DEV_UDEV_DIR" ] && [ "$(ls -A $DEV_UDEV_DIR)" ]; then
    echo "Active devices found in $DEV_UDEV_DIR:"
    
    # Check if lsusb command is available
    if command -v lsusb >/dev/null 2>&1; then
        # Iterate over each file in the directory
        for symlink in "$DEV_UDEV_DIR"/*; do
            if [ -L "$symlink" ]; then
                # Get the real device path (e.g., /dev/bus/usb/001/003)
                real_path=$(realpath "$symlink")
                
                # Extract Bus and Device numbers
                bus_num=$(basename "$(dirname "$real_path")")
                dev_num=$(basename "$real_path")
                
                # Query lsusb for the descriptive information
                device_info=$(lsusb -s "${bus_num}:${dev_num}")
                serial_info=$(lsusb -s "${bus_num}:${dev_num}" -v 2>/dev/null | grep iSerial | awk '{print $3}')

                echo "  - $(basename "$symlink"): -> $device_info, Serial: $serial_info"
            fi
        done
    else
        # Fallback if lsusb is not installed
        for symlink in "$DEV_UDEV_DIR"/*; do
            if [ -L "$symlink" ]; then
                echo "$symlink -> $(realpath "$symlink")"
            fi
        done
    fi
else
    echo "No active devices in $DEV_UDEV_DIR."
fi