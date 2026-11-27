#!/usr/bin/env python3
"""Canonical SHA-256 input normalization for additive DevOps tools.

The canonical contract form is 64 lowercase hex characters without a prefix.
Command-line tools may print ``sha256:<hex>``; accept that representation on
input so their output can be piped directly into contract generators.
"""

from __future__ import annotations

import re

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PREFIX = "sha256:"


def normalize_sha256(value: str) -> str:
    """Strip one optional ``sha256:`` prefix and validate the digest.

    Args:
        value: A digest, optionally prefixed with ``sha256:``.

    Returns:
        The canonical 64-character lowercase hex digest.

    Raises:
        ValueError: If the value is not a valid SHA-256 digest.
    """
    candidate = value.strip()
    if candidate.startswith(PREFIX):
        candidate = candidate[len(PREFIX) :]
    if not SHA256_RE.fullmatch(candidate):
        raise ValueError(
            "SHA-256 must be 64 lowercase hex chars, "
            "optionally prefixed with sha256:"
        )
    return candidate
