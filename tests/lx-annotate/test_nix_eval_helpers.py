from __future__ import annotations

import json
import subprocess

import pytest

import nix_eval_helpers as helpers


def test_eval_json_resolves_the_current_checkout_as_a_git_flake(monkeypatch) -> None:
    received: dict[str, object] = {}

    def fake_run(arguments, **options):
        received["arguments"] = arguments
        received["options"] = options
        return subprocess.CompletedProcess(arguments, 0, json.dumps({"ok": True}), "")

    monkeypatch.setattr(helpers.subprocess, "run", fake_run)
    helpers.eval_json.cache_clear()

    result = helpers.eval_json('builtins.getFlake "__LUXNIX_FLAKE_URI__"')

    assert result == {"ok": True}
    arguments = received["arguments"]
    options = received["options"]
    assert isinstance(arguments, list)
    assert isinstance(options, dict)
    command = " ".join(arguments)
    assert helpers.REPO_FLAKE_URI in command
    assert helpers.FLAKE_URI_PLACEHOLDER not in command
    assert options["cwd"] == helpers.REPO_ROOT


def test_eval_json_exposes_nix_failures(monkeypatch) -> None:
    def fake_run(arguments, **_options):
        return subprocess.CompletedProcess(arguments, 1, "", "concise Nix failure")

    monkeypatch.setattr(helpers.subprocess, "run", fake_run)
    helpers.eval_json.cache_clear()

    with pytest.raises(AssertionError, match="concise Nix failure"):
        helpers.eval_json("false")


def test_eval_result_preserves_expected_failure_results(monkeypatch) -> None:
    expected = subprocess.CompletedProcess(["nix"], 1, "", "expected failure")
    monkeypatch.setattr(helpers.subprocess, "run", lambda *_args, **_kwargs: expected)

    assert helpers.eval_result("false") is expected
