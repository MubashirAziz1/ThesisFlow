"""Runtime path resolution for standalone harness usage."""

from pathlib import Path


def existing_project_file(names: tuple[str, ...]) -> Path | None:
    """Return the first existing named file under the working directory or repository root."""
    for root in _candidate_roots():
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def _candidate_roots() -> tuple[Path, ...]:
    """Working directory first, then each parent through the repository root."""
    cwd = Path.cwd().resolve()
    roots = [cwd]
    for parent in cwd.parents:
        roots.append(parent)
        if (parent / ".git").exists():
            break
    return tuple(roots)