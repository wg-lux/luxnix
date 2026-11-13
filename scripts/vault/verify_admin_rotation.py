#!/usr/bin/env python3
"""Validate a replacement password via private stdin; print only disposition."""

import json
import sys

from lx_administration.models.vault.admin_rotation import verify

if __name__ == "__main__":
    try:
        print(verify(json.load(sys.stdin)))
    except Exception:
        print(
            "Admin rotation verification failed; no credentials were changed",
            file=sys.stderr,
        )
        sys.exit(1)
