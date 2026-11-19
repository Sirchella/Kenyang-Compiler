"""Semantic analyser (Area 3).

The parser only checks the shape of a program. This stage checks that the
program makes sense: every name is declared, every operator gets the right
kind of value, every call matches its function, and so on.

While it works it also writes the type of every expression onto the tree and
gives every variable a unique name, so the next stage does not have to
repeat any of this work.
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib

from src import ast_nodes as ast
from src.diagnostics import Diagnostic

ERR = "error"  # type given to a broken expression, so one mistake is reported once
UNSUPPORTED_TYPES = {"char"}
NUMBERS = ("int", "float")


def assignable(want: str, got: str) -> bool:
    """A value fits a variable of type `want`; a whole number may widen to a decimal."""
    return want == got or (want == "float" and got == "int")


@dataclass
class Symbol:
    unique: str
    ty: str
    node: ast.Node | None = None
    is_param: bool = False
    used: bool = False  # becomes True when the value is read


@dataclass
class FuncSig:
    name: str
    param_types: list[str]
    ret_type: str
    line: int


class Analyser:
    def __init__(self, source: str = "") -> None:
        self.source_lines = source.splitlines() or [""]
        self.errors: list[Diagnostic] = []
        self.warnings: list[Diagnostic] = []
        self.functions: dict[str, FuncSig] = {}
        self.scopes: list[dict[str, Symbol]] = []
        self.name_counts: dict[str, int] = {}
        self.current: FuncSig | None = None
        self.loop_depth = 0

    # --------------------------------------------------------------- errors

    def error(self, node: ast.Node, message: str, hint: str | None = None) -> None:
        text = self.source_lines[node.line - 1] if 1 <= node.line <= len(self.source_lines) else ""
        self.errors.append(Diagnostic("SemanticError", message, node.line, node.column, text, hint))

    def warn(self, node: ast.Node, message: str, hint: str | None = None) -> None:
        text = self.source_lines[node.line - 1] if 1 <= node.line <= len(self.source_lines) else ""
        self.warnings.append(Diagnostic("Warning", message, node.line, node.column, text, hint))

    # ---------------------------------------------------------------- scopes

    def push_scope(self) -> None:
        self.scopes.append({})

    def pop_scope(self) -> None:
        scope = self.scopes.pop()
        for name, sym in scope.items():
            if not sym.used and not sym.is_param and sym.node is not None and not name.startswith("_"):
                self.warn(sym.node, f"variable '{name}' is never used",
                          "Remove it, or start its name with _ if it is on purpose.")

    def declare(self, node: ast.Node, name: str, ty: str, is_param: bool = False) -> str:
        if name in self.scopes[-1]:
            self.error(node, f"'{name}' is already declared in this scope")
        count = self.name_counts.get(name, 0)
        self.name_counts[name] = count + 1
        unique = name if count == 0 else f"{name}.{count}"
        self.scopes[-1][name] = Symbol(unique, ty, node, is_param)
        return unique

    def lookup(self, name: str) -> Symbol | None:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def undefined_name(self, node: ast.Node, name: str) -> None:
        known = [n for scope in self.scopes for n in scope]
        close = difflib.get_close_matches(name, known, n=1)
        hint = f"Did you mean '{close[0]}'?" if close else None
        self.error(node, f"'{name}' is not declared", hint)

    # ------------------------------------------------------------- top level

    def check_type_name(self, node: ast.Node, type_name: str) -> str:
        if type_name in UNSUPPORTED_TYPES:
            self.error(node, f"the type '{type_name}' is not supported in this version",
                       "Use int, float, bool or string.")
            return ERR
        return type_name

    def analyse(self, program: ast.Program) -> list[Diagnostic]:
        for func in program.functions:
            if func.name in self.functions:
                self.error(func, f"function '{func.name}' is already defined on line "
                                 f"{self.functions[func.name].line}")
                continue
            ptypes = [self.check_type_name(p, p.type_name) for p in func.params]
            rtype = self.check_type_name(func, func.ret_type)
            self.functions[func.name] = FuncSig(func.name, ptypes, rtype, func.line)

        main = self.functions.get("main")
        if main is None:
            self.error(program, "the program has no 'main' function",
                       "Add a function called main with no parameters.")
        else:
            if main.param_types:
                self.error(program, "'main' must not take parameters")
            if main.ret_type not in ("void", ERR):
                self.error(program, "'main' must not return a value")

        for func in program.functions:
            if self.functions.get(func.name) and self.functions[func.name].line == func.line:
                self.check_function(func)
        return self.errors

    def check_function(self, func: ast.FuncDecl) -> None:
        self.current = self.functions[func.name]
        self.scopes = []
        self.name_counts = {}
        self.loop_depth = 0
        self.push_scope()
        for param, ptype in zip(func.params, self.current.param_types):
            param.ty = ptype
            param.unique = self.declare(param, param.name, ptype, is_param=True)
        self.check_stmts(func.body.stmts)
        if self.current.ret_type not in ("void", ERR) and not self.always_returns(func.body):
            self.error(func, f"function '{func.name}' may end without returning a value",
                       "Make sure every path ends with a return statement.")
        self.pop_scope()

    # ------------------------------------------------------------ statements

    def check_stmts(self, stmts: list[ast.Stmt]) -> None:
        warned = False
        for i, stmt in enumerate(stmts):
            self.check_stmt(stmt)
            leaves = isinstance(stmt, (ast.Break, ast.Continue)) or self.always_returns(stmt)
            if leaves and i + 1 < len(stmts) and not warned:
                self.warn(stmts[i + 1], "this code can never run",
                          "Everything after a return, break or continue in the same block is skipped.")
                warned = True

    def check_block(self, block: ast.Block) -> None:
        self.push_scope()
        self.check_stmts(block.stmts)
        self.pop_scope()

    def check_stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.VarDecl):
            self.check_var_decl(stmt)
        elif isinstance(stmt, ast.Assign):
            self.check_assign(stmt)
        elif isinstance(stmt, ast.Block):
            self.check_block(stmt)
        elif isinstance(stmt, ast.If):
            self.expect_bool(stmt.cond, "the condition of an if")
            self.check_block(stmt.then)
            if stmt.otherwise is not None:
                self.check_stmt(stmt.otherwise)
        elif isinstance(stmt, ast.While):
            self.expect_bool(stmt.cond, "the condition of a while loop")
            self.loop_depth += 1
            self.check_block(stmt.body)
            self.loop_depth -= 1
        elif isinstance(stmt, ast.For):
            self.push_scope()
            if stmt.init is not None:
                self.check_stmt(stmt.init)
            if stmt.cond is not None:
                self.expect_bool(stmt.cond, "the condition of a for loop")
            if stmt.step is not None:
                self.check_stmt(stmt.step)
            self.loop_depth += 1
            self.check_block(stmt.body)
            self.loop_depth -= 1
            self.pop_scope()
        elif isinstance(stmt, ast.Return):
            self.check_return(stmt)
        elif isinstance(stmt, ast.Write):
            ty = self.check_expr(stmt.value)
            if ty == "void":
                self.error(stmt.value, "a function that returns nothing has no value to write")
        elif isinstance(stmt, ast.Read):
            sym = self.lookup(stmt.name)
            if sym is None:
                self.undefined_name(stmt, stmt.name)
            else:
                stmt.unique = sym.unique
                if sym.ty not in ("int", ERR):
                    self.error(stmt, f"read can only fill an int variable, but '{stmt.name}' is {sym.ty}")
        elif isinstance(stmt, ast.ExprStmt):
            self.check_expr(stmt.expr)
        elif isinstance(stmt, (ast.Break, ast.Continue)):
            if self.loop_depth == 0:
                word = "break" if isinstance(stmt, ast.Break) else "continue"
                self.error(stmt, f"'{word}' can only be used inside a loop")

    def check_var_decl(self, stmt: ast.VarDecl) -> None:
        init_type = self.check_expr(stmt.init) if stmt.init is not None else None
        if stmt.type_name is None:
            if init_type is None:
                self.error(stmt, f"'{stmt.name}' needs a starting value so its type can be found")
                ty = ERR
            elif init_type == "void":
                self.error(stmt.init, "a function that returns nothing has no value to store")  # type: ignore[arg-type]
                ty = ERR
            else:
                ty = init_type
        else:
            ty = self.check_type_name(stmt, stmt.type_name)
            if ty == "void":
                self.error(stmt, "a variable cannot have the type void")
                ty = ERR
            elif init_type is not None and ERR not in (ty, init_type) and not assignable(ty, init_type):
                self.error(stmt.init, f"cannot store {init_type} in '{stmt.name}', which is {ty}")  # type: ignore[arg-type]
        stmt.ty = ty
        stmt.unique = self.declare(stmt, stmt.name, ty)

    def check_assign(self, stmt: ast.Assign) -> None:
        value_type = self.check_expr(stmt.value)
        sym = self.lookup(stmt.name)
        if sym is None:
            self.undefined_name(stmt, stmt.name)
            return
        stmt.unique = sym.unique
        stmt.ty = sym.ty
        if ERR not in (sym.ty, value_type) and not assignable(sym.ty, value_type):
            self.error(stmt.value, f"cannot store {value_type} in '{stmt.name}', which is {sym.ty}")

    def check_return(self, stmt: ast.Return) -> None:
        assert self.current is not None
        want = self.current.ret_type
        if stmt.value is None:
            if want not in ("void", ERR):
                self.error(stmt, f"this function must return a {want} value")
            return
        got = self.check_expr(stmt.value)
        if want == "void":
            self.error(stmt, "a void function cannot return a value")
        elif ERR not in (want, got) and not assignable(want, got):
            self.error(stmt.value, f"this function returns {want}, but the value is {got}")

    def expect_bool(self, expr: ast.Expr, where: str) -> None:
        ty = self.check_expr(expr)
        if ty not in ("bool", ERR):
            self.error(expr, f"{where} must be bool, but this is {ty}")

    def always_returns(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.Return):
            return True
        if isinstance(stmt, ast.Block):
            return any(self.always_returns(s) for s in stmt.stmts)
        if isinstance(stmt, ast.If):
            return (stmt.otherwise is not None
                    and self.always_returns(stmt.then)
                    and self.always_returns(stmt.otherwise))
        return False

    # ----------------------------------------------------------- expressions

    def check_expr(self, expr: ast.Expr) -> str:
        expr.ty = self.type_of(expr)
        return expr.ty

    def type_of(self, expr: ast.Expr) -> str:
        if isinstance(expr, ast.IntLit):
            if expr.value > 2 ** 63 - 1:
                self.error(expr, "this number is too large for an int",
                           "The largest int is 9223372036854775807.")
                return ERR
            return "int"
        if isinstance(expr, ast.FloatLit):
            return "float"
        if isinstance(expr, ast.BoolLit):
            return "bool"
        if isinstance(expr, ast.StrLit):
            return "string"
        if isinstance(expr, ast.Name):
            sym = self.lookup(expr.name)
            if sym is None:
                self.undefined_name(expr, expr.name)
                return ERR
            expr.unique = sym.unique
            sym.used = True
            return sym.ty
        if isinstance(expr, ast.Unary):
            return self.type_of_unary(expr)
        if isinstance(expr, ast.Binary):
            return self.type_of_binary(expr)
        if isinstance(expr, ast.Call):
            return self.type_of_call(expr)
        raise AssertionError(f"unknown expression {expr!r}")

    def type_of_unary(self, expr: ast.Unary) -> str:
        ty = self.check_expr(expr.operand)
        if ty == ERR:
            return ERR
        if expr.op == "neg":
            if ty not in NUMBERS:
                self.error(expr, f"the minus sign needs a number, but this is {ty}")
                return ERR
            return ty
        if ty != "bool":
            self.error(expr, f"'not' needs a bool, but this is {ty}")
            return ERR
        return "bool"

    def type_of_binary(self, expr: ast.Binary) -> str:
        left = self.check_expr(expr.left)
        right = self.check_expr(expr.right)
        if ERR in (left, right):
            return ERR
        op = expr.op
        both_numbers = left in NUMBERS and right in NUMBERS
        if op == "%":
            if left == right == "int":
                return "int"
            self.error(expr, f"'%' needs two ints, but got {left} and {right}",
                       "The remainder is only defined for whole numbers." if both_numbers else None)
            return ERR
        if op in ("+", "-", "*", "/"):
            if both_numbers:
                return "float" if "float" in (left, right) else "int"
            hint = "Joining strings with + is not supported in this version." if "string" in (left, right) else None
            self.error(expr, f"'{op}' needs two numbers, but got {left} and {right}", hint)
            return ERR
        if op in ("<", "<=", ">", ">="):
            if both_numbers:
                return "bool"
            self.error(expr, f"'{op}' needs two numbers, but got {left} and {right}")
            return ERR
        if op in ("==", "!="):
            if both_numbers or (left == right and left == "bool"):
                return "bool"
            if left == right == "string":
                self.error(expr, "comparing strings is not supported in this version")
            else:
                self.error(expr, f"'{op}' needs two values of the same type, but got {left} and {right}")
            return ERR
        if left == right == "bool":
            return "bool"
        self.error(expr, f"'{op}' needs two bools, but got {left} and {right}")
        return ERR

    def type_of_call(self, expr: ast.Call) -> str:
        arg_types = [self.check_expr(a) for a in expr.args]
        sig = self.functions.get(expr.name)
        if sig is None:
            known = list(self.functions)
            close = difflib.get_close_matches(expr.name, known, n=1)
            hint = f"Did you mean '{close[0]}'?" if close else None
            self.error(expr, f"function '{expr.name}' is not defined", hint)
            return ERR
        if len(arg_types) != len(sig.param_types):
            self.error(expr, f"'{expr.name}' takes {len(sig.param_types)} argument(s) "
                             f"but {len(arg_types)} were given")
            return sig.ret_type
        for i, (got, want) in enumerate(zip(arg_types, sig.param_types), start=1):
            if ERR not in (got, want) and not assignable(want, got):
                self.error(expr.args[i - 1], f"argument {i} of '{expr.name}' should be {want}, but is {got}")
        return sig.ret_type


def analyse(program: ast.Program, source: str = "") -> list[Diagnostic]:
    return Analyser(source).analyse(program)


def analyse_with_warnings(program: ast.Program, source: str = "") -> tuple[list[Diagnostic], list[Diagnostic]]:
    """Return (errors, warnings). Warnings are only trusted when there are no errors."""
    analyser = Analyser(source)
    errors = analyser.analyse(program)
    return errors, ([] if errors else sorted(analyser.warnings, key=lambda w: (w.line, w.column)))
