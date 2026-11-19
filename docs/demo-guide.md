# Demonstration Guide

A step-by-step script for showing the compiler to the lecturer. The whole demonstration takes about ten minutes. Every command was run before writing this guide, and the output shown is the real output.

All commands are run from the project folder in PowerShell. WSL (Ubuntu) must be installed for the native steps.

---

## 0. Before the Demonstration

```powershell
pip install -r requirements.txt
python -m pytest -q
```

Expected: `167 passed`. If this passes, everything below will work.

Folder for generated files (the compiler writes the program and its assembly next to the name given with `-o`):

```powershell
mkdir build
```

---

## 1. The Language (1 minute)

Open `examples/factorial_utf8.ken` and `examples/factorial_ascii.ken` side by side.

Say: the keywords are Lower Kenyang words. Every word has a Kenyang spelling and an ASCII spelling, and both make the same program. The word list is `keywords.json` (70 words from published sources).

```powershell
python -m src.lexer --check-keywords
```

Expected: `OK: 70 keywords validated with 0 collisions.`

---

## 2. A Program Through Every Step (4 minutes)

Use `examples/journey.ken`:

```text
kʉ main() : ngwɔ {
    pɨ x = 2 + 3 * 4;
    sɔ(x);
}
```

**Step 1, tokens:**
```powershell
python -m src.compiler examples/journey.ken --emit tokens
```
Say: the text is cut into labelled pieces, each with its line and column.

**Step 2 and 3, syntax tree with types:**
```powershell
python -m src.compiler examples/journey.ken --emit ast
```
Say: `3 * 4` sits lower than `+`, so it is calculated first. Every part has its type.

**Step 4, simple steps:**
```powershell
python -m src.compiler examples/journey.ken --emit ir
```
Expected:
```text
function main() : void
    t1 = 3 * 4
    t2 = 2 + t1
    x = t2
    write x : int
    return
```

**Step 5, after the optimiser:**
```powershell
python -m src.compiler examples/journey.ken --emit ir-opt --stats
```
Expected: `write 14 : int` and `return`. Say: the compiler worked out `2 + 3 * 4` before the program runs.

**Step 6, assembly:**
```powershell
python -m src.compiler examples/journey.ken --no-opt --emit asm
```
Say: these are real processor instructions as text. `imul` multiplies, `add` adds, and `call rt_print_int` prints.

**Step 7, build and run the real program:**
```powershell
python -m src.compiler examples/journey.ken -o build/journey --run
```
Expected: `14`

Show that it is real machine code:
```powershell
wsl -- bash -c "cd build && file journey && objdump -d -M intel --no-show-raw-insn journey | head -30"
```
Say: this is an ELF program. It does not use Python. The instructions shown are the ones the processor runs.

---

## 3. Bigger Programs (2 minutes)

```powershell
python -m src.compiler examples/factorial_utf8.ken -o build/fact --run
python -m src.compiler examples/fibonacci.ken -o build/fib --run
python -m src.compiler examples/prime_check.ken -o build/prime --run
python -m src.compiler examples/loops.ken -o build/loops --run
python -m src.compiler examples/logic.ken -o build/logic --run
```

Expected outputs: `120`; the first ten Fibonacci numbers (0 to 34); `prime`; `16` and `111`; and the five lines of the logic example (the right side of `ne` and `kɛ` is not run when the left side already decides).

Input from the keyboard:
```powershell
echo 12 -5 | python -m src.compiler examples/input_sum.ken -o build/sum --run
```
Expected: `7` and `-60`.

Optimiser effect on the factorial program:
```powershell
python -m src.compiler examples/factorial_utf8.ken --emit ir-opt --stats
```
Expected: `14 instructions before, 10 after, 4 removed`.

---

## 3b. Decimal Numbers (1 minute)

```powershell
python -m src.compiler examples/decimals.ken -o build/decimals --run
```

Expected: `3.250000`, `-1.500000`, `tɛtɛp`, `8.500000`, `12.566360`, `1.000000`, `0.333333`, `-7.500000`, `7.000000`.

Say: whole numbers and decimals can be mixed, and the whole number is converted first. Show the conversion step:

```powershell
python -m src.compiler examples/decimals.ken --emit ir
```

Look for `itof` and the operators with a dot, such as `*.`.

---

## 4. The Compiler Finds Mistakes (2 minutes)

**Spelling and symbol mistakes (lexer):**
```powershell
python -m src.compiler examples/errors/lex_error.ken
```
Expected: two errors, `Unexpected character '@'` and `Unterminated string literal`, each with line and column.

**Shape mistakes (parser):**
```powershell
python -m src.compiler examples/errors/syntax_error.ken
```
Expected: three errors: the missing `;`, the missing `)`, and the missing value. The parser keeps going after each one.

**Meaning mistakes (semantic analyser):**
```powershell
python -m src.compiler examples/errors/semantic_error.ken
```
Expected: six errors, including `'cuont' is not declared` with `hint: Did you mean 'count'?`, a function that may not return a value, a wrong number of arguments, and a type mismatch.

Say: nothing is built when there is an error, and every error of a step is shown at once.

**Warnings (code that is legal but careless):**
```powershell
python -m src.compiler examples/errors/warnings.ken --interpret
```
Expected: two warnings (`this code can never run` and `variable 'spare' is never used`), then the program still runs and prints `2`.

**Assembly clean-up:**
```powershell
python -m src.compiler examples/loops.ken --emit ir-opt --stats
```
Expected on the error stream: `assembly clean-up: 120 instructions before, 107 after, 13 removed`.

---

## 5. The Two Ways to Run Agree (1 minute)

```powershell
python -m src.compiler examples/arithmetic.ken --interpret
python -m src.compiler examples/arithmetic.ken -o build/arith --run
python -m src.compiler examples/arithmetic.ken --no-opt -o build/arith2 --run
```

Expected: the same eleven lines each time, including `-3` and `-2` for `-17 / 5` and `-17 % 5`, and `-9223372036854775808` at the edge of the number range.

Say: the virtual machine, the optimised program and the unoptimised program always agree. This is the main idea behind the tests.

---

## 6. Closing (30 seconds)

- Seven steps, each with one job: Read, Shape, Check, Flatten, Trim, Write, Join.
- 167 automated tests.
- Limits: no arrays, character type, or text joining yet (section 10 of `docs/project-explainer.md`).

---

## If Something Goes Wrong

| Problem | Fix |
|---|---|
| `no assembler found` | Install WSL with Ubuntu: `wsl --install -d Ubuntu`. Then run again. Or add `--interpret` to run without it. |
| `ModuleNotFoundError: lark` | Run `pip install -r requirements.txt`. |
| Kenyang letters look broken in the terminal | Use Windows Terminal, or open the `.ken` file in an editor. The ASCII spelling always works. |
| `build` folder missing | Run `mkdir build` first. |
