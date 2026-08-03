"""
The Alembic environment must survive a `%` in DATABASE_URL.

The Claritty platform hands every app a tenant-scoped URL:

    …/clarity_platform?options=-csearch_path%3Dtenant_<id>&sslmode=require

Alembic's config is a ConfigParser, which treats `%` as interpolation syntax,
so pushing that URL through `config.set_main_option` raises ValueError before a
single migration runs. The container then never comes up healthy and the
platform reports "Build failed. Please check that your app builds successfully
locally" — which it does, because a local DATABASE_URL contains no `%`. It cost
twelve days and ~45 deploys to find; this test is the tripwire.
"""
import configparser
import pathlib
import re


ENV_PY = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "env.py"


def _code() -> str:
    """env.py with comments stripped — the file explains this bug at length, and
    a naive substring search would match the explanation instead of a call."""
    lines = []
    for line in ENV_PY.read_text().splitlines():
        code = line.split("#", 1)[0]
        if code.strip():
            lines.append(code)
    return "\n".join(lines)


def test_the_db_url_never_goes_through_configparser():
    """set_main_option / engine_from_config both round-trip through the
    ConfigParser that chokes on `%`."""
    src = _code()
    assert "set_main_option" not in src, (
        "DATABASE_URL must not be written into Alembic's ConfigParser — a `%` in "
        "the URL (the platform's tenant search_path) raises ValueError at import."
    )
    assert "engine_from_config" not in src, (
        "engine_from_config reads the URL back out of the ConfigParser section, "
        "which reintroduces the same interpolation problem."
    )
    assert "create_engine" in src


def test_a_tenant_scoped_url_would_break_configparser():
    """Proves the mechanism rather than trusting the comment: this is exactly
    what the platform passes, and exactly what ConfigParser does with it."""
    url = (
        "postgresql://u:p@host:5432/clarity_platform"
        "?options=-csearch_path%3Dtenant_7ac1b8d7_app_f90d5653&sslmode=require"
    )
    cp = configparser.ConfigParser()
    cp.add_section("alembic")
    try:
        cp.set("alembic", "sqlalchemy.url", url)
    except ValueError as e:
        assert "interpolation" in str(e)
    else:  # pragma: no cover - would mean Python changed under us
        raise AssertionError("expected ConfigParser to reject the platform's URL")


def test_the_url_helper_prefers_the_environment():
    """Env wins over the ini, and it's read raw."""
    src = _code()
    helper = re.search(r"def _url\(\).*?return (.+)", src, re.S)
    assert helper, "env.py should resolve the URL through one helper"
    assert "_db_url" in helper.group(1)
