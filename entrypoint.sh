#!/bin/bash
set -e

echo "Cleaning up stale D-Bus and Tobii locks..."
rm -f /var/run/dbus/pid
rm -f /var/run/messagebus.pid
rm -f /run/dbus/pid

# Setup User and Group dynamically based on env vars (defaults to 1000)
USER_ID=${PUID:-1000}
GROUP_ID=${PGID:-1000}

# Create group if it doesn't exist
if ! getent group "$GROUP_ID" >/dev/null; then
    groupadd -g "$GROUP_ID" appgroup
fi

# Create user if it doesn't exist, and create a home directory (-m)
if ! getent passwd "$USER_ID" >/dev/null; then
    useradd -u "$USER_ID" -g "$GROUP_ID" -m -s /bin/bash appuser
fi

echo "Starting D-Bus system daemon..."
# Create the directory that dbus-daemon needs to store its socket file
mkdir -p /var/run/dbus

echo "Starting Tobii platform runtime in the background..."
/opt/tobiipdk/TOBIIPROFUSIONC/bin/platform_runtime_TOBIIPROFUSIONC_UB22_x64_service &

echo "Waiting for services to initialize..."
sleep 2

echo "Starting main application..."
# gosu drops root privileges and executes the passed command as our new user
exec gosu "${USER_ID}:${GROUP_ID}" "$@"