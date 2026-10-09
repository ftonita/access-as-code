"""Shared error type: problems with the declaration files themselves (exit code 2)."""

from __future__ import annotations


class AccessFileError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems
