"""Code generator for x86-64 Linux (Area 4).

It turns the intermediate code into assembly text (GNU assembler, Intel
syntax). The assembler and linker then make a real executable.

Plan used here, kept simple on purpose:
- Every variable and temporary lives in its own 8-byte slot on the stack.
- Each instruction loads what it needs into registers (rax, rcx, rdx),
  does its work, and stores the answer back into a slot.
- Functions follow the System V calling convention: the first six arguments
  travel in rdi, rsi, rdx, rcx, r8, r9, the rest on the stack, and the answer
  comes back in rax.
- The runtime (printing, reading, exit) is written in assembly and talks
  straight to the Linux kernel, so no C library is needed.
"""

from __future__ import annotations

import struct

from src.ir import (
    BinOp, CallInstr, FloatConst, IntConst, IRFunction, IRProgram, Jump, JumpIfFalse,
    JumpIfTrue, Label, Move, Operand, ReadInstr, ReturnInstr, StrConst, UnOp,
    Var, WriteInstr,
)

ARG_REGS = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]
FLOAT_ARITH = {"+.": "addsd", "-.": "subsd", "*.": "mulsd", "/.": "divsd"}
FLOAT_COMPARE = {  # operator: (ucomisd operands in order, condition set)
    "<.": ("xmm1, xmm0", "seta"), "<=.": ("xmm1, xmm0", "setae"),
    ">.": ("xmm0, xmm1", "seta"), ">=.": ("xmm0, xmm1", "setae"),
    "==.": ("xmm0, xmm1", "sete"), "!=.": ("xmm0, xmm1", "setne"),
}
COMPARE_SET = {"<": "setl", "<=": "setle", ">": "setg", ">=": "setge", "==": "sete", "!=": "setne"}


def sym(name: str) -> str:
    """Assembly name of a Kenyang function (prefixed so it never clashes)."""
    return f"ken_{name}"


def count_instructions(lines: list[str]) -> int:
    """Count real instructions (not labels, directives or comments)."""
    return sum(1 for l in lines if l.startswith("    ") and l.strip()[:1] not in (".", "#"))


def peephole(lines: list[str]) -> list[str]:
    """Small clean-up of the assembly text.

    The generator stores every answer in a stack box, and the next instruction
    often loads the same box straight back. The value is still in the register,
    so the load is not needed (or is a cheaper register copy).
    """
    out: list[str] = []
    for line in lines:
        text = line.strip()
        if out:
            prev = out[-1].strip()
            if prev.startswith("mov [rbp - ") and prev.endswith(", rax"):
                slot = prev[len("mov "):prev.index("],") + 1]
                if text == f"mov rax, {slot}":
                    continue
                if text == f"mov rcx, {slot}":
                    out.append("    mov rcx, rax")
                    continue
        out.append(line)
    return out


def byte_list(text: str) -> str:
    data = list(text.encode("utf-8")) + [0]
    return ", ".join(str(b) for b in data)


class FunctionEmitter:
    def __init__(self, func: IRFunction, strings: list[str]) -> None:
        self.func = func
        self.strings = strings
        self.lines: list[str] = []
        self.slots: dict[str, int] = {}
        self.collect_slots()
        self.frame = (8 * len(self.slots) + 15) // 16 * 16

    def collect_slots(self) -> None:
        names: list[str] = list(self.func.params)

        def add(op: Operand | None) -> None:
            if isinstance(op, Var) and op.name not in names:
                names.append(op.name)

        for ins in self.func.body:
            if isinstance(ins, Move):
                add(ins.dst); add(ins.src)
            elif isinstance(ins, BinOp):
                add(ins.dst); add(ins.left); add(ins.right)
            elif isinstance(ins, UnOp):
                add(ins.dst); add(ins.operand)
            elif isinstance(ins, (JumpIfFalse, JumpIfTrue)):
                add(ins.cond)
            elif isinstance(ins, CallInstr):
                add(ins.dst)
                for a in ins.args:
                    add(a)
            elif isinstance(ins, ReturnInstr):
                add(ins.value)
            elif isinstance(ins, WriteInstr):
                add(ins.value)
            elif isinstance(ins, ReadInstr):
                add(ins.dst)
        self.slots = {n: 8 * (i + 1) for i, n in enumerate(names)}

    # ---------------------------------------------------------------- helpers

    def emit(self, text: str) -> None:
        self.lines.append(f"    {text}")

    def local_label(self, name: str) -> str:
        return f".L_{self.func.name}_{name}"

    def load(self, reg: str, op: Operand) -> None:
        if isinstance(op, IntConst):
            if op.value == 0:
                self.emit(f"xor {reg}, {reg}")
            else:
                self.emit(f"mov {reg}, {op.value}")
        elif isinstance(op, FloatConst):
            # a decimal travels as its 64 raw bits, like any other 8-byte value
            bits = struct.unpack("<q", struct.pack("<d", op.value))[0]
            self.emit(f"mov {reg}, {bits}")
        elif isinstance(op, StrConst):
            self.emit(f"lea {reg}, [rip + str_{op.index}]")
        else:
            self.emit(f"mov {reg}, [rbp - {self.slots[op.name]}]")

    def store(self, var: Var, reg: str = "rax") -> None:
        self.emit(f"mov [rbp - {self.slots[var.name]}], {reg}")

    # ------------------------------------------------------------------- body

    def generate(self) -> list[str]:
        name = sym(self.func.name)
        self.lines.append(f"    .globl {name}")
        self.lines.append(f"{name}:")
        self.emit("push rbp")
        self.emit("mov rbp, rsp")
        if self.frame:
            self.emit(f"sub rsp, {self.frame}")
        for i, param in enumerate(self.func.params):
            if i < len(ARG_REGS):
                self.emit(f"mov [rbp - {self.slots[param]}], {ARG_REGS[i]}")
            else:
                self.emit(f"mov rax, [rbp + {16 + 8 * (i - len(ARG_REGS))}]")
                self.emit(f"mov [rbp - {self.slots[param]}], rax")
        last = len(self.func.body) - 1
        for i, ins in enumerate(self.func.body):
            if i == last and isinstance(ins, ReturnInstr):
                # the epilogue follows at once, so no jump is needed
                if ins.value is not None:
                    self.load("rax", ins.value)
                continue
            self.instruction(ins)
        self.lines.append(f"{self.local_label('end')}:")
        self.emit("leave")
        self.emit("ret")
        return self.lines

    def instruction(self, ins: object) -> None:
        if isinstance(ins, Label):
            self.lines.append(f"{self.local_label(ins.name)}:")
        elif isinstance(ins, Jump):
            self.emit(f"jmp {self.local_label(ins.target)}")
        elif isinstance(ins, JumpIfFalse):
            self.load("rax", ins.cond)
            self.emit("test rax, rax")
            self.emit(f"jz {self.local_label(ins.target)}")
        elif isinstance(ins, JumpIfTrue):
            self.load("rax", ins.cond)
            self.emit("test rax, rax")
            self.emit(f"jnz {self.local_label(ins.target)}")
        elif isinstance(ins, Move):
            self.load("rax", ins.src)
            self.store(ins.dst)
        elif isinstance(ins, UnOp):
            self.load("rax", ins.operand)
            if ins.op == "neg":
                self.emit("neg rax")
            elif ins.op == "itof":
                self.emit("cvtsi2sd xmm0, rax")
                self.emit("movq rax, xmm0")
            elif ins.op == "fneg":
                self.emit("btc rax, 63")  # flip the sign bit
            else:
                self.emit("xor rax, 1")
            self.store(ins.dst)
        elif isinstance(ins, BinOp):
            self.binary(ins)
        elif isinstance(ins, CallInstr):
            self.call(ins)
        elif isinstance(ins, ReturnInstr):
            if ins.value is not None:
                self.load("rax", ins.value)
            self.emit(f"jmp {self.local_label('end')}")
        elif isinstance(ins, WriteInstr):
            self.load("rdi", ins.value)
            routine = {"int": "rt_print_int", "bool": "rt_print_bool",
                       "float": "rt_print_float"}.get(ins.ty, "rt_print_str")
            self.emit(f"call {routine}")
        elif isinstance(ins, ReadInstr):
            self.emit("call rt_read_int")
            self.store(ins.dst)
        else:
            raise AssertionError(f"unknown instruction {ins!r}")

    def binary(self, ins: BinOp) -> None:
        op = ins.op
        self.load("rax", ins.left)
        self.load("rcx", ins.right)
        if op.endswith("."):
            self.float_binary(op)
        elif op == "+":
            self.emit("add rax, rcx")
        elif op == "-":
            self.emit("sub rax, rcx")
        elif op == "*":
            self.emit("imul rax, rcx")
        elif op in ("/", "%"):
            self.emit("test rcx, rcx")
            self.emit("jz rt_div_zero")
            self.emit("cqo")
            self.emit("idiv rcx")
            if op == "%":
                self.emit("mov rax, rdx")
        else:
            self.emit("cmp rax, rcx")
            self.emit(f"{COMPARE_SET[op]} al")
            self.emit("movzx rax, al")
        self.store(ins.dst)

    def float_binary(self, op: str) -> None:
        self.emit("movq xmm0, rax")
        self.emit("movq xmm1, rcx")
        if op in FLOAT_ARITH:
            if op == "/.":
                self.emit("xorpd xmm2, xmm2")
                self.emit("ucomisd xmm1, xmm2")
                self.emit("je rt_div_zero")
            self.emit(f"{FLOAT_ARITH[op]} xmm0, xmm1")
            self.emit("movq rax, xmm0")
        else:
            operands, condition = FLOAT_COMPARE[op]
            self.emit(f"ucomisd {operands}")
            self.emit(f"{condition} al")
            self.emit("movzx rax, al")

    def call(self, ins: CallInstr) -> None:
        reg_args = ins.args[: len(ARG_REGS)]
        stack_args = ins.args[len(ARG_REGS):]
        pad = len(stack_args) % 2 == 1
        if pad:
            self.emit("sub rsp, 8")
        for arg in reversed(stack_args):
            self.load("rax", arg)
            self.emit("push rax")
        for reg, arg in zip(ARG_REGS, reg_args):
            self.load(reg, arg)
        self.emit(f"call {sym(ins.name)}")
        if stack_args:
            self.emit(f"add rsp, {8 * len(stack_args) + (8 if pad else 0)}")
        elif pad:
            self.emit("add rsp, 8")
        if ins.dst is not None:
            self.store(ins.dst)


# ---------------------------------------------------------------------- runtime

RUNTIME = r"""
# ---- runtime: talks to the Linux kernel directly (no C library) ----

    .globl _start
_start:
    call ken_main
    xor edi, edi
    mov eax, 60                 # exit(0)
    syscall

# print the decimal number whose 64 bits are in rdi (six digits after the point), then a new line
rt_print_float:
    push rbp
    mov rbp, rsp
    sub rsp, 48
    xor r8d, r8d                # r8 = 1 when the number is negative
    movq xmm0, rdi
    xorpd xmm1, xmm1
    ucomisd xmm0, xmm1
    jae 14f
    mov r8d, 1
    btc rdi, 63                 # work with the positive value
    movq xmm0, rdi
14:
    cvttsd2si r9, xmm0          # r9 = whole part
    cvtsi2sd xmm1, r9
    subsd xmm0, xmm1
    mov rax, 1000000
    cvtsi2sd xmm1, rax
    mulsd xmm0, xmm1
    cvtsd2si r10, xmm0          # r10 = six digits after the point
    cmp r10, 1000000
    jb 15f
    inc r9
    sub r10, 1000000
15:
    lea rsi, [rbp - 1]
    mov byte ptr [rsi], 10
    mov rax, r10
    mov ecx, 10
    mov r11d, 6
16:
    xor edx, edx
    div rcx
    add dl, 48
    dec rsi
    mov [rsi], dl
    dec r11d
    jnz 16b
    dec rsi
    mov byte ptr [rsi], 46      # the point
    mov rax, r9
17:
    xor edx, edx
    div rcx
    add dl, 48
    dec rsi
    mov [rsi], dl
    test rax, rax
    jnz 17b
    test r8d, r8d
    jz 18f
    dec rsi
    mov byte ptr [rsi], 45      # the minus sign
18:
    mov rdx, rbp
    sub rdx, rsi
    mov edi, 1
    mov eax, 1
    syscall
    leave
    ret

# print the signed number in rdi, then a new line
rt_print_int:
    push rbp
    mov rbp, rsp
    sub rsp, 48
    mov rax, rdi
    lea rsi, [rbp - 1]
    mov byte ptr [rsi], 10
    xor r8d, r8d                # r8 = 1 when the number is negative
    test rax, rax
    jns 1f
    neg rax
    mov r8d, 1
1:
    mov ecx, 10
2:
    xor edx, edx
    div rcx
    add dl, 48
    dec rsi
    mov [rsi], dl
    test rax, rax
    jnz 2b
    test r8d, r8d
    jz 3f
    dec rsi
    mov byte ptr [rsi], 45
3:
    mov rdx, rbp
    sub rdx, rsi
    mov edi, 1
    mov eax, 1                  # write(1, buffer, length)
    syscall
    leave
    ret

# print the zero-ended text whose address is in rdi, then a new line
rt_print_str:
    push rbp
    mov rbp, rsp
    mov rsi, rdi
    xor edx, edx
4:
    cmp byte ptr [rsi + rdx], 0
    je 5f
    inc rdx
    jmp 4b
5:
    mov edi, 1
    mov eax, 1
    syscall
    lea rsi, [rip + rt_newline]
    mov edx, 1
    mov edi, 1
    mov eax, 1
    syscall
    leave
    ret

# print the Kenyang word for true or false, then a new line
rt_print_bool:
    test rdi, rdi
    jz 6f
    lea rdi, [rip + rt_true_word]
    jmp rt_print_str
6:
    lea rdi, [rip + rt_false_word]
    jmp rt_print_str

# read one byte from the keyboard or a file: rax = byte, or -1 at the end
rt_getc:
    push rbp
    mov rbp, rsp
    sub rsp, 16
    mov qword ptr [rbp - 8], 0
    xor edi, edi
    lea rsi, [rbp - 8]
    mov edx, 1
    xor eax, eax                # read(0, buffer, 1)
    syscall
    cmp rax, 1
    jne 7f
    movzx rax, byte ptr [rbp - 8]
    leave
    ret
7:
    mov rax, -1
    leave
    ret

# read a signed whole number; returns it in rax
rt_read_int:
    push rbp
    mov rbp, rsp
    xor r8d, r8d                # r8 = value
    xor r9d, r9d                # r9 = 1 when there was a minus sign
8:
    call rt_getc
    cmp rax, -1
    je 12f
    cmp rax, 127                # bytes outside ASCII (such as a byte-order mark) are skipped
    ja 8b
    cmp rax, 32
    je 8b
    cmp rax, 9
    je 8b
    cmp rax, 10
    je 8b
    cmp rax, 13
    je 8b
    cmp rax, 45
    jne 10f
    mov r9d, 1
    call rt_getc
10:
    cmp rax, 48
    jb 12f
    cmp rax, 57
    ja 12f
    sub rax, 48
    imul r8, r8, 10
    add r8, rax
    call rt_getc
    jmp 10b
12:
    mov rax, r8
    test r9d, r9d
    jz 13f
    neg rax
13:
    leave
    ret

# division by zero: print a message on the error channel and stop
rt_div_zero:
    mov edi, 2
    lea rsi, [rip + rt_div_msg]
    mov edx, 32                 # length of the message below
    mov eax, 1
    syscall
    mov edi, 1
    mov eax, 60                 # exit(1)
    syscall

    .section .rodata
rt_newline:
    .byte 10
rt_true_word:
    .byte 116, 201, 155, 116, 201, 155, 112, 0
rt_false_word:
    .byte 110, 115, 101, 0
rt_div_msg:
    .ascii "runtime error: division by zero\n"
"""


def generate(program: IRProgram, clean_up: bool = True) -> str:
    return generate_with_stats(program, clean_up)[0]


def generate_with_stats(program: IRProgram, clean_up: bool = True) -> tuple[str, int, int]:
    """Return (assembly text, instructions before clean-up, instructions after)."""
    before = after = 0
    lines = [
        "# Generated by the Lower Kenyang compiler. Target: x86-64 Linux.",
        "    .intel_syntax noprefix",
        "    .text",
        "",
    ]
    for func in program.functions:
        body = FunctionEmitter(func, program.strings).generate()
        before += count_instructions(body)
        if clean_up:
            body = peephole(body)
        after += count_instructions(body)
        lines.extend(body)
        lines.append("")
    lines.append(RUNTIME.strip("\n"))
    lines.append("")
    lines.append("# ---- string constants of the program ----")
    for i, text in enumerate(program.strings):
        lines.append(f"str_{i}:")
        lines.append(f"    .byte {byte_list(text)}")
    lines.append("")
    lines.append('    .section .note.GNU-stack,"",@progbits')
    return "\n".join(lines) + "\n", before, after
