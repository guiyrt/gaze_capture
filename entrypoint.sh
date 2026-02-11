#!/bin/bash
set -e

echo "Cleaning up stale D-Bus and Tobii locks..."
rm -f /var/run/dbus/pid
rm -f /var/run/messagebus.pid
rm -f /run/dbus/pid

echo "Starting D-Bus system daemon..."
# Create the directory that dbus-daemon needs to store its socket file
mkdir -p /var/run/dbus
dbus-daemon --system

echo "Starting Tobii platform runtime in the background..."
/opt/tobiipdk/TOBIIPROFUSIONC/bin/platform_runtime_TOBIIPROFUSIONC_UB22_x64_service &

echo "Waiting for services to initialize..."
sleep 2

echo "Starting main application..."
# Execute the command passed to the container
exec "$@"