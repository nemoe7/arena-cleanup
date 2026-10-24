"""The walk script's entry point routes `--views` to the board view capture."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import walk


def test_views_flag_captures_the_board_views_instead_of_the_walk(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  calls: list[tuple[str, Path, str | None]] = []
  monkeypatch.setattr(
    walk, "views", lambda out, chromium: calls.append(("views", out, chromium)) or 0
  )
  monkeypatch.setattr(
    walk, "walk", lambda out, chromium: calls.append(("walk", out, chromium)) or 0
  )
  monkeypatch.setattr(
    "sys.argv", ["walk.py", "--views", "--out", "shots", "--chromium", "/bin/chrome"]
  )
  assert walk.main() == 0
  monkeypatch.setattr("sys.argv", ["walk.py", "--out", "steps"])
  assert walk.main() == 0
  assert calls == [
    ("views", Path("shots"), "/bin/chrome"),
    ("walk", Path("steps"), None),
  ]
