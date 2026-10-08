"""Path lookup for project files above the working directory."""

from packages.harness.thesisflow.config.runtime_paths import existing_project_file


def test_existing_project_file_finds_config_at_repository_root(tmp_path, monkeypatch):
    """A server started in backend should still find config.yaml at the repo root."""
    repo = tmp_path / "research_assistant"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    (repo / ".git").mkdir()
    config = repo / "config.yaml"
    config.write_text("log_level: info\n", encoding="utf-8")
    monkeypatch.chdir(backend)

    found = existing_project_file(("config.yaml",))

    assert found == config.resolve()


def test_existing_project_file_prefers_working_directory(tmp_path, monkeypatch):
    """A config.yaml next to the process wins over the one at the repository root."""
    repo = tmp_path / "research_assistant"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "config.yaml").write_text("root: true\n", encoding="utf-8")
    local = backend / "config.yaml"
    local.write_text("local: true\n", encoding="utf-8")
    monkeypatch.chdir(backend)

    found = existing_project_file(("config.yaml",))

    assert found == local.resolve()
