"""Tests for intermediate code, the optimiser and the virtual machine (Areas 3 and 4)."""

from __future__ import annotations

import pytest

from src import ir
from src.interpreter import RuntimeFault
from src.optimiser import fold_binary, trunc_div, trunc_mod, wrap
from tests.helpers import EXAMPLES, build, run_vm


def main_body(source: str, optimise: bool = False) -> list[str]:
    result = build("kʉ main() : ngwɔ {\n" + source + "\n}", optimise)
    assert result.ok, result.errors
    func = result.ir_optimised.functions[0]
    return [str(i).strip() for i in func.body]


# ------------------------------------------------------------ intermediate code

def test_expression_becomes_small_steps() -> None:
    lines = main_body("pɨ x = 2 + 3 * 4;")
    assert lines[:3] == ["t1 = 3 * 4", "t2 = 2 + t1", "x = t2"]


def test_void_function_ends_with_return() -> None:
    assert main_body("")[-1] == "return"


def test_while_loop_shape() -> None:
    lines = main_body("pɨ i = 0; kʉ_te (i < 3) { i = i + 1; }")
    assert "L1:" in lines
    assert any(line.startswith("if_false") and line.endswith("goto L2") for line in lines)
    assert "goto L1" in lines and "L2:" in lines


def test_and_skips_right_side_with_a_jump() -> None:
    lines = main_body("tɛp a = tɛtɛp; tɛp b = tɛtɛp; tɛp c = a ne b;")
    assert any(line.startswith("if_false") for line in lines)


def test_break_and_continue_jump_to_loop_labels() -> None:
    lines = main_body("pay_te (pɨ i = 0; i < 5; i = i + 1) { yat (i == 2) { chak; } yat (i == 4) { kati; } }")
    jumps = [line for line in lines if line.startswith("goto")]
    assert len(set(jumps)) >= 3  # continue, break and the loop jump back


def test_strings_are_shared_in_one_table() -> None:
    result = build('kʉ main() : ngwɔ { sɔ("a"); sɔ("b"); sɔ("a"); }')
    assert result.ir.strings == ["a", "b"]


# ------------------------------------------------------------------ the optimiser

def test_constants_are_worked_out_in_advance() -> None:
    lines = main_body("pɨ x = 2 + 3 * 4; sɔ(x);", optimise=True)
    assert lines == ["write 14 : int", "return"]


def test_division_by_zero_is_not_folded_away() -> None:
    lines = main_body("pɨ z = 0; sɔ(5 / z);", optimise=True)
    assert any("/" in line for line in lines)


def test_a_branch_that_never_runs_is_removed() -> None:
    lines = main_body('yat (nse) { sɔ("never"); } sɔ("always");', optimise=True)
    assert lines == ["write str1 : string", "return"]  # str1 is "always"


def test_code_after_return_is_removed() -> None:
    result = build('kʉ f() : pɨ { piti 1; sɔ("dead"); piti 2; } kʉ main() : ngwɔ { sɔ(f()); }')
    body = [str(i).strip() for i in result.ir_optimised.functions[0].body]
    assert body == ["return 1"]


def test_algebra_rules() -> None:
    lines = main_body("pɨ a; pay(a); sɔ(a + 0); sɔ(a * 1); sɔ(a * 0);", optimise=True)
    assert "write a : int" in lines
    assert "write 0 : int" in lines
    assert not any("+" in line or "*" in line for line in lines)


def test_unused_variable_is_removed_but_calls_are_kept() -> None:
    src = "kʉ f() : pɨ { sɔ(1); piti 2; } kʉ main() : ngwɔ { pɨ unused = f(); }"
    result = build(src)
    main = [str(i).strip() for i in result.ir_optimised.functions[1].body]
    assert main == ["call f()", "return"]


def test_optimiser_reduces_instruction_count() -> None:
    result = build((EXAMPLES / "factorial_utf8.ken").read_text(encoding="utf-8"))
    assert result.stats.after < result.stats.before
    assert result.stats.removed == result.stats.before - result.stats.after


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.ken")), ids=lambda p: p.name)
def test_optimiser_never_changes_the_answer(path) -> None:
    source = path.read_text(encoding="utf-8")
    assert run_vm(source, "3 4", optimise=True) == run_vm(source, "3 4", optimise=False)


def test_number_helpers_match_the_processor() -> None:
    assert wrap(2 ** 63) == -(2 ** 63)
    assert wrap(-(2 ** 63) - 1) == 2 ** 63 - 1
    assert (trunc_div(-17, 5), trunc_mod(-17, 5)) == (-3, -2)
    assert (trunc_div(17, -5), trunc_mod(17, -5)) == (-3, 2)
    assert fold_binary("/", 1, 0) is None
    assert fold_binary("<=", 2, 2) == 1


# ----------------------------------------------------------------- virtual machine

def test_vm_runs_recursion() -> None:
    src = ("kʉ f(pɨ n) : pɨ { yat (n <= 1) { piti 1; } piti n * f(n - 1); } "
           "kʉ main() : ngwɔ { sɔ(f(10)); }")
    assert run_vm(src) == "3628800\n"


def test_vm_reports_division_by_zero() -> None:
    with pytest.raises(RuntimeFault, match="division by zero"):
        run_vm("kʉ main() : ngwɔ { pɨ z; pay(z); sɔ(1 / z); }", "0")


def test_vm_reads_numbers_like_the_native_runtime() -> None:
    src = "kʉ main() : ngwɔ { pɨ a; pɨ b; pɨ c; pay(a); pay(b); pay(c); sɔ(a); sɔ(b); sɔ(c); }"
    assert run_vm(src, "  42\n-7 x") == "42\n-7\n0\n"


def test_vm_prints_booleans_with_kenyang_words() -> None:
    assert run_vm("kʉ main() : ngwɔ { sɔ(tɛtɛp); sɔ(nse); }") == "tɛtɛp\nnse\n"


def test_instruction_count_ignores_labels() -> None:
    program = ir.IRProgram([ir.IRFunction("f", [], "void", [ir.Label("L1"), ir.ReturnInstr(None)])], [])
    assert program.instruction_count() == 1


def test_vm_skips_a_byte_order_mark_before_the_number() -> None:
    src = "kʉ main() : ngwɔ { pɨ a; pay(a); sɔ(a); }"
    assert run_vm(src, "\ufeff12\n") == "12\n"


# -------------------------------------------------------------- decimal numbers

def test_whole_number_is_converted_when_mixed_with_a_decimal() -> None:
    lines = main_body("pɨ n; pay(n); pɨ_kati x = n * 1.5; sɔ(x);")
    assert "t1 = itof n" in lines
    assert any("*." in line for line in lines)


def test_decimal_constants_are_folded() -> None:
    lines = main_body("sɔ(1.5 * 2 + 0.25);", optimise=True)
    assert lines == ["write 3.25 : float", "return"]


def test_decimal_division_by_zero_is_not_folded() -> None:
    lines = main_body("pɨ_kati z = 0.0; sɔ(1.0 / z);", optimise=True)
    assert any("/." in line for line in lines)


def test_vm_prints_decimals_with_six_digits() -> None:
    src = "kʉ main() : ngwɔ { sɔ(1 / 3.0); sɔ(-2.5); sɔ(0.0000004); sɔ(0.9999996); sɔ(100); }"
    assert run_vm(src) == "0.333333\n-2.500000\n0.000000\n1.000000\n100\n"


def test_vm_decimal_division_by_zero() -> None:
    with pytest.raises(RuntimeFault, match="division by zero"):
        run_vm("kʉ main() : ngwɔ { pɨ_kati z = 0.0; sɔ(1 / z); }")
