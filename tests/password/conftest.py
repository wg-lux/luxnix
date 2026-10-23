"""Isolated synthetic storage for tests creating test-only key files."""

import pytest


@pytest.fixture(autouse=True)
def isolated_key_storage(encrypted_test_storage):
    """Exercise key handling against an explicitly simulated encrypted device."""
