"""Runtime path resolution for standalone harness usage."""

from pathlib import Path


def existing_project_file(names: tuple[str, ...]) -> Path | None:
    """Return the first existing named file under the project root."""
    root = Path.cwd().resolve()
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None