from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Callable, List, Optional

MAX_CAPTURE_BYTES = 512 * 1024  # 512 KB maximum buffer for stdout/stderr capture


@dataclass
class ExecutionResult:
    """Structured execution metadata returned by the runner."""
    command: List[str]
    cwd: str
    started_at: str
    ended_at: str
    duration_ms: float
    exit_code: int
    interrupted: bool
    stdout: str
    stderr: str
    error_message: Optional[str] = None


class CommandRunner:
    """
    Executes a process, streams output to stdout/stderr in real-time,
    bounds captured evidence in memory, and handles interrupts/termination safely.
    """

    def __init__(
        self,
        max_capture_bytes: int = MAX_CAPTURE_BYTES,
        stdout_sink: Optional[Callable[[str], None]] = None,
        stderr_sink: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.max_capture_bytes = max_capture_bytes
        self.stdout_sink = stdout_sink or (lambda s: sys.stdout.write(s) and sys.stdout.flush())
        self.stderr_sink = stderr_sink or (lambda s: sys.stderr.write(s) and sys.stderr.flush())

    def _stream_pipe(
        self,
        pipe: IO[bytes],
        sink: Callable[[str], None],
        buffer: bytearray,
        lock: threading.Lock,
    ) -> None:
        """Read from raw byte pipe, forward decoded text to terminal sink, and append to bounded buffer."""
        try:
            for chunk in iter(lambda: pipe.read(1024), b""):
                text = chunk.decode("utf-8", errors="replace")
                try:
                    sink(text)
                except Exception:
                    pass

                with lock:
                    if len(buffer) < self.max_capture_bytes:
                        space = self.max_capture_bytes - len(buffer)
                        buffer.extend(chunk[:space])
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def run(
        self,
        command: List[str],
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
    ) -> ExecutionResult:
        """
        Execute command with argument list, stream output, and capture structured metadata.
        """
        if not command:
            raise ValueError("Command list cannot be empty.")

        resolved_cwd = str(cwd.resolve()) if cwd else os.getcwd()
        started_at = datetime.now(timezone.utc).isoformat()
        start_mono = time.monotonic()

        stdout_buf = bytearray()
        stderr_buf = bytearray()
        lock = threading.Lock()
        interrupted = False
        exit_code = -1
        error_message: Optional[str] = None

        proc: Optional[subprocess.Popen[bytes]] = None

        # Cross-platform creation flags for process group handling
        creationflags = 0
        preexec_fn = None
        if sys.platform == "win32":
            # CREATE_NEW_PROCESS_GROUP allows sending CTRL_BREAK_EVENT if needed
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            preexec_fn = os.setsid

        try:
            proc = subprocess.Popen(
                command,
                cwd=resolved_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                bufsize=0,
                creationflags=creationflags,
                preexec_fn=preexec_fn,
                env=env,
            )
        except FileNotFoundError as exc:
            end_mono = time.monotonic()
            ended_at = datetime.now(timezone.utc).isoformat()
            duration_ms = (end_mono - start_mono) * 1000
            return ExecutionResult(
                command=command,
                cwd=resolved_cwd,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=round(duration_ms, 2),
                exit_code=127,
                interrupted=False,
                stdout="",
                stderr="",
                error_message=f"Executable not found: {command[0]} ({exc})",
            )
        except PermissionError as exc:
            end_mono = time.monotonic()
            ended_at = datetime.now(timezone.utc).isoformat()
            duration_ms = (end_mono - start_mono) * 1000
            return ExecutionResult(
                command=command,
                cwd=resolved_cwd,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=round(duration_ms, 2),
                exit_code=126,
                interrupted=False,
                stdout="",
                stderr="",
                error_message=f"Permission denied executing: {command[0]} ({exc})",
            )
        except Exception as exc:
            end_mono = time.monotonic()
            ended_at = datetime.now(timezone.utc).isoformat()
            duration_ms = (end_mono - start_mono) * 1000
            return ExecutionResult(
                command=command,
                cwd=resolved_cwd,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=round(duration_ms, 2),
                exit_code=1,
                interrupted=False,
                stdout="",
                stderr="",
                error_message=f"Failed to launch command: {exc}",
            )

        t_out = threading.Thread(
            target=self._stream_pipe,
            args=(proc.stdout, self.stdout_sink, stdout_buf, lock),
            daemon=True,
        )
        t_err = threading.Thread(
            target=self._stream_pipe,
            args=(proc.stderr, self.stderr_sink, stderr_buf, lock),
            daemon=True,
        )
        t_out.start()
        t_err.start()

        try:
            exit_code = proc.wait()
        except KeyboardInterrupt:
            interrupted = True
            self._terminate_process(proc)
            try:
                exit_code = proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                exit_code = proc.wait()
            # Standard exit code on SIGINT
            if exit_code == 0 or exit_code is None:
                exit_code = 130

        # Wait for streamer threads to complete flushing
        t_out.join(timeout=1.0)
        t_err.join(timeout=1.0)

        end_mono = time.monotonic()
        ended_at = datetime.now(timezone.utc).isoformat()
        duration_ms = (end_mono - start_mono) * 1000

        stdout_str = stdout_buf.decode("utf-8", errors="replace")
        stderr_str = stderr_buf.decode("utf-8", errors="replace")

        return ExecutionResult(
            command=command,
            cwd=resolved_cwd,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=round(duration_ms, 2),
            exit_code=exit_code if exit_code is not None else 1,
            interrupted=interrupted,
            stdout=stdout_str,
            stderr=stderr_str,
            error_message=error_message,
        )

    def _terminate_process(self, proc: subprocess.Popen[bytes]) -> None:
        """Safely terminate child process across Windows and POSIX."""
        if proc.poll() is not None:
            return

        if sys.platform == "win32":
            try:
                # Use taskkill to cleanly terminate child process tree on Windows
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
        else:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
