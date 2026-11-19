# How We Built a Compiler for a Programming Language Based on Lower Kenyang

**A plain-language explainer**
Course: Compiler Construction, Fall 2026

This document explains the whole project in simple words. It says what we built, how it works, and why we made each choice. Each part ends with a short line to remember. If you read it once, you can explain the project to someone else.

---

## 0. The Five-Minute Version

- We made a **programming language** whose keywords are **Lower Kenyang** words, the language of the Bayangi people of Cameroon.
- We made a **compiler** for it. A compiler is a program that reads a program written in our language and turns it into a file the computer can run.
- Only the **keywords** are Kenyang. The rest of the compiler is built the same way as any other compiler. This is why the project is possible.
- The compiler works in **seven steps**: Read, Shape, Check, Flatten, Trim, Write, Join.
- The output is a **real machine-code program** (an ELF executable). It does not need Python or any other helper to run.
- It handles **whole numbers, decimal numbers, true/false and text**, and it gives **warnings** about careless code.
- We tested it with **167 automated tests** and 14 example programs. The native program and a second, independent way of running the same program always give the same answer.

**Remember:** Kenyang words in, running program out, seven steps in between.

---

## 1. What We Built

| | |
|---|---|
| **Input** | A text file ending in `.ken`, written with Kenyang keywords |
| **Output** | A program that runs on a computer (x86-64 Linux machine code) |
| **Written in** | Python 3.14, with the Lark library for reading the text |
| **Run on** | Windows, using WSL (Windows Subsystem for Linux) for the last two steps |

Here is a program in our language and what it prints:

```text
kʉ factorial(pɨ n) : pɨ {
    yat (n <= 1) {
        piti 1;
    } rɔ {
        piti n * factorial(n - 1);
    }
}

kʉ main() : ngwɔ {
    pɨ ans = factorial(5);
    sɔ(ans);
}
```

Output: `120`

The same program can be typed with plain English-keyboard letters, because many people do not have the Kenyang letters on their keyboard:

```text
kuh factorial(pih n) : pih {
    yat (n <= 1) {
        piti 1;
    } roh {
        piti n * factorial(n - 1);
    }
}
```

Both spellings make exactly the same program.

---

## 2. The Idea Behind a Compiler

A computer processor does not understand words like `if` or `while`. It only understands very small instructions made of numbers, such as "add these two numbers" or "jump to this place". This is called **machine code**.

People cannot write long programs in machine code. So we write in a **language people can read**, and a **compiler** translates it for the computer.

Think of a translator at a meeting. One person speaks Kenyang. The listener only understands numbers. The translator cannot translate everything in one go. The translator must first split the speech into words, then understand the sentence, then check it makes sense, then find a simple way to say it, then say it in the other language.

A compiler does the same, step by step. Each step has one small job. This is the main idea of the course: **break one big problem into small steps, and give each step a clear input and output.**

**Remember:** a compiler is a translator that works in small steps.

---

## 3. Why the Kenyang Part Is Small

Many people think "a programming language in a native tongue" must be very hard. It is not, for three reasons.

1. **The Kenyang part is a word list.** The compiler has a table with one Kenyang word for each idea: if, else, while, return, and so on. The table is the file `keywords.json`. After the compiler reads a word and finds its meaning in the table, it no longer cares which language the word came from.
2. **The steps are small and separate.** One member can work on one step without knowing the details of the others.
3. **The method is old and proven.** Compilers have been built this way for fifty years. We followed a known recipe.

Here are some of the words we use:

| Idea | Kenyang | ASCII spelling |
|---|---|---|
| whole number | `pɨ` | `pih` |
| true | `tɛtɛp` | `tehtehp` |
| false | `nse` | `nse` |
| if | `yat` | `yat` |
| else | `rɔ` | `roh` |
| while | `kʉ_te` | `kuh_te` |
| function | `kʉ` | `kuh` |
| return | `piti` | `piti` |
| write | `sɔ` | `soh` |
| read | `pay` | `pay` |
| and / or / not | `ne` / `kɛ` / `ka` | `ne` / `keh` / `ka` |

The full list has 70 words. They come from published Lower Kenyang sources, listed in `docs/kenyang-research-dossier.md`. The compiler uses 22 of them in this version. 12 more are kept aside (reserved) for later use. The others are free to use as names.

Two small choices help the people who write programs:

- **Two spellings.** Every word has a Kenyang spelling and an ASCII spelling. The compiler treats them as the same.
- **Tone marks do not matter.** Kenyang is a tonal language, and tone marks are rarely typed. The lexer removes tone marks from keywords before it looks them up, so `sɔ́` and `sɔ` are the same word.

**Remember:** Kenyang is the dictionary. The compiler is standard.

---

## 4. What the Language Can Do

| Feature | What you can write |
|---|---|
| Data | whole numbers, decimal numbers, true/false, text |
| Variables | `pɨ x = 5;`, `pɨ_kati y = 2.5;`, or let the compiler find the type with `ŋati x = 5;` |
| Calculation | `+ - * / %` with the usual order (`*` before `+`). Whole numbers and decimals can be mixed: the whole number is turned into a decimal first |
| Comparison | `== != < <= > >=` |
| Logic | `ne` (and), `kɛ` (or), `ka` (not). The right side is skipped when the left side already decides the answer |
| Choice | `yat` ... `rɔ_yat` ... `rɔ` (if, else if, else) |
| Repeat | `kʉ_te` (while) and `pay_te` (for), with `kati` (break) and `chak` (continue) |
| Functions | with inputs and one output, calling each other, calling themselves |
| Input and output | `sɔ(x);` prints, `pay(x);` reads a number |

**What it cannot do yet:** arrays, joining or comparing text. See section 10.

### Three extras that go beyond the basics

1. **Decimal numbers.** `pɨ_kati` is a decimal number (a 64-bit floating-point number, the same kind the processor uses). A whole number can be used wherever a decimal is expected: `pɨ_kati x = 3;` is fine, and `2 * 1.5` is `3.0`. The other way round is an error, because it would lose the part after the point. Decimals are printed with six digits after the point.
2. **Warnings.** Some code is legal but probably a mistake. The compiler still builds the program and prints a warning: a variable that is never used, and code after a `piti`, `kati` or `chak` that can never run. A name starting with `_` is never reported as unused.
3. **Assembly clean-up.** After the code generator finishes, a small pass removes loads that are not needed. The code generator keeps every answer in a stack box, and the next instruction often loads the same box straight back. The value is still in the register, so the load can go. On `loops.ken` this removes 13 of 120 instructions.

---

## 5. The Seven Steps

```text
  .ken file
     |
     v
 1. READ     (lexer)       text            ->  tokens
 2. SHAPE    (parser)      tokens          ->  syntax tree
 3. CHECK    (semantic)    syntax tree     ->  checked tree
 4. FLATTEN  (IR)          checked tree    ->  simple steps
 5. TRIM     (optimiser)   simple steps    ->  fewer simple steps
 6. WRITE    (code gen)    simple steps    ->  assembly text
 7. JOIN     (as and ld)   assembly text   ->  running program
```

Each step only sees the output of the step before it. This is why the team could work in parallel: once the shape of the hand-over is agreed (a token list, a tree, a list of simple steps), each person can build and test their part alone.

Steps 1 to 3 understand the **Kenyang program**. Steps 4 to 7 build the **machine program**. The simple steps in the middle (step 4) are the bridge between the two halves.

**Remember:** Read, Shape, Check, Flatten, Trim, Write, Join.

---

## 6. One Program Through All Seven Steps

We follow the smallest useful program, `examples/journey.ken`:

```text
kʉ main() : ngwɔ {
    pɨ x = 2 + 3 * 4;
    sɔ(x);
}
```

You can see every stage below yourself with `python -m src.compiler examples/journey.ken --emit <stage>`.

### Step 1: Read (tokens)

The text is cut into small labelled pieces called **tokens**:

```text
 2:1    KW_FUNC       'kʉ'
 2:4    IDENT         'main'
 3:5    KW_INT        'pɨ'
 3:8    IDENT         'x'
 3:10   ASSIGN        '='
 3:12   INT_LIT       '2'
 3:14   PLUS          '+'
 3:16   INT_LIT       '3'
 3:18   STAR          '*'
 3:20   INT_LIT       '4'
 3:21   SEMI          ';'
 ...
```

Each token knows its line and column. This is how error messages can point to the exact place.

### Step 2: Shape (syntax tree)

The tokens are checked against the grammar and arranged in a tree. The tree shows what belongs together. Here `3 * 4` sits lower in the tree than `+`, so it is calculated first:

```text
VarDecl  x
  Binary  +
    IntLit  2
    Binary  *
      IntLit  3
      IntLit  4
```

### Step 3: Check (meaning)

The compiler checks that the program makes sense. `x` is declared. `2`, `3` and `4` are numbers, so `+` and `*` are allowed. It writes the type `int` on every part of the tree.

### Step 4: Flatten (simple steps)

The tree becomes a flat list. Each line does one small thing. Names like `t1` are temporary boxes:

```text
t1 = 3 * 4
t2 = 2 + t1
x = t2
write x : int
return
```

### Step 5: Trim (optimise)

The compiler sees that `3 * 4` and `2 + 12` never change, so it calculates them now, once, instead of every time the program runs:

```text
write 14 : int
return
```

Five lines became two.

### Step 6: Write (assembly)

Each simple step becomes processor instructions, written as readable text. This is the result of the **unoptimised** version, which shows the work more clearly:

```text
    mov rax, 3
    mov rcx, 4
    imul rax, rcx          # 3 * 4
    mov [rbp - 8], rax     # keep the answer in a box on the stack
    mov rax, 2
    mov rcx, [rbp - 8]
    add rax, rcx           # 2 + 12
    ...
    call rt_print_int      # print the number
```

The optimised version is only `mov rdi, 14` and `call rt_print_int`.

### Step 7: Join (machine code)

Two ready-made tools finish the job. `as` (the assembler) turns the text into numbers. `ld` (the linker) puts the pieces together into one file. If we open the file with a disassembler, we see real machine instructions with their addresses:

```text
401008: mov    rax,0x3
40100f: mov    rcx,0x4
401016: imul   rax,rcx
...
```

Run the file and it prints `14`.

---

## 7. Each Step in Detail

### Step 1. Read: the Lexer (`src/lexer.py`, `grammar/kenyang.lark`)

- **Job:** cut the text into tokens.
- **Why it is needed:** the rest of the compiler cannot work with loose characters. It needs words, numbers and symbols, each with a label.
- **How it works:** the Lark library matches the text against patterns (a number looks like digits, a word looks like letters). Then each word is looked up in the keyword table. If it is there, it becomes a keyword token. If not, it is a name chosen by the programmer.
- **Our choices:**
  - Keywords are looked up **after** tone marks are removed.
  - On a bad character the lexer reports the error and **keeps going**, so all mistakes are shown in one run.
  - Names must use plain English letters. Kenyang letters are allowed in keywords and text only. This avoids confusion between two names that look the same.
- **A mistake it catches:** `pɨ x = 5 @ 3;` gives `Unexpected character '@'` with the line and column.

### Step 2. Shape: the Parser (`src/parser.py`, `src/ast_nodes.py`)

- **Job:** check the order of tokens and build the syntax tree.
- **Why it is needed:** `2 + 3 * 4` is only a list of five tokens. The compiler must know that the multiplication comes first.
- **How it works:** it is a **recursive descent parser**. There is one small function for each grammar rule. Rules for weaker operators call rules for stronger ones, so the strong ones end up lower in the tree:
  `or` calls `and`, which calls `==`, which calls `<`, which calls `+`, which calls `*`, which calls `-x`, which calls a number or a bracket.
- **Our choices:**
  - We wrote the parser **by hand**, not with a tool, so we can explain every line and control the error messages.
  - After an error, the parser **skips to the next `;` or `}`** and continues. One missing semicolon does not hide the rest of the errors.
  - A missing `;` is reported **at the end of the line that lacks it**, not at the start of the next line.
  - Every tree node stores its line and column.
- **A mistake it catches:** `pɨ x = 5` (no semicolon) gives `expected ';' after the declaration`.

### Step 3. Check: the Semantic Analyser (`src/semantic.py`)

- **Job:** check that the program makes sense, not just that its shape is right.
- **Why it is needed:** `pɨ x = "hello";` has a perfect shape but no meaning. Without this step the compiler would build a broken program.
- **How it works:** it keeps a **symbol table**, a list of every name and its type, one list per block. It walks the tree and checks:
  - every name is declared before it is used;
  - both sides of an operator have the right type;
  - a function call has the right number and type of inputs;
  - a function with an output returns a value on every path;
  - `kati` and `chak` are only inside loops.
- **Our choices:**
  - Every variable gets a **unique name** (`x`, then `x.1` if an inner block reuses `x`), so later steps never confuse two variables.
  - When a name is wrong, the compiler suggests the closest known name: `'cuont' is not declared. Did you mean 'count'?`
  - After one error in an expression, the expression gets the type `error`, so one mistake does not cause ten more messages.
  - Decimal rules: a whole number may widen to a decimal; a decimal may never narrow to a whole number; `%` needs two whole numbers.
  - It also collects **warnings** (never-used variables and unreachable code). Warnings do not stop the build.
- **A mistake it catches:** `sɔ(add(1));` when `add` needs two inputs.

### Step 4. Flatten: Intermediate Code (`src/ir.py`)

- **Job:** turn the tree into a flat list of tiny steps (**three-address code**: each step has at most one operator and two inputs).
- **Why it is needed:** the machine has no trees, no `while` and no `if`. It only has small instructions and jumps. This step is the bridge. It is also the form the optimiser works best on, and it lets us run the program in two different ways.
- **How it works:**
  - A calculation gets one step per operator, with temporary names.
  - `if` and loops become **labels and jumps**. For example, `while (c) { body }` becomes: label `start`, "if `c` is false go to `end`", the body, "go to `start`", label `end`.
  - `ne` and `kɛ` become jumps too. This is how the right side is skipped when the left side already decides the answer.
  - Text constants are kept in one table, so the same text is stored once.
  - When a whole number meets a decimal, an `itof` step ("integer to float") is added. Decimal calculations use operators with a dot (`+.`, `*.`, `<.`) so nobody confuses them with whole-number calculations.
- **Why not go straight from the tree to machine code?** It would put two hard jobs in one place and make testing very hard. With this bridge, a person can read the simple steps and check them by hand.

### Step 5. Trim: the Optimiser (`src/optimiser.py`)

- **Job:** make the simple steps shorter without changing what the program does.
- **Why it is needed:** the flattening step creates many extra steps. Real compilers always clean them up. This is also a good part of the course to show.
- **How it works:** it repeats four ideas until nothing changes:
  1. **Constant folding:** `3 * 4` becomes `12` now, not when the program runs.
  2. **Passing values forward:** if `x` is known to be `5`, use `5` where `x` is used.
  3. **Dead code removal:** delete steps whose result is never used, and code after a `return`. A branch like `yat (nse) { ... }` that can never run is deleted.
  4. **Jump clean-up:** remove a jump to the next line and labels nobody uses.
- **Safety rules:**
  - Division by zero is **never** folded away, so the program still reports the error when it runs.
  - Calls are **never** deleted, because they may print something.
  - Numbers wrap at 64 bits, exactly like the processor, so a folded answer always equals the real answer.
- **A result:** for the factorial program, 14 steps become 10.
- **How we know it is safe:** a test runs every example with the optimiser on and off and checks the answers are the same.

### Step 6. Write: the Code Generator and Runtime (`src/codegen.py`)

- **Job:** turn each simple step into processor instructions.
- **How it works (kept simple on purpose):**
  - Every variable and every temporary gets its own **box on the stack** (a block of memory the function owns).
  - For each step, the generator loads the values into registers (`rax`, `rcx`), does the work, and stores the answer back in a box.
  - Functions follow the standard **System V calling rule**: the first six inputs go in registers `rdi, rsi, rdx, rcx, r8, r9`, extra inputs go on the stack, and the answer comes back in `rax`.
  - Decisions and loops become compare-and-jump instructions.
  - Division checks for zero first and stops with `runtime error: division by zero`. This is true for decimals as well.
  - **Decimal numbers** use the processor's SSE instructions (`addsd`, `mulsd`, `ucomisd` and others). A decimal is kept in its box as 8 raw bytes, like any other value, and is moved into a special register only to calculate.
  - A final **clean-up pass** (peephole pass) removes loads of a box that was just stored.
- **The runtime:** a small set of routines written in assembly. They print a whole number, print a decimal, print text, print `tɛtɛp` or `nse`, read a number, and exit. They talk **directly to the Linux kernel** (system calls), so we need no C library.
- **Our choices:**
  - **One box per variable** is not the fastest design, but it is easy to get right and easy to explain. Correctness first.
  - **x86-64** because it is what most computers use, and it is well documented.

### Step 7. Join: Assembler and Linker (`src/toolchain.py`)

- **Job:** turn the assembly text into a program.
- **How it works:** the compiler calls two standard tools, `as` and `ld`. On Windows it calls them through WSL. The result is an **ELF executable**, the standard program file format on Linux.
- **How we know it is real machine code:** the first four bytes of the file are `7F 45 4C 46` (the letters `ELF`), and a disassembler can read the instructions back.

### The second way to run: the Virtual Machine (`src/interpreter.py`)

This is not one of the seven steps. It is a small program that runs the simple steps directly. We built it for two reasons:

1. People without WSL can still run Kenyang programs (`--interpret`).
2. It gives the tests a **second, independent answer**. If the native program and the virtual machine ever disagree, we know there is a bug in one of them.

---

## 8. The Big Decisions and Why We Made Them

| Decision | What we chose | Why |
|---|---|---|
| Language to write the compiler in | Python | Quick to write and test, and every member can read it. The compiler is the project; speed of the compiler is not the goal. |
| Lexer | Lark | It handles UTF-8 (Kenyang letters) cleanly. |
| Parser | Written by hand (recursive descent) | We understand and explain every line. We control error messages and recovery. |
| What is the "Kenyang" part | The keywords | Keeps the project possible. Understanding free Kenyang sentences is a different, much harder field. |
| Spelling | Kenyang letters and an ASCII copy | Authentic, and also easy to type on any keyboard. |
| Tone marks | Ignored in keywords | They are rarely typed. They should not cause errors. |
| Names of variables | ASCII letters only | Avoids two names that look the same but use different Unicode characters. |
| Middle form | Three-address code | Easy to read, check and optimise. Splits the front half from the back half. |
| Target | x86-64 Linux | Real machine code that runs without any helper. |
| Running on Windows | Through WSL | Windows has no `as` or `ld`. WSL provides them and matches the calling rule we use. |
| Runtime | In assembly, direct system calls | No C library needed. Shows exactly how a program talks to the system. |
| Variables in code generation | One box on the stack each | Simple and correct. Faster designs (register allocation) are possible later. |
| Reserved words | 34 words reserved, 36 free | The extended words (like `a` and `te`) would otherwise take away common variable names. |
| Decimal numbers | 64-bit floating point, kept as raw bytes in the same boxes | One kind of box for every value keeps the code generator simple. The processor does the calculation. |
| Printing decimals | Six digits after the point, rounded the same way in the compiler and the virtual machine | The native program and the virtual machine must give the same text. |
| Warnings | Reported, but never stop the build | The program is legal, so it should still run. The programmer is told about the risk. |
| Assembly clean-up | One simple rule: drop a load right after a store of the same box | Safe to prove correct, and it shows a measurable gain. |
| Backup way to run | Virtual machine | Works without WSL. Doubles as a test partner. |
| Errors | Report many, keep going | Programmers fix all mistakes in one pass. |

---

## 9. How We Know It Works

**167 automated tests** run with one command: `python -m pytest`.

| Group | What it checks |
|---|---|
| Lexer (9) | All 70 keywords in both spellings, tone marks, errors and recovery |
| Parser (19) | Operator order, every statement, error recovery, tree shape |
| Semantic analyser (30) | Every type and scope rule, every error message, decimal rules, warnings |
| Intermediate code and optimiser (39) | The shape of the simple steps, every optimisation, decimal folding, same answer with and without optimising |
| End to end (70) | All 14 examples, run **four ways each**: optimised or not, native program or virtual machine. All four must print the same, correct answer. Also decimal printing, warnings and the assembly clean-up |

Other checks:

- Division by zero stops the native program with an error message and exit code 1.
- Reading negative and very large numbers works in the native program.
- The output file starts with the `ELF` marker.
- A test checks that every example in the folder has an expected answer, so no example is left untested.

If a computer has no WSL or `as`, the native tests are skipped and the virtual machine tests still run.

---

## 10. What the Compiler Cannot Do Yet

We say this clearly, because a compiler with honest limits is better than one with hidden ones.

- **Single characters** (`ɛyɔŋ`): the word is reserved, but the compiler answers "not supported in this version".
- **Decimal numbers:** no exponent form such as `1e5`. Printing shows six digits after the point and works up to about 9.2 followed by 18 zeros. Decimals cannot be read from the keyboard yet.
- **Arrays**, **structures** and **switch**: not built.
- **Text:** it can be stored, passed, returned and printed. It cannot be joined with `+` or compared with `==`.
- **Variables outside functions:** all variables are inside functions.
- **Speed:** the machine code is correct but not fast, because every value is kept in a box in memory.
- **Largest and smallest number:** dividing the smallest 64-bit number by `-1` is not handled.

Each of these is a clear next step for a future version.

---

## 11. Who Built What

| Area | Part | Files |
|---|---|---|
| 1 | Language design, 70-word Kenyang lexicon, lexer | `docs/language-spec.md`, `keywords.json`, `grammar/kenyang.lark`, `src/lexer.py`, `docs/kenyang-research-dossier.md` |
| 2 | Parser and syntax tree | `src/parser.py`, `src/ast_nodes.py`, `src/diagnostics.py` |
| 3 | Semantic analyser (with warnings) and optimiser | `src/semantic.py`, `src/optimiser.py` |
| 4 | Intermediate code, code generator, runtime, build tools, virtual machine, command line | `src/ir.py`, `src/codegen.py`, `src/toolchain.py`, `src/interpreter.py`, `src/compiler.py` |

Everyone should be able to explain all seven steps, not only their own area.

---

## 12. Questions the Lecturer May Ask

**What is a compiler?**
A program that translates a program from one language into another. Ours translates Kenyang-keyword programs into machine code.

**Is this a translator for Kenyang sentences?**
No. It is a programming language with fixed rules. Only the keywords are Kenyang.

**Why are there seven steps and not one?**
Each step has one small job and can be built and tested alone. One big step would be impossible to check.

**What is a token?**
One meaningful piece of the program: a keyword, a name, a number, a symbol.

**What is the difference between the parser and the semantic analyser?**
The parser checks the **shape** (is a semicolon missing?). The semantic analyser checks the **meaning** (are you adding a number to text?).

**What is a symbol table?**
A list of every name in the program with its type. We keep one list per block and search from the inside out.

**What is three-address code, and why use it?**
Simple steps with at most one operator each. It is the bridge between the Kenyang half and the machine half, and it is easy to check and optimise.

**How do you know the optimiser does not break programs?**
Every example runs with and without it, and the answers must match. The optimiser also never folds division by zero and never removes calls.

**How do `ne` and `kɛ` skip the right side?**
They become jumps in the simple steps. If the left side decides the answer, the jump skips the right side.

**How do you know the output is real machine code?**
It is an ELF file. A disassembler (`objdump`) shows the instructions, and it runs on its own without Python.

**Why do you need WSL?**
Windows has no assembler or linker in the form we use. WSL gives us Linux tools, and Linux is the system our machine code is written for.

**What happens if two keywords are spelled the same?**
`python -m src.lexer --check-keywords` checks the whole table for clashes. There are none.

**What if the program has a mistake?**
The compiler reports every mistake of the current step with line, column and a hint, and builds nothing.

**How do you handle decimal numbers?**
A decimal is a 64-bit floating-point number. A whole number is converted to a decimal when the two meet. The code generator uses the processor's own decimal instructions. The runtime has its own routine to print the number with six digits after the point.

**What is a warning, and how is it different from an error?**
An error means the program is wrong and nothing is built. A warning means the program is legal but probably careless, such as a variable that is never used. It is built, and the programmer is told.

**What is the assembly clean-up?**
A pass over the finished assembly. If an instruction stores a value in a box and the next instruction loads that same box, the load is removed, because the value is still in the register.

**What would you add next?**
Arrays, joining text, reading decimals, and putting more values in registers instead of memory boxes.

---

## 13. Glossary

| Word | Meaning |
|---|---|
| Compiler | A program that translates another program into a form the computer can run |
| Machine code | The numbers a processor runs directly |
| Assembly | Machine code written as readable text |
| Assembler (`as`) | Tool that turns assembly into machine code |
| Linker (`ld`) | Tool that joins pieces of machine code into one program file |
| ELF | The program file format used on Linux |
| Token | One piece of a program: keyword, name, number or symbol |
| Lexer | The step that cuts text into tokens |
| Grammar | The written rules for a correct program |
| Parser | The step that checks the grammar and builds the tree |
| Syntax tree | A diagram of how the parts of a program fit together |
| Recursive descent | A way to write a parser with one function per grammar rule |
| Semantic analysis | Checking that a program makes sense |
| Symbol table | A list of names and their types |
| Type | The kind of a value: number, truth value, text |
| Scope | The part of the program where a name can be used |
| Intermediate code | The flat list of simple steps between the tree and the machine code |
| Three-address code | Intermediate code where each step has at most one operator |
| Label and jump | A named place in the code, and an instruction to go to it |
| Optimiser | The step that makes the simple steps shorter |
| Constant folding | Working out a calculation of known numbers ahead of time |
| Dead code | Code that can never run, or whose result is never used |
| Register | A tiny, very fast storage place inside the processor |
| Stack | The block of memory a function uses for its own variables |
| Calling convention | The agreed rule for how functions pass inputs and outputs |
| Runtime | Helper routines every program needs, such as printing |
| System call | A request from a program to the operating system |
| Virtual machine | A program that runs the simple steps directly |
| Floating-point number | The computer's way of storing a decimal number in 64 bits |
| Widening | Turning a whole number into a decimal so the two can be used together |
| Warning | A message about code that is legal but probably a mistake. The build continues |
| Peephole pass | A small clean-up that looks at a few neighbouring instructions and removes waste |
| WSL | Windows Subsystem for Linux: Linux tools inside Windows |
| Tone mark | An accent that shows how a syllable is pitched in a tonal language |
| ASCII | The basic English-keyboard character set |
| UTF-8 | The way text files store letters from many languages |
