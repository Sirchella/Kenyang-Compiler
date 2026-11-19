"""Helpers shared by the tests of every stage."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import interpreter, toolchain
from src.compiler import Compilation, compile_source

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def build(source: str, optimise: bool = True) -> Compilation:
    return compile_source(source, "test.ken", optimise=optimise)


def run_vm(source: str, stdin: str = "", optimise: bool = True) -> str:
    result = build(source, optimise)
    assert result.ok, "\n".join(result.errors)
    assert result.ir_optimised is not None
    return interpreter.run(result.ir_optimised, stdin)


def run_native(path: Path, source: str, stdin: str = "", optimise: bool = True) -> str:
    """Compile to a real executable inside `path` and return what it prints."""
    result = build(source, optimise)
    assert result.ok and result.asm is not None, "\n".join(result.errors)
    asm = path / "prog.s"
    asm.write_text(result.asm, encoding="utf-8", newline="\n")
    exe = path / "prog"
    toolchain.build(asm, exe)
    code, out, err = toolchain.run_executable(exe, stdin)
    assert code == 0, f"exit code {code}: {err}"
    return out


needs_native = pytest.mark.skipif(
    not toolchain.native_available(),
    reason="no assembler and linker found (install WSL on Windows, binutils on Linux)",
)
