"""Tests for parsimony_mcp._env — the bounded .env loader."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from parsimony_mcp._env import load_env


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Treat tmp_path as $HOME so the bounded walk operates inside the test sandbox."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def project(home: Path) -> Path:
    """A project directory under $HOME with a pyproject.toml anchor."""
    project = home / "myproject"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n")
    return project


class TestPrecedence:
    """overrides > pre-existing os.environ > .env file."""

    def test_dotenv_populates_unset_vars(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (project / ".env").write_text("FRED_API_KEY=from_dotenv\n")
        monkeypatch.delenv("FRED_API_KEY", raising=False)

        load_env(cwd=project)

        assert os.environ["FRED_API_KEY"] == "from_dotenv"

    def test_pre_existing_environ_wins_over_dotenv(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (project / ".env").write_text("FRED_API_KEY=from_dotenv\n")
        monkeypatch.setenv("FRED_API_KEY", "from_host")

        load_env(cwd=project)

        assert os.environ["FRED_API_KEY"] == "from_host"

    def test_overrides_win_over_environ(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FRED_API_KEY", "from_host")

        load_env(cwd=project, overrides={"FRED_API_KEY": "from_overrides"})

        assert os.environ["FRED_API_KEY"] == "from_overrides"

    def test_overrides_win_over_dotenv(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (project / ".env").write_text("FRED_API_KEY=from_dotenv\n")
        monkeypatch.delenv("FRED_API_KEY", raising=False)

        load_env(cwd=project, overrides={"FRED_API_KEY": "from_overrides"})

        assert os.environ["FRED_API_KEY"] == "from_overrides"

    def test_returns_mappingproxy_snapshot(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (project / ".env").write_text("FRED_API_KEY=v\n")
        monkeypatch.delenv("FRED_API_KEY", raising=False)

        snap = load_env(cwd=project)

        # MappingProxyType is read-only — write attempts raise.
        with pytest.raises(TypeError):
            snap["FRED_API_KEY"] = "mutated"  # type: ignore[index]


class TestBoundedWalk:
    """The walk stops at project anchors, $HOME, and refuses world-writable parents."""

    def test_finds_dotenv_at_cwd(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (project / ".env").write_text("PROJECT_KEY=at_root\n")
        monkeypatch.delenv("PROJECT_KEY", raising=False)

        load_env(cwd=project)

        assert os.environ["PROJECT_KEY"] == "at_root"

    def test_finds_dotenv_in_ancestor_when_no_anchor_in_between(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # .env at project root; cwd is a deep subdir without its own anchor.
        (project / ".env").write_text("ANCESTOR_KEY=found\n")
        deep = project / "src" / "lib" / "x"
        deep.mkdir(parents=True)
        # No anchor files in the intermediate dirs — the walk should
        # find project/.env via project's anchor.
        monkeypatch.delenv("ANCESTOR_KEY", raising=False)

        load_env(cwd=deep)

        assert os.environ["ANCESTOR_KEY"] == "found"

    def test_stops_at_intermediate_anchor(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A nested project with its own anchor and no .env. The walk
        # should stop there and never find an ancestor .env.
        (project / ".env").write_text("ANCESTOR_KEY=should_not_load\n")
        nested = project / "subproject"
        nested.mkdir()
        (nested / "pyproject.toml").write_text("[project]\nname='sub'\n")
        deep = nested / "src"
        deep.mkdir()
        monkeypatch.delenv("ANCESTOR_KEY", raising=False)

        load_env(cwd=deep)

        assert "ANCESTOR_KEY" not in os.environ

    def test_does_not_load_when_outside_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Set HOME to a different sibling so cwd is "outside HOME".
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.setenv("HOME", str(elsewhere))

        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / ".env").write_text("OUTSIDE_KEY=should_not_load\n")
        (outside / "pyproject.toml").write_text("[project]\nname='x'\n")
        monkeypatch.delenv("OUTSIDE_KEY", raising=False)

        load_env(cwd=outside)

        assert "OUTSIDE_KEY" not in os.environ

    def test_refuses_world_writable_parent(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (project / ".env").write_text("WW_KEY=should_not_load\n")
        os.chmod(project, 0o777)
        monkeypatch.delenv("WW_KEY", raising=False)

        try:
            load_env(cwd=project)
        finally:
            os.chmod(project, 0o755)

        assert "WW_KEY" not in os.environ
        err = capsys.readouterr().err
        assert "world-writable" in err


class TestProjectDirPin:
    """PARSIMONY_MCP_PROJECT_DIR is honoured only when trustworthy."""

    def test_valid_pin_is_used_as_search_root(
        self, home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pinned = home / "pinned"
        pinned.mkdir()
        (pinned / "pyproject.toml").write_text("[project]\nname='p'\n")
        (pinned / ".env").write_text("PINNED_KEY=from_pinned\n")

        unrelated = home / "unrelated"
        unrelated.mkdir()
        monkeypatch.delenv("PINNED_KEY", raising=False)

        load_env(cwd=unrelated, project_dir_pin=pinned)

        assert os.environ["PINNED_KEY"] == "from_pinned"

    def test_nonexistent_pin_falls_back_to_cwd_with_warning(
        self,
        project: Path,
        home: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (project / ".env").write_text("FALLBACK_KEY=from_cwd\n")
        monkeypatch.delenv("FALLBACK_KEY", raising=False)

        load_env(cwd=project, project_dir_pin=home / "does_not_exist")

        assert os.environ["FALLBACK_KEY"] == "from_cwd"
        err = capsys.readouterr().err
        assert "PARSIMONY_MCP_PROJECT_DIR rejected" in err
        assert "does not resolve" in err

    def test_pin_outside_home_falls_back_with_warning(
        self,
        project: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # tmp_path is currently HOME; create a sibling outside it.
        outside = tmp_path.parent / f"outside_{tmp_path.name}"
        outside.mkdir(exist_ok=True)
        try:
            (project / ".env").write_text("FALLBACK_KEY=from_cwd\n")
            monkeypatch.delenv("FALLBACK_KEY", raising=False)

            load_env(cwd=project, project_dir_pin=outside)

            assert os.environ["FALLBACK_KEY"] == "from_cwd"
            err = capsys.readouterr().err
            assert "PARSIMONY_MCP_PROJECT_DIR rejected" in err
            assert "outside $HOME" in err
        finally:
            outside.rmdir()

    def test_world_writable_pin_falls_back_with_warning(
        self,
        project: Path,
        home: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        pinned = home / "world_writable"
        pinned.mkdir(mode=0o777)
        os.chmod(pinned, 0o777)  # umask might have masked it

        (project / ".env").write_text("FALLBACK_KEY=from_cwd\n")
        monkeypatch.delenv("FALLBACK_KEY", raising=False)

        try:
            load_env(cwd=project, project_dir_pin=pinned)
        finally:
            os.chmod(pinned, 0o755)

        assert os.environ["FALLBACK_KEY"] == "from_cwd"
        err = capsys.readouterr().err
        assert "world-writable" in err

    def test_pin_pointing_at_file_falls_back(
        self,
        project: Path,
        home: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        pinned_file = home / "not_a_dir.txt"
        pinned_file.write_text("nope")

        (project / ".env").write_text("FALLBACK_KEY=from_cwd\n")
        monkeypatch.delenv("FALLBACK_KEY", raising=False)

        load_env(cwd=project, project_dir_pin=pinned_file)

        assert os.environ["FALLBACK_KEY"] == "from_cwd"
        err = capsys.readouterr().err
        assert "not a directory" in err


class TestNoEnvFile:
    """When no .env exists, overrides still apply and pre-existing env stays."""

    def test_overrides_apply_without_dotenv(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ONLY_OVERRIDE", raising=False)

        load_env(cwd=project, overrides={"ONLY_OVERRIDE": "value"})

        assert os.environ["ONLY_OVERRIDE"] == "value"

    def test_no_dotenv_no_overrides_is_a_noop(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PRE_EXISTING", "kept")

        load_env(cwd=project)

        assert os.environ["PRE_EXISTING"] == "kept"
