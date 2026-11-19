"""Tests for the parser and the syntax tree (Area 2)."""

from __future__ import annotations

import re

from src import ast_nodes as ast
from src.lexer import KenyangLexer
from src.parser import decode_string, parse

from tests.helpers import EXAMPLES

LEXER = KenyangLexer(tiers=("CORE", "STANDARD"))


def parse_text(source: str):
    lexed = LEXER.tokenize(source)
    assert lexed.ok, lexed.errors
    return parse(lexed.tokens, source)


def body_of_main(source: str) -> list[ast.Stmt]:
    program, errors = parse_text("kʉ main() : ngwɔ { " + source + " }")
    assert errors == [], [e.message for e in errors]
    return program.functions[0].body.stmts


def test_function_header_and_parameters() -> None:
    program, errors = parse_text("kʉ add(pɨ a, pɨ b) : pɨ { piti a + b; }")
    assert errors == []
    func = program.functions[0]
    assert func.name == "add"
    assert [(p.type_name, p.name) for p in func.params] == [("int", "a"), ("int", "b")]
    assert func.ret_type == "int"


def test_function_without_return_type_is_void() -> None:
    program, _ = parse_text("kʉ main() { }")
    assert program.functions[0].ret_type == "void"


def test_multiplication_binds_tighter_than_addition() -> None:
    stmt = body_of_main("pɨ x = 2 + 3 * 4;")[0]
    tree = stmt.init
    assert isinstance(tree, ast.Binary) and tree.op == "+"
    assert isinstance(tree.right, ast.Binary) and tree.right.op == "*"


def test_subtraction_is_left_associative() -> None:
    tree = body_of_main("pɨ x = 10 - 3 - 2;")[0].init
    assert tree.op == "-" and isinstance(tree.left, ast.Binary)
    assert isinstance(tree.right, ast.IntLit) and tree.right.value == 2


def test_logic_operator_priority() -> None:
    tree = body_of_main("tɛp x = a kɛ b ne c;")[0].init
    assert tree.op == "or" and tree.right.op == "and"


def test_unary_operators() -> None:
    tree = body_of_main("pɨ x = -3;")[0].init
    assert isinstance(tree, ast.Unary) and tree.op == "neg"
    tree = body_of_main("tɛp x = ka tɛtɛp;")[0].init
    assert isinstance(tree, ast.Unary) and tree.op == "not"


def test_if_elif_else_chain() -> None:
    stmt = body_of_main("yat (a) { } rɔ_yat (b) { } rɔ { }")[0]
    assert isinstance(stmt, ast.If)
    assert isinstance(stmt.otherwise, ast.If)
    assert isinstance(stmt.otherwise.otherwise, ast.Block)


def test_while_for_and_loop_control() -> None:
    stmts = body_of_main("kʉ_te (a) { kati; } pay_te (pɨ i = 0; i < 3; i = i + 1) { chak; }")
    assert isinstance(stmts[0], ast.While)
    assert isinstance(stmts[0].body.stmts[0], ast.Break)
    loop = stmts[1]
    assert isinstance(loop, ast.For)
    assert isinstance(loop.init, ast.VarDecl) and isinstance(loop.step, ast.Assign)
    assert isinstance(loop.body.stmts[0], ast.Continue)


def test_write_read_return_and_calls() -> None:
    stmts = body_of_main("pay(x); sɔ(f(1, 2)); f(3); piti;")
    assert isinstance(stmts[0], ast.Read) and stmts[0].name == "x"
    assert isinstance(stmts[1], ast.Write) and isinstance(stmts[1].value, ast.Call)
    assert len(stmts[1].value.args) == 2
    assert isinstance(stmts[2], ast.ExprStmt)
    assert isinstance(stmts[3], ast.Return) and stmts[3].value is None


def test_positions_are_recorded_on_nodes() -> None:
    program, _ = parse_text("kʉ main() : ngwɔ {\n    pɨ x = 1;\n}")
    decl = program.functions[0].body.stmts[0]
    assert (decl.line, decl.column) == (2, 5)


def test_string_escapes_are_decoded() -> None:
    assert decode_string('"a\\tb\\n\\"q\\"\\\\"') == 'a\tb\n"q"\\'


def test_missing_semicolon_is_reported_after_previous_token() -> None:
    _, errors = parse_text("kʉ main() : ngwɔ {\n    pɨ x = 5\n    sɔ(x);\n}")
    assert len(errors) == 1
    assert "';'" in errors[0].message
    assert errors[0].line == 2  # on the line that lacks the ';', not the next one


def test_parser_reports_several_errors_in_one_run() -> None:
    source = "kʉ main() : ngwɔ {\n pɨ a = ;\n pɨ b = 1 +;\n sɔ(a);\n}"
    _, errors = parse_text(source)
    assert [e.line for e in errors] == [2, 3]


def test_missing_closing_brace_is_reported() -> None:
    _, errors = parse_text("kʉ main() : ngwɔ {\n sɔ(1);\n")
    assert any("missing '}'" in e.message for e in errors)


def test_code_outside_a_function_is_rejected() -> None:
    _, errors = parse_text("pɨ x = 1;\nkʉ main() : ngwɔ { }")
    assert len(errors) == 1 and "outside a function" in errors[0].message


def test_expression_alone_is_not_a_statement() -> None:
    _, errors = parse_text("kʉ main() : ngwɔ { 1 + 2; }")
    assert len(errors) == 1 and "does nothing" in errors[0].message


def test_decimal_literal_becomes_a_float_node() -> None:
    tree = body_of_main("pɨ_kati x = 1.5;")[0].init
    assert isinstance(tree, ast.FloatLit) and tree.value == 1.5


def test_all_examples_parse_without_errors() -> None:
    for path in sorted(EXAMPLES.glob("*.ken")):
        source = path.read_text(encoding="utf-8")
        program, errors = parse_text(source)
        assert errors == [], f"{path.name}: {[e.message for e in errors]}"
        assert program.functions


def test_utf8_and_ascii_spellings_give_the_same_tree() -> None:
    a, _ = parse_text((EXAMPLES / "factorial_utf8.ken").read_text(encoding="utf-8"))
    b, _ = parse_text((EXAMPLES / "factorial_ascii.ken").read_text(encoding="utf-8"))
    def without_positions(tree: ast.Program) -> str:
        return re.sub(r"  @\d+:\d+", "", ast.dump(tree))  # the two spellings differ in length

    assert without_positions(a) == without_positions(b)
