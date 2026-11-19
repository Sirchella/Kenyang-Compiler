"""Error reports shared by the parser and the semantic analyser."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One error found while compiling, with its place in the source file."""

    kind: str
    message: str
    line: int
    column: int
    source_line: str = ""
    hint: str | None = None

    def format(self, filename: str = "<input>") -> str:
        caret_pad = " " * max(0, self.column - 1)
        lines = [
            f"{self.kind} [{filename}:{self.line}:{self.column}]: {self.message}",
            f"  {self.line:>4} | {self.source_line}",
            f"       | {caret_pad}^",
        ]
        if self.hint:
            lines.append(f"  hint: {self.hint}")
        return "\n".join(lines)


class CompileError(Exception):
    """Raised for problems that stop the compiler at once."""
