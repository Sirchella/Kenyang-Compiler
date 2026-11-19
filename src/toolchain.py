"""Calls the assembler and linker, and runs the finished program.

On Linux the tools are used directly. On Windows they are used through
Windows Subsystem for Linux (WSL), because the generated program is a Linux
executable.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


class ToolchainError(Exception):
    pass


def _prefix() -> list[str] | None:
    """Command prefix that runs a Linux command, or None if unavailable."""
    if sys.platform.startswith("linux"):
        if shutil.which("as") and shutil.which("ld"):
            return []
        return None
    if sys.platform == "win32" and shutil.which("wsl"):
        try:
            probe = subprocess.run(
                ["wsl", "--", "sh", "-c", "command -v as && command -v ld"],
                capture_output=True, timeout=60, stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return ["wsl"] if probe.returncode == 0 else None
    return None


def native_available() -> bool:
    return _prefix() is not None


def _run(prefix: list[str], directory: Path, args: list[str], stdin: bytes | None = None,
         ) -> subprocess.CompletedProcess[bytes]:
    if prefix:
        command = ["wsl", "--cd", str(directory), "--", *args]
        cwd = None
    else:
        command = args
        cwd = str(directory)
    # tools that are not given input must not read ours, or they would swallow it
    extra = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    return subprocess.run(command, capture_output=True, cwd=cwd, timeout=120, **extra)


def build(asm_path: Path, exe_path: Path) -> None:
    """Assemble `asm_path` and link it into the executable `exe_path`."""
    prefix = _prefix()
    if prefix is None:
        raise ToolchainError(
            "no assembler found. Install WSL with Ubuntu (Windows) or the binutils "
            "package (Linux), or use --interpret to run without one."
        )
    directory = asm_path.resolve().parent
    obj_name = exe_path.stem + ".o"
    steps = [
        ["as", asm_path.name, "-o", obj_name],
        ["ld", obj_name, "-o", exe_path.name],
    ]
    for step in steps:
        done = _run(prefix, directory, step)
        if done.returncode != 0:
            raise ToolchainError(
                f"'{step[0]}' failed:\n" + done.stderr.decode("utf-8", errors="replace")
            )
    obj = directory / obj_name
    if obj.exists():
        obj.unlink()


def run_interactive(exe_path: Path) -> int:
    """Run a built program with the keyboard and screen of this terminal."""
    prefix = _prefix()
    if prefix is None:
        raise ToolchainError("cannot run a Linux executable here")
    directory = exe_path.resolve().parent
    try:
        stdin = sys.stdin.fileno()
    except (OSError, ValueError, AttributeError):
        stdin = None  # no usable keyboard or pipe (for example inside a test)
    if prefix:
        command = ["wsl", "--cd", str(directory), "--", "./" + exe_path.name]
        return subprocess.run(command, stdin=stdin).returncode
    return subprocess.run(["./" + exe_path.name], cwd=str(directory), stdin=stdin).returncode


def run_executable(exe_path: Path, stdin: str = "") -> tuple[int, str, str]:
    """Run a built program. Returns (exit code, output, error output)."""
    prefix = _prefix()
    if prefix is None:
        raise ToolchainError("cannot run a Linux executable here")
    directory = exe_path.resolve().parent
    done = _run(prefix, directory, ["./" + exe_path.name], stdin.encode("utf-8"))
    return (
        done.returncode,
        done.stdout.decode("utf-8", errors="replace"),
        done.stderr.decode("utf-8", errors="replace"),
    )
