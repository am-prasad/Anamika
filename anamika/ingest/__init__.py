"""Ingestion: decoding, format sniffing and tolerant parsing of every input file.

Parsers never return partially parsed content: a file is either fully understood or it
raises :class:`~anamika.ingest.sniff.QuarantineError` with a closed-vocabulary reason.
"""
