#!/usr/bin/env python3
"""Publish complete, authenticated Vault CRLs for the hub's pinned client CA set.

CRL endpoints are public PKI objects; publisher authentication is HTTPS under a
separately provisioned Vault TLS CA, followed by signature verification under
local client CAs. No token or trust material is fetched from the endpoint.
"""

import argparse
import datetime as dt
import fcntl
import os
from pathlib import Path
import re
import ssl
import tempfile
import urllib.parse
import urllib.request

from cryptography import x509
from cryptography.hazmat.primitives import serialization

LIMIT = 16 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("CRL redirects are forbidden")


def fetch(url, tls_ca):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("CRL URL must use HTTPS without embedded credentials")
    context = ssl.create_default_context(cafile=str(tls_ca))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
        NoRedirect(),
    )
    with opener.open(url, timeout=15) as response:
        content = response.read(LIMIT + 1)
    if len(content) > LIMIT:
        raise ValueError("CRL response exceeds size limit")
    return content


def parse_crls(content):
    blocks = re.findall(
        rb"-----BEGIN X509 CRL-----.*?-----END X509 CRL-----", content, re.S
    )
    if (
        not blocks
        or re.sub(
            rb"-----BEGIN X509 CRL-----.*?-----END X509 CRL-----",
            b"",
            content,
            flags=re.S,
        ).strip()
    ):
        raise ValueError("Expected only PEM CRLs")
    return [x509.load_pem_x509_crl(block) for block in blocks]


def validate(content, ca_file, max_age, min_validity, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    certificates = x509.load_pem_x509_certificates(Path(ca_file).read_bytes())
    if not certificates:
        raise ValueError("Pinned client CA bundle is empty")
    crls = parse_crls(content)
    issuers = {}
    for cert in certificates:
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError("Pinned client CA bundle contains a non-CA certificate")
        if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
            raise ValueError("Pinned client CA certificate is not current")
        matching = [
            crl
            for crl in crls
            if crl.issuer == cert.subject and crl.is_signature_valid(cert.public_key())
        ]
        if len(matching) != 1:
            raise ValueError("Exactly one signed CRL is required for each pinned CA")
        crl = matching[0]
        # Delta/indirect CRLs require additional OpenSSL configuration; refuse
        # these rather than publish a silently incomplete revocation set.
        for extension in crl.extensions:
            if isinstance(
                extension.value, (x509.DeltaCRLIndicator, x509.IssuingDistributionPoint)
            ):
                raise ValueError("Only complete, direct CRLs are supported")
            if extension.critical:
                raise ValueError("Unsupported critical CRL extension")
        if not now - dt.timedelta(seconds=max_age) <= crl.last_update_utc <= now:
            raise ValueError("CRL is stale or issued in the future")
        if crl.next_update_utc is None or crl.next_update_utc <= now + dt.timedelta(
            seconds=min_validity
        ):
            raise ValueError("CRL is expired or too close to expiry")
        issuers[cert.subject.rfc4514_string()] = crl
    if len(issuers) != len(crls):
        raise ValueError("CRL bundle contains duplicate or untrusted issuers")
    return issuers


def publish(content, ca_file, output, max_age, min_validity):
    output = Path(output)
    current = validate(content, ca_file, max_age, min_validity)
    # The systemd-owned directory and lock are root-only writable. Keep the
    # prior authenticated publication intact on all validation failures.
    output.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    with (output.parent / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if output.exists():
            previous = parse_crls(output.read_bytes())
            for old in previous:
                new = current.get(old.issuer.rfc4514_string())
                if new is None:
                    raise ValueError(
                        "Removing a pinned CRL requires explicit CA migration"
                    )
                if new.last_update_utc < old.last_update_utc:
                    raise ValueError("CRL publication would roll back issuance time")
                try:
                    old_number = old.extensions.get_extension_for_class(x509.CRLNumber)
                    new_number = new.extensions.get_extension_for_class(x509.CRLNumber)
                except x509.ExtensionNotFound:
                    raise ValueError("CRL rollback protection requires CRL numbers")
                if new_number.value.crl_number < old_number.value.crl_number:
                    raise ValueError("CRL publication would roll back its number")
                if (
                    new_number.value.crl_number == old_number.value.crl_number
                    and new.public_bytes(serialization.Encoding.DER)
                    != old.public_bytes(serialization.Encoding.DER)
                ):
                    raise ValueError("CRL number reused for different contents")
        # Require numbered CRLs from the first publication too.
        for crl in current.values():
            crl.extensions.get_extension_for_class(x509.CRLNumber)
        fd, temporary = tempfile.mkstemp(prefix=".crl-", dir=output.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
            os.replace(temporary, output)
            directory_fd = os.open(output.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", required=True)
    parser.add_argument("--tls-ca", required=True, type=Path)
    parser.add_argument("--client-ca", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-age-seconds", type=int, default=259200)
    parser.add_argument("--min-validity-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.max_age_seconds <= 0 or args.min_validity_seconds <= 0:
        parser.error("Freshness bounds must be positive")
    try:
        content = b"\n".join(fetch(url, args.tls_ca) for url in args.url)
        publish(
            content,
            args.client_ca,
            args.output,
            args.max_age_seconds,
            args.min_validity_seconds,
        )
    except Exception as error:
        # Do not print HTTP bodies or caller-controlled URLs to the journal.
        print(f"Hub CRL publication failed ({type(error).__name__}); transfers blocked")
        return 1
    print("Authenticated hub CRL bundle published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
