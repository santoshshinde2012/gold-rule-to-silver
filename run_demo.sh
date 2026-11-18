#!/usr/bin/env bash
# Create a virtual environment, install dependencies, run tests, and print the example results.
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q --disable-pip-version-check -r requirements.txt
python -m pytest
python -m src.silver_rule_demo
