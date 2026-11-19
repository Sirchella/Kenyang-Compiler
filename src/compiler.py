"""The compiler driver: joins every stage and provides the command line.

Stages, in order:
    source -> tokens -> syntax tree -> checked tree -> intermediate code
           -> optimised intermediate code -> assembly -> executable

Usage examples:
    python -m src.compiler examples/factorial_utf8.ken --run
    python -m src.compiler examples/gcd.ken --emit ir
    python -m src.compiler examples/gcd.ken --interpret
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from functools import lru_cache
import io
from pathlib import Path
import subprocess
import sys

from src import ast_nodes, codegen, interpreter, ir, optimiser, toolchain
from src.diagnostics import Diagnostic
from src.lexer import KenyangLexer, Token
from src.parser import parse
from src.semantic import analyse_with_warnings

# Words from the "extended" tier stay available as plain names (for example
# `a` or `te`), because this version of the compiler does not use them.
COMPILER_TIERS = ("CORE", "STANDARD")


@lru_cache(maxsize=1)
def _lexer() -> KenyangLexer:
    """Building the lexer reads the grammar file, so it is done only once."""
    return KenyangLexer(tiers=COMPILER_TIERS)


@dataclass
class Compilation:
    source: str
    tokens: list[Token] = field(default_factory=list)
    program: ast_nodes.Program | None = None
    ir: ir.IRProgram | None = None
    ir_optimised: ir.IRProgram | None = None
    stats: optimiser.Stats | None = None
    asm: str | None = None
    asm_counts: tuple[int, int] | None = None  # instructions before and after the clean-up
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def compile_source(source: str, filename: str = "<input>", optimise: bool = True,
                   want_asm: bool = True) -> Compilation:
    result = Compilation(source)

    lexed = _lexer().tokenize(source)
    result.tokens = lexed.tokens
    if not lexed.ok:
        result.errors = [e.format(filename) for e in lexed.errors]
        return result

    program, parse_errors = parse(lexed.tokens, source)
    result.program = program
    if parse_errors:
        result.errors = [e.format(filename) for e in parse_errors]
        return result

    semantic_errors, warnings = analyse_with_warnings(program, source)
    if semantic_errors:
        result.errors = [e.format(filename) for e in semantic_errors]
        return result
    result.warnings = [w.format(filename) for w in warnings]

    result.ir = ir.generate(program)
    if optimise:
        result.ir_optimised, result.stats = optimiser.optimise(result.ir)
    else:
        result.ir_optimised = result.ir
    if want_asm:
        result.asm, before, after = codegen.generate_with_stats(result.ir_optimised, clean_up=optimise)
        result.asm_counts = (before, after)
    return result


def compile_file(path: Path, optimise: bool = True) -> Compilation:
    return compile_source(path.read_text(encoding="utf-8"), path.name, optimise)


def _uses_input(program: ir.IRProgram) -> bool:
    return any(isinstance(i, ir.ReadInstr) for f in program.functions for i in f.body)


def _build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kenyang", description="Lower Kenyang compiler")
    p.add_argument("file", type=Path, help="a .ken source file")
    p.add_argument("--emit", choices=["tokens", "ast", "ir", "ir-opt", "asm"],
                   help="print the result of one stage and stop")
    p.add_argument("-o", "--output", type=Path, help="name of the executable to make")
    p.add_argument("--run", action="store_true", help="run the program after building it")
    p.add_argument("--interpret", action="store_true",
                   help="run on the built-in virtual machine instead of making an executable")
    p.add_argument("--no-opt", action="store_true", help="turn the optimiser off")
    p.add_argument("--stats", action="store_true", help="show what the optimiser removed")
    p.add_argument("--no-warn", action="store_true", help="hide warnings")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", newline="\n")

    args = _build_cli().parse_args(argv)
    if not args.file.exists():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 2

    result = compile_file(args.file, optimise=not args.no_opt)

    if args.emit == "tokens":
        for tok in result.tokens:
            print(f"{tok.line:>3}:{tok.column:<3}  {tok.type:<12}  {tok.lexeme!r}")
    if not result.ok:
        for message in result.errors:
            print(message, file=sys.stderr)
        count = len(result.errors)
        print(f"\n{count} error{'s' if count != 1 else ''} found. Nothing was built.", file=sys.stderr)
        return 1

    if result.warnings and not args.no_warn:
        for message in result.warnings:
            print(message, file=sys.stderr)
        count = len(result.warnings)
        print(f"{count} warning{'s' if count != 1 else ''}.\n", file=sys.stderr)

    assert result.program and result.ir and result.ir_optimised and result.asm
    if args.emit == "ast":
        print(ast_nodes.dump(result.program))
    elif args.emit == "ir":
        print(result.ir)
    elif args.emit == "ir-opt":
        print(result.ir_optimised)
    elif args.emit == "asm":
        print(result.asm)
    if args.stats and result.stats:
        s = result.stats
        print(f"optimiser: {s.before} instructions before, {s.after} after, {s.removed} removed",
              file=sys.stderr)
    if args.stats and result.asm_counts:
        b, a = result.asm_counts
        print(f"assembly clean-up: {b} instructions before, {a} after, {b - a} removed",
              file=sys.stderr)
    if args.emit:
        return 0

    if args.interpret:
        stdin = sys.stdin.read() if _uses_input(result.ir_optimised) else ""
        try:
            sys.stdout.write(interpreter.run(result.ir_optimised, stdin))
        except interpreter.RuntimeFault as fault:
            print(f"runtime error: {fault}", file=sys.stderr)
            return 1
        return 0

    out = args.output or args.file.with_suffix("")
    asm_path = out.with_suffix(".s")
    asm_path.write_text(result.asm, encoding="utf-8", newline="\n")
    try:
        toolchain.build(asm_path, out)
    except toolchain.ToolchainError as err:
        print(f"error: {err}", file=sys.stderr)
        return 3
    print(f"built {out} (assembly kept in {asm_path})", file=sys.stderr)

    if args.run:
        return toolchain.run_interactive(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
