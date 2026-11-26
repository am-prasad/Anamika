"""Anamika — an offline, LLM-free privacy firewall for multilingual hospital records.

Pipeline: ingest → detect → link → protect → rewrite → report. The safety layer
(:mod:`anamika.safety`) wraps every stage so no personal data reaches logs, errors or
temporary files.
"""

__version__ = "0.1.0"
