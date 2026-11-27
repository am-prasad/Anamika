#!/usr/bin/env python3
"""Anamika: offline, LLM-free privacy firewall for multilingual hospital records.

Main execution entry point used by ``raksha.toml``::

    python main.py --input {input} --output {output}

The pipeline lives in ``backend/anamika`` (ingest → detect → link → protect → rewrite →
report). This file only puts that package on the import path and hands over to its CLI,
so the evaluated command and ``python backend/main.py`` are byte-for-byte equivalent.
The secret is read from the ``RAKSHA_SECRET`` environment variable; privacy rules come
from ``config/policy.yaml``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from anamika.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
