"""Unit tests for the test-server guard.

These are pure unit tests — no SSH. The guard reads the target's
``~/.rdo/.env`` through an injectable ``reader`` callable, so the test bodies
simply pass in fake env-file strings and assert on the return value or the
exception type.
"""

from __future__ import annotations

import pytest

from gishant_scripts.diagnostic.test_server_guard import (
    TestServerConfigError,
    _parse_env_file,
    resolve_and_validate_test_env,
)


def _fake_reader(body: str):
    """Return a reader callable that always yields *body*."""

    def reader(_target):  # noqa: ARG001 - signature required by the guard
        return body

    return reader


# ---------------------------------------------------------------------------
# _parse_env_file
# ---------------------------------------------------------------------------


class TestParseEnvFile:
    def test_skips_comments_and_blanks(self):
        body = "\n# comment\n\nFOO=bar\n"
        assert _parse_env_file(body) == {"FOO": "bar"}

    def test_strips_single_and_double_quotes(self):
        body = 'A="x"\nB=\'y\'\nC=z\n'
        assert _parse_env_file(body) == {"A": "x", "B": "y", "C": "z"}

    def test_preserves_equals_in_value(self):
        assert _parse_env_file("TOKEN=abc=def")["TOKEN"] == "abc=def"


# ---------------------------------------------------------------------------
# Whitelist acceptance
# ---------------------------------------------------------------------------


class TestGuardAccepts:
    def test_accepts_localhost(self):
        body = "AYON_TEST_SERVER_URL=http://localhost:5000\nAYON_TEST_API_KEY=k\n"
        out = resolve_and_validate_test_env("linux", reader=_fake_reader(body))
        assert out["AYON_SERVER_URL"] == "http://localhost:5000"
        assert out["AYON_API_KEY"] == "k"

    def test_accepts_10_1_69_24(self):
        body = "AYON_TEST_SERVER_URL=http://10.1.69.24:5000\nAYON_TEST_API_KEY=k\n"
        out = resolve_and_validate_test_env("windows", reader=_fake_reader(body))
        assert out["AYON_SERVER_URL"] == "http://10.1.69.24:5000"

    def test_accepts_127_0_0_1(self):
        body = "AYON_TEST_SERVER_URL=http://127.0.0.1:5000\nAYON_TEST_API_KEY=k\n"
        out = resolve_and_validate_test_env("linux", reader=_fake_reader(body))
        assert out["AYON_SERVER_URL"] == "http://127.0.0.1:5000"


# ---------------------------------------------------------------------------
# Whitelist rejection
# ---------------------------------------------------------------------------


class TestGuardRejects:
    @pytest.mark.parametrize(
        "url",
        [
            "https://ayon.redefineoriginals.com",
            "https://ayon.prod.internal",
            "https://ayon-prod.example.com",
            "http://10.1.70.50:5000",
        ],
    )
    def test_rejects_production_looking_urls(self, url):
        body = f"AYON_TEST_SERVER_URL={url}\nAYON_TEST_API_KEY=k\n"
        with pytest.raises(TestServerConfigError, match="non-test server"):
            resolve_and_validate_test_env("linux", reader=_fake_reader(body))

    def test_missing_url_raises(self):
        body = "AYON_TEST_API_KEY=k\n"
        with pytest.raises(TestServerConfigError, match="missing or empty"):
            resolve_and_validate_test_env("linux", reader=_fake_reader(body))

    def test_empty_url_raises(self):
        body = "AYON_TEST_SERVER_URL=\nAYON_TEST_API_KEY=k\n"
        with pytest.raises(TestServerConfigError, match="missing or empty"):
            resolve_and_validate_test_env("linux", reader=_fake_reader(body))

    def test_missing_api_key_raises(self):
        body = "AYON_TEST_SERVER_URL=http://localhost:5000\n"
        with pytest.raises(TestServerConfigError, match="AYON_TEST_API_KEY"):
            resolve_and_validate_test_env("linux", reader=_fake_reader(body))


# ---------------------------------------------------------------------------
# Kitsu handling
# ---------------------------------------------------------------------------


class TestKitsu:
    def test_kitsu_optional_when_absent(self):
        body = "AYON_TEST_SERVER_URL=http://localhost:5000\nAYON_TEST_API_KEY=k\n"
        out = resolve_and_validate_test_env("linux", reader=_fake_reader(body))
        assert "RDO_KITSU_HOST" not in out
        assert "RDO_KITSU_API_TOKEN" not in out

    def test_kitsu_both_set_accepted(self):
        body = (
            "AYON_TEST_SERVER_URL=http://localhost:5000\n"
            "AYON_TEST_API_KEY=k\n"
            "RDO_KITSU_TEST_HOST=http://localhost:8090\n"
            "RDO_KITSU_TEST_API_TOKEN=t\n"
        )
        out = resolve_and_validate_test_env("linux", reader=_fake_reader(body))
        assert out["RDO_KITSU_HOST"] == "http://localhost:8090"
        assert out["RDO_KITSU_API_TOKEN"] == "t"

    def test_kitsu_prod_url_rejected(self):
        body = (
            "AYON_TEST_SERVER_URL=http://localhost:5000\n"
            "AYON_TEST_API_KEY=k\n"
            "RDO_KITSU_TEST_HOST=https://kitsu.redefine.co\n"
            "RDO_KITSU_TEST_API_TOKEN=t\n"
        )
        with pytest.raises(TestServerConfigError, match="non-test server"):
            resolve_and_validate_test_env("linux", reader=_fake_reader(body))

    def test_kitsu_token_without_host_rejected(self):
        body = (
            "AYON_TEST_SERVER_URL=http://localhost:5000\n"
            "AYON_TEST_API_KEY=k\n"
            "RDO_KITSU_TEST_API_TOKEN=t\n"
        )
        with pytest.raises(TestServerConfigError, match="HOST missing"):
            resolve_and_validate_test_env("linux", reader=_fake_reader(body))
