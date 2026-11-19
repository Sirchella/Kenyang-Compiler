"""End-to-end tests: Kenyang source in, running program out (Area 4)."""

from __future__ import annotations

import pytest

from src import compiler
from tests.helpers import EXAMPLES, build, needs_native, run_native, run_vm

EXPECTED = {
    "factorial_utf8": ("", "120\n"),
    "factorial_ascii": ("", "120\n"),
    "fibonacci": ("", "0\n1\n1\n2\n3\n5\n8\n13\n21\n34\n"),
    "gcd": ("", "6\n"),
    "prime_check": ("", "prime\n"),
    "arithmetic": ("", "14\n20\n3\n2\n-3\n-2\n5\n9223372036854775807\n"
                       "-9223372036854775808\ntɛtɛp\nnse\n"),
    "loops": ("", "16\n111\n"),
    "logic": ("", "left is false\nand stopped early\nleft is true\nor stopped early\n"
                  "tɛtɛp\nnse\n"),
    "strings": ("", "Bayangi\n\nhello\nKenyang\ntab\there \"quoted\"\nBayangi\ntɛtɛp\n"),
    "grade": ("", "A\nB\nC\nF\n"),
    "many_args": ("", "140\n204\n"),
    "input_sum": ("12 -5\n", "7\n-60\n"),
    "journey": ("", "14\n"),
    "decimals": ("", "3.250000\n-1.500000\ntɛtɛp\n8.500000\n12.566360\n1.000000\n"
                     "0.333333\n-7.500000\n7.000000\n"),
}


def test_every_example_has_an_expected_answer() -> None:
    names = {p.stem for p in EXAMPLES.glob("*.ken")}
    assert names == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
@pytest.mark.parametrize("optimise", [True, False], ids=["opt", "noopt"])
def test_virtual_machine_gives_expected_output(name: str, optimise: bool) -> None:
    stdin, want = EXPECTED[name]
    source = (EXAMPLES / f"{name}.ken").read_text(encoding="utf-8")
    assert run_vm(source, stdin, optimise) == want


@needs_native
@pytest.mark.parametrize("name", sorted(EXPECTED))
@pytest.mark.parametrize("optimise", [True, False], ids=["opt", "noopt"])
def test_native_program_gives_expected_output(name: str, optimise: bool, tmp_path) -> None:
    stdin, want = EXPECTED[name]
    source = (EXAMPLES / f"{name}.ken").read_text(encoding="utf-8")
    assert run_native(tmp_path, source, stdin, optimise) == want


@needs_native
def test_native_division_by_zero_stops_with_a_message(tmp_path) -> None:
    from src import toolchain
    source = "kʉ main() : ngwɔ { pɨ z; pay(z); sɔ(10 / z); }"
    result = build(source, optimise=False)
    asm = tmp_path / "prog.s"
    asm.write_text(result.asm, encoding="utf-8", newline="\n")
    toolchain.build(asm, tmp_path / "prog")
    code, out, err = toolchain.run_executable(tmp_path / "prog", "0")
    assert code == 1 and out == ""
    assert "division by zero" in err


@needs_native
def test_native_handles_negative_and_large_numbers(tmp_path) -> None:
    source = ("kʉ main() : ngwɔ { pɨ a; pɨ b; pay(a); pay(b); sɔ(a * b); sɔ(a - b); "
              "sɔ(a / b); sɔ(a % b); }")
    out = run_native(tmp_path, source, "-100000000000 7", optimise=False)
    assert out == "-700000000000\n-100000000007\n-14285714285\n-5\n"


@needs_native
def test_native_skips_a_byte_order_mark_before_the_number(tmp_path) -> None:
    source = "kʉ main() : ngwɔ { pɨ a; pay(a); sɔ(a); }"
    assert run_native(tmp_path, source, "﻿12\n") == "12\n"


@needs_native
def test_assembly_is_real_machine_code(tmp_path) -> None:
    """The executable must be a native ELF file, not a script."""
    from src import toolchain
    result = build("kʉ main() : ngwɔ { sɔ(1); }")
    asm = tmp_path / "prog.s"
    asm.write_text(result.asm, encoding="utf-8", newline="\n")
    toolchain.build(asm, tmp_path / "prog")
    assert (tmp_path / "prog").read_bytes()[:4] == b"\x7fELF"


# ------------------------------------------------------------------ command line

def test_cli_reports_errors_and_fails(capsys) -> None:
    code = compiler.main([str(EXAMPLES / "errors" / "semantic_error.ken")])
    err = capsys.readouterr().err
    assert code == 1
    assert "6 errors found" in err and "Did you mean 'count'?" in err


def test_cli_lexical_and_syntax_errors(capsys) -> None:
    assert compiler.main([str(EXAMPLES / "errors" / "lex_error.ken")]) == 1
    assert "2 errors found" in capsys.readouterr().err
    assert compiler.main([str(EXAMPLES / "errors" / "syntax_error.ken")]) == 1
    assert "3 errors found" in capsys.readouterr().err


def test_cli_emit_stages(capsys) -> None:
    path = str(EXAMPLES / "gcd.ken")
    assert compiler.main([path, "--emit", "tokens"]) == 0
    assert "KW_FUNC" in capsys.readouterr().out
    assert compiler.main([path, "--emit", "ast"]) == 0
    assert "FuncDecl" in capsys.readouterr().out
    assert compiler.main([path, "--emit", "ir"]) == 0
    assert "function gcd(a, b)" in capsys.readouterr().out
    assert compiler.main([path, "--emit", "ir-opt", "--stats"]) == 0
    captured = capsys.readouterr()
    assert "function gcd(a, b)" in captured.out and "removed" in captured.err
    assert compiler.main([path, "--emit", "asm"]) == 0
    assert "ken_gcd:" in capsys.readouterr().out


def test_cli_interpret_runs_the_program(capsys) -> None:
    assert compiler.main([str(EXAMPLES / "gcd.ken"), "--interpret"]) == 0
    assert capsys.readouterr().out == "6\n"


def test_cli_missing_file(capsys) -> None:
    assert compiler.main(["no_such_file.ken"]) == 2


@needs_native
def test_native_decimal_printing_matches_the_virtual_machine(tmp_path) -> None:
    source = ("kʉ main() : ngwɔ { sɔ(1 / 3.0); sɔ(-2.5); sɔ(0.0000004); sɔ(0.9999996); "
              "sɔ(123456789.125); sɔ(-0.5); sɔ(2.0 * 3 - 0.75); }")
    assert run_native(tmp_path, source, optimise=False) == run_vm(source, optimise=False)
    assert run_native(tmp_path, source) == run_vm(source)


@needs_native
def test_native_decimal_division_by_zero(tmp_path) -> None:
    from src import toolchain
    result = build("kʉ main() : ngwɔ { pɨ_kati z = 0.0; sɔ(1 / z); }", optimise=False)
    asm = tmp_path / "prog.s"
    asm.write_text(result.asm, encoding="utf-8", newline="\n")
    toolchain.build(asm, tmp_path / "prog")
    code, out, err = toolchain.run_executable(tmp_path / "prog")
    assert code == 1 and "division by zero" in err


def test_assembly_clean_up_removes_reloads_and_keeps_the_answer() -> None:
    source = (EXAMPLES / "loops.ken").read_text(encoding="utf-8")
    with_pass = compiler.compile_source(source, "t.ken")
    without = compiler.compile_source(source, "t.ken", optimise=False)
    before, after = with_pass.asm_counts
    assert after < before
    assert without.asm_counts[0] == without.asm_counts[1]  # --no-opt also skips the clean-up


def test_cli_prints_warnings_but_still_runs(capsys) -> None:
    code = compiler.main([str(EXAMPLES / "errors" / "warnings.ken"), "--interpret"])
    captured = capsys.readouterr()
    assert code == 0
    assert "2 warnings" in captured.err and captured.out == "2\n"
    compiler.main([str(EXAMPLES / "errors" / "warnings.ken"), "--interpret", "--no-warn"])
    assert "warning" not in capsys.readouterr().err
