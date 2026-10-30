"""Reject a CA bundle that still contains any distrusted Mozilla root.

Certificates are matched by DER content, so a root is found whether it is
published as a plain CERTIFICATE block or as an OpenSSL TRUSTED CERTIFICATE
block that carries trust rules after the certificate.
"""

import argparse
import base64
import sys
from pathlib import Path

BEGIN = "-----BEGIN "
NON_LABEL_PREFIXES = ("Trusted for:", "Rejected for:", "Traditional PEM block omitted", "  - ", "#")


def _certificate_der(blob: bytes) -> bytes:
    # A TRUSTED CERTIFICATE blob is the certificate SEQUENCE followed by
    # auxiliary trust data; keep only the first DER element.
    if blob[0] != 0x30:
        raise ValueError("PEM block does not start with a DER SEQUENCE")
    length = blob[1]
    offset = 2
    if length & 0x80:
        size = length & 0x7F
        length = int.from_bytes(blob[2 : 2 + size], "big")
        offset += size
    return blob[: offset + length]


def read_blocks(path: Path) -> list[tuple[str, bytes]]:
    """Return (label, certificate DER) for every certificate block."""
    blocks = []
    label = ""
    previous_blank = True
    body: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if body is not None:
            if line.startswith("-----END "):
                blocks.append((label, _certificate_der(base64.b64decode("".join(body)))))
                body = None
            else:
                body.append(line.strip())
            continue
        if line.startswith(BEGIN) and "CERTIFICATE-----" in line:
            body = []
        elif line and previous_blank and not line.startswith(NON_LABEL_PREFIXES):
            label = line.strip()
        previous_blank = not line.strip()
    if body is not None:
        raise ValueError(f"{path}: unterminated PEM block")
    return blocks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="unfiltered Mozilla bundle")
    parser.add_argument("--bundle", type=Path, required=True, help="final system bundle")
    parser.add_argument("--label", action="append", default=[], help="distrusted label")
    args = parser.parse_args()

    distrusted: dict[bytes, str] = {}
    for label, der in read_blocks(args.source):
        if label in args.label:
            distrusted[der] = label
    missing = sorted(set(args.label) - set(distrusted.values()))
    if missing:
        print(
            "ERROR: distrusted labels are not in the pinned cacert; remove them from "
            f"luxnix.caTrust.distrustedCertificates: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    present = sorted({distrusted[der] for _, der in read_blocks(args.bundle) if der in distrusted})
    if present:
        print(f"ERROR: {args.bundle} still contains distrusted roots: {', '.join(present)}", file=sys.stderr)
        return 1
    print(f"Verified {len(set(args.label))} distrusted roots are absent from {args.bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
