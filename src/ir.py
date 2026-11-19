"""Intermediate code: three-address code (Area 4).

Each instruction does one small thing. The tree is turned into a flat list of
these instructions, one list per function. Everything after this stage
(optimiser, interpreter, code generator) works on this form only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from src import ast_nodes as ast


# ------------------------------------------------------------------ operands

@dataclass(frozen=True)
class Var:
    """A named variable or a compiler temporary (t1, t2, ...)."""
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class IntConst:
    value: int

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class FloatConst:
    value: float

    def __str__(self) -> str:
        return repr(self.value)


@dataclass(frozen=True)
class StrConst:
    index: int  # position in the program's string table

    def __str__(self) -> str:
        return f"str{self.index}"


Operand = Union[Var, IntConst, FloatConst, StrConst]


# -------------------------------------------------------------- instructions

@dataclass
class Label:
    name: str

    def __str__(self) -> str:
        return f"{self.name}:"


@dataclass
class Jump:
    target: str

    def __str__(self) -> str:
        return f"    goto {self.target}"


@dataclass
class JumpIfFalse:
    cond: Operand
    target: str

    def __str__(self) -> str:
        return f"    if_false {self.cond} goto {self.target}"


@dataclass
class JumpIfTrue:
    cond: Operand
    target: str

    def __str__(self) -> str:
        return f"    if_true {self.cond} goto {self.target}"


@dataclass
class Move:
    dst: Var
    src: Operand

    def __str__(self) -> str:
        return f"    {self.dst} = {self.src}"


@dataclass
class BinOp:
    dst: Var
    op: str
    left: Operand
    right: Operand

    def __str__(self) -> str:
        return f"    {self.dst} = {self.left} {self.op} {self.right}"


@dataclass
class UnOp:
    dst: Var
    op: str  # neg, not, fneg (decimal minus) or itof (whole number to decimal)
    operand: Operand

    def __str__(self) -> str:
        symbol = {"neg": "-", "not": "not ", "fneg": "-.", "itof": "itof "}[self.op]
        return f"    {self.dst} = {symbol}{self.operand}"


@dataclass
class CallInstr:
    dst: Var | None
    name: str
    args: list[Operand]

    def __str__(self) -> str:
        call = f"call {self.name}({', '.join(str(a) for a in self.args)})"
        return f"    {self.dst} = {call}" if self.dst else f"    {call}"


@dataclass
class ReturnInstr:
    value: Operand | None

    def __str__(self) -> str:
        return f"    return {self.value}" if self.value is not None else "    return"


@dataclass
class WriteInstr:
    value: Operand
    ty: str  # int, float, bool or string: decides how the value is printed

    def __str__(self) -> str:
        return f"    write {self.value} : {self.ty}"


@dataclass
class ReadInstr:
    dst: Var

    def __str__(self) -> str:
        return f"    read {self.dst}"


Instr = Union[Label, Jump, JumpIfFalse, JumpIfTrue, Move, BinOp, UnOp,
              CallInstr, ReturnInstr, WriteInstr, ReadInstr]


@dataclass
class IRFunction:
    name: str
    params: list[str]
    ret_type: str
    body: list[Instr] = field(default_factory=list)

    def __str__(self) -> str:
        head = f"function {self.name}({', '.join(self.params)}) : {self.ret_type}"
        return head + "\n" + "\n".join(str(i) for i in self.body)


@dataclass
class IRProgram:
    functions: list[IRFunction]
    strings: list[str]

    def __str__(self) -> str:
        parts = [f"str{i} = {s!r}" for i, s in enumerate(self.strings)]
        parts.extend(str(f) + "\n" for f in self.functions)
        return "\n".join(parts)

    def instruction_count(self) -> int:
        return sum(1 for f in self.functions for i in f.body if not isinstance(i, Label))


# ---------------------------------------------------------------- generation

class Generator:
    def __init__(self) -> None:
        self.strings: list[str] = []
        self.code: list[Instr] = []
        self.temp_count = 0
        self.label_count = 0
        self.loops: list[tuple[str, str]] = []  # (continue label, break label)
        self.sigs: dict[str, tuple[list[str], str]] = {}
        self.ret_type = "void"

    def temp(self) -> Var:
        self.temp_count += 1
        return Var(f"t{self.temp_count}")

    def label(self) -> str:
        self.label_count += 1
        return f"L{self.label_count}"

    def emit(self, instr: Instr) -> None:
        self.code.append(instr)

    def string_const(self, text: str) -> StrConst:
        if text not in self.strings:
            self.strings.append(text)
        return StrConst(self.strings.index(text))

    def coerce(self, op: Operand, have: str | None, want: str | None) -> Operand:
        """Turn a whole number into a decimal where a decimal is needed."""
        if want != "float" or have != "int":
            return op
        if isinstance(op, IntConst):
            return FloatConst(float(op.value))
        dst = self.temp()
        self.emit(UnOp(dst, "itof", op))
        return dst

    def program(self, program: ast.Program) -> IRProgram:
        self.sigs = {f.name: ([p.ty or "int" for p in f.params], f.ret_type) for f in program.functions}
        functions = [self.function(f) for f in program.functions]
        return IRProgram(functions, self.strings)

    def function(self, func: ast.FuncDecl) -> IRFunction:
        self.code = []
        self.temp_count = 0
        self.label_count = 0
        self.loops = []
        self.ret_type = func.ret_type
        for stmt in func.body.stmts:
            self.stmt(stmt)
        if func.ret_type == "void":
            self.emit(ReturnInstr(None))
        return IRFunction(func.name, [p.unique for p in func.params], func.ret_type, self.code)

    # -------------------------------------------------------------- statements

    def stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.VarDecl):
            if stmt.init is not None:
                value = self.coerce(self.expr(stmt.init), stmt.init.ty, stmt.ty)
            elif stmt.ty == "string":
                value = self.string_const("")
            elif stmt.ty == "float":
                value = FloatConst(0.0)
            else:
                value = IntConst(0)
            self.emit(Move(Var(stmt.unique), value))
        elif isinstance(stmt, ast.Assign):
            value = self.coerce(self.expr(stmt.value), stmt.value.ty, stmt.ty)
            self.emit(Move(Var(stmt.unique), value))
        elif isinstance(stmt, ast.Block):
            for inner in stmt.stmts:
                self.stmt(inner)
        elif isinstance(stmt, ast.If):
            self.if_stmt(stmt)
        elif isinstance(stmt, ast.While):
            start, end = self.label(), self.label()
            self.emit(Label(start))
            self.emit(JumpIfFalse(self.expr(stmt.cond), end))
            self.loops.append((start, end))
            self.stmt(stmt.body)
            self.loops.pop()
            self.emit(Jump(start))
            self.emit(Label(end))
        elif isinstance(stmt, ast.For):
            self.for_stmt(stmt)
        elif isinstance(stmt, ast.Return):
            if stmt.value is None:
                self.emit(ReturnInstr(None))
            else:
                self.emit(ReturnInstr(self.coerce(self.expr(stmt.value), stmt.value.ty, self.ret_type)))
        elif isinstance(stmt, ast.Write):
            self.emit(WriteInstr(self.expr(stmt.value), stmt.value.ty or "int"))
        elif isinstance(stmt, ast.Read):
            self.emit(ReadInstr(Var(stmt.unique)))
        elif isinstance(stmt, ast.ExprStmt):
            call = stmt.expr
            assert isinstance(call, ast.Call)
            args = self.call_args(call)
            dst = self.temp() if call.ty != "void" else None
            self.emit(CallInstr(dst, call.name, args))
        elif isinstance(stmt, ast.Break):
            self.emit(Jump(self.loops[-1][1]))
        elif isinstance(stmt, ast.Continue):
            self.emit(Jump(self.loops[-1][0]))
        else:
            raise AssertionError(f"unknown statement {stmt!r}")

    def if_stmt(self, stmt: ast.If) -> None:
        else_label, end_label = self.label(), self.label()
        self.emit(JumpIfFalse(self.expr(stmt.cond), else_label))
        self.stmt(stmt.then)
        if stmt.otherwise is not None:
            self.emit(Jump(end_label))
            self.emit(Label(else_label))
            self.stmt(stmt.otherwise)
            self.emit(Label(end_label))
        else:
            self.emit(Label(else_label))

    def for_stmt(self, stmt: ast.For) -> None:
        cond_label, step_label, end_label = self.label(), self.label(), self.label()
        if stmt.init is not None:
            self.stmt(stmt.init)
        self.emit(Label(cond_label))
        if stmt.cond is not None:
            self.emit(JumpIfFalse(self.expr(stmt.cond), end_label))
        self.loops.append((step_label, end_label))
        self.stmt(stmt.body)
        self.loops.pop()
        self.emit(Label(step_label))
        if stmt.step is not None:
            self.stmt(stmt.step)
        self.emit(Jump(cond_label))
        self.emit(Label(end_label))

    # ------------------------------------------------------------- expressions

    def expr(self, expr: ast.Expr) -> Operand:
        if isinstance(expr, ast.IntLit):
            return IntConst(expr.value)
        if isinstance(expr, ast.FloatLit):
            return FloatConst(expr.value)
        if isinstance(expr, ast.BoolLit):
            return IntConst(1 if expr.value else 0)
        if isinstance(expr, ast.StrLit):
            return self.string_const(expr.value)
        if isinstance(expr, ast.Name):
            return Var(expr.unique)
        if isinstance(expr, ast.Unary):
            operand = self.expr(expr.operand)
            dst = self.temp()
            op = "fneg" if expr.op == "neg" and expr.operand.ty == "float" else expr.op
            self.emit(UnOp(dst, op, operand))
            return dst
        if isinstance(expr, ast.Binary):
            if expr.op in ("and", "or"):
                return self.short_circuit(expr)
            left = self.expr(expr.left)
            right = self.expr(expr.right)
            op = expr.op
            if "float" in (expr.left.ty, expr.right.ty):
                left = self.coerce(left, expr.left.ty, "float")
                right = self.coerce(right, expr.right.ty, "float")
                op += "."
            dst = self.temp()
            self.emit(BinOp(dst, op, left, right))
            return dst
        if isinstance(expr, ast.Call):
            args = self.call_args(expr)
            dst = self.temp()
            self.emit(CallInstr(dst, expr.name, args))
            return dst
        raise AssertionError(f"unknown expression {expr!r}")

    def call_args(self, call: ast.Call) -> list[Operand]:
        param_types = self.sigs[call.name][0]
        return [self.coerce(self.expr(a), a.ty, want) for a, want in zip(call.args, param_types)]

    def short_circuit(self, expr: ast.Binary) -> Operand:
        """`a and b` skips b when a is false; `a or b` skips b when a is true."""
        result = self.temp()
        end = self.label()
        self.emit(Move(result, self.expr(expr.left)))
        if expr.op == "and":
            self.emit(JumpIfFalse(result, end))
        else:
            self.emit(JumpIfTrue(result, end))
        self.emit(Move(result, self.expr(expr.right)))
        self.emit(Label(end))
        return result


def generate(program: ast.Program) -> IRProgram:
    return Generator().program(program)
