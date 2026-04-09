#!/usr/bin/env bash
# install.sh — Install all project dependencies in the correct order.
#
# Two packages cannot be installed via a plain `pip install -r requirements.txt`
# because their metadata pins numpy to a version incompatible with TensorFlow 2.20:
#
#   laion-clap  — 1.1.4 pinned numpy==1.23.5; upgraded to 1.1.7 (>=1.23.5,<2.0) in
#                 requirements.txt, so it now resolves cleanly.
#   musicnn     — pins numpy<1.17; must be installed with --no-deps to avoid
#                 overriding the numpy version that TF 2.20 needs (>=1.26.0).
#
# Usage:
#   bash install.sh
#
# On first run the script will install musicnn 0.1.0 with --no-deps.
# Subsequent runs are idempotent.

set -euo pipefail

echo "==> Installing requirements.txt (pip resolver)"
pip install -r requirements.txt

echo "==> Installing musicnn 0.1.0 with --no-deps (numpy pin bypass)"
pip install --no-deps musicnn==0.1.0

echo ""
echo "All dependencies installed successfully."
echo "numpy version in use: $(python -c 'import numpy; print(numpy.__version__)')"
