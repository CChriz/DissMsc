#!/usr/bin/env bash
# Setup for TEST4_property — install hypothesis and pytest
set -e
pip install --quiet hypothesis pytest 2>&1 | tail -5
echo "TEST4_property setup complete"
