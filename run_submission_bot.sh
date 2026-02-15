#!/usr/bin/env bash
source .venv/bin/activate
set -euo pipefail
export PYTHONPATH=app/src/main/python
python3 app/src/main/python/util/submission_evaluator_bot.py
