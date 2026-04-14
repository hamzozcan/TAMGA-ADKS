#!/bin/bash

cd "$(dirname "$0")"

if [ -d "venv" ]; then
  PYTHON_CMD="./venv/bin/python3"
else
  PYTHON_CMD="python3"
fi

exec "$PYTHON_CMD" tamga_afad_bridge.py "$@"
