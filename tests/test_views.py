"""The views script shoots the board views into the given directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import views


def test_the_flags_reach_the_capture(monkeypatch: pytest.MonkeyPatch) -> None:
  calls: list[tuple[Path, str | None]] = []
  monkeypatch.setattr(
    views, "views", lambda out, chromium: calls.append((out, chromium)) or 0
  )
  monkeypatch.setattr(
    "sys.argv", ["views.py", "--out", "shots", "--chromium", "/bin/chrome"]
  )
  assert views.main() == 0
  monkeypatch.delenv("E2E_CHROMIUM", raising=False)
  monkeypatch.setattr("sys.argv", ["views.py", "--out", "shots"])
  assert views.main() == 0
  assert calls == [(Path("shots"), "/bin/chrome"), (Path("shots"), None)]
