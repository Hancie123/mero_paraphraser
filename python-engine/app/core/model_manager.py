"""Owns the local AI model: download, verification, llama-server and completions.

The runtime (llama.cpp) and model are downloaded once, with SHA-256
verification and resume, into ``config.ai_home()``; a release installer copies
them there instead. ``llama-server`` then runs on a random localhost port and is
tied to this process (a Windows job object) so it never outlives the app.

Standard library only, so the engine still bundles with PyInstaller.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from ..schemas.paraphrase import ParaphraseError
from . import config
from .config import DOWNLOADS, MODEL, RUNTIME

_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class _Cancelled(Exception):
    pass


class ModelManager:
    def __init__(self) -> None:
        # download state
        self._dl_lock = threading.Lock()
        self._dl_thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._dl_state = "idle"  # idle | downloading | verifying | error
        self._dl_message = ""
        self._dl_done = 0
        self._dl_total = sum(d.size for d in DOWNLOADS)
        # server state
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._port = 0
        self._ready = False
        self._job: object | None = None
        self._error = ""
        _migrate_legacy_home()
        atexit.register(self.stop)

    # ------------------------------------------------------------ files

    @staticmethod
    def server_exe() -> Path | None:
        if os.environ.get("MERO_LLAMA_SERVER"):
            p = Path(os.environ["MERO_LLAMA_SERVER"])
            return p if p.is_file() else None
        root = config.ai_home() / RUNTIME.target
        name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        return next(iter(root.rglob(name)), None) if root.is_dir() else None

    @staticmethod
    def model_path() -> Path:
        return config.local_model() or config.ai_home() / MODEL.target

    def installed(self) -> bool:
        model = self.model_path()
        if self.server_exe() is None or not model.is_file():
            return False
        if config.local_model():
            return True
        # A size check catches a truncated copy without hashing 2.5 GB on every start.
        return model.stat().st_size == MODEL.size

    def status(self) -> dict:
        with self._dl_lock:
            state = self._dl_state
            if state == "idle":
                state = "ready" if self.installed() else "missing"
            return {
                "state": state,  # missing | downloading | verifying | ready | error
                "model": config.MODEL_NAME,
                "size_bytes": self._dl_total,
                "done_bytes": self._dl_done if state in ("downloading", "verifying") else 0,
                "message": self._dl_message,
                "server": self.server_state(),
                "folder": str(config.ai_home()),
            }

    # ------------------------------------------------------------ download

    def start_download(self) -> dict:
        with self._dl_lock:
            if not (self._dl_thread and self._dl_thread.is_alive()):
                self._cancel.clear()
                self._dl_state, self._dl_message, self._dl_done = "downloading", "", 0
                self._dl_thread = threading.Thread(target=self._download_all, daemon=True)
                self._dl_thread.start()
        return self.status()

    def cancel_download(self) -> dict:
        self._cancel.set()
        return self.status()

    def remove(self) -> dict:
        with self._dl_lock:
            if self._dl_thread and self._dl_thread.is_alive():
                raise ParaphraseError("wait for the download to finish or cancel it first")
        self.stop()
        shutil.rmtree(config.ai_home(), ignore_errors=True)
        return self.status()

    def prepare(self, log=print) -> Path:
        """Download (if needed) and fully verify the runtime and model. Used by the release build."""
        with self._dl_lock:
            self._cancel.clear()
            self._dl_state, self._dl_message, self._dl_done = "downloading", "", 0
        stop = threading.Event()

        def report() -> None:
            while not stop.wait(5):
                log(f"  {self._dl_state} {self._dl_done / 1e9:.2f} of {self._dl_total / 1e9:.2f} GB")

        threading.Thread(target=report, daemon=True).start()
        try:
            self._download_all()
        finally:
            stop.set()
        if self._dl_state == "error":
            raise ParaphraseError(self._dl_message)
        log(f"Verifying {MODEL.name}...")
        if _sha256(self.model_path()) != MODEL.sha256:
            raise ParaphraseError(f"{self.model_path()} is corrupted; delete it and run again")
        if not self.installed():
            raise ParaphraseError("the AI runtime is incomplete; delete the ai folder and run again")
        return config.ai_home()

    def _download_all(self) -> None:
        try:
            base = 0
            for item in DOWNLOADS:
                target = config.ai_home() / item.target
                marker = target / ".complete" if item.extract else target
                if marker.exists():
                    base += item.size
                    with self._dl_lock:
                        self._dl_done = base
                    continue
                archive = self._fetch(item, base)
                if item.extract:
                    with zipfile.ZipFile(archive) as zf:  # extractall rejects ../ and absolute paths
                        zf.extractall(target)
                    (target / ".complete").write_text(item.sha256)
                    archive.unlink(missing_ok=True)
                base += item.size
            with self._dl_lock:
                self._dl_state, self._dl_message = "idle", ""
        except _Cancelled:
            with self._dl_lock:
                self._dl_state, self._dl_message = "idle", ""
        except Exception as exc:  # report to the UI; the partial file is kept for resume
            with self._dl_lock:
                self._dl_state, self._dl_message = "error", _friendly(exc)

    def _fetch(self, item, base: int) -> Path:
        """Download ``item`` to its final path (or a .zip next to it), resuming a .part file."""
        final = config.ai_home() / (item.target + ".zip" if item.extract else item.target)
        part = final.with_name(final.name + ".part")
        final.parent.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256()
        have = part.stat().st_size if part.exists() else 0
        if have > item.size:
            part.unlink()
            have = 0
        if have:
            with part.open("rb") as f:
                while block := f.read(1 << 20):
                    digest.update(block)

        if have < item.size:
            req = urllib.request.Request(item.url, headers={"User-Agent": "MeroParaphraser/0.1"})
            if have:
                req.add_header("Range", f"bytes={have}-")
            with urllib.request.urlopen(req, timeout=30) as resp:
                if have and resp.status != 206:  # server ignored Range: start over
                    have, digest = 0, hashlib.sha256()
                with part.open("ab" if have else "wb") as out:
                    while True:
                        if self._cancel.is_set():
                            raise _Cancelled
                        block = resp.read(1 << 20)
                        if not block:
                            break
                        out.write(block)
                        digest.update(block)
                        have += len(block)
                        with self._dl_lock:
                            self._dl_done = base + have

        with self._dl_lock:
            self._dl_state = "verifying"
        if digest.hexdigest() != item.sha256:
            part.unlink(missing_ok=True)
            raise ParaphraseError(f"the {item.name} download was corrupted; please try again")
        os.replace(part, final)
        with self._dl_lock:
            self._dl_state = "downloading"
        return final

    # ------------------------------------------------------------ server

    def server_state(self) -> str:
        if self._proc and self._proc.poll() is None:
            return "running" if self._ready else "starting"
        return "error" if self._error else "stopped"

    def warm(self) -> dict:
        """Start loading the model in the background so the first request is fast."""
        if self.installed() and self.server_state() in ("stopped", "error"):
            try:
                with self._lock:
                    self._error = ""
                    self._spawn()  # so status() reports "starting" right away
            except Exception as exc:
                self._error = str(exc)
            else:
                threading.Thread(target=self._ensure_quietly, daemon=True).start()
        return self.status()

    def _ensure_quietly(self) -> None:
        try:
            self.ensure()
        except Exception:
            pass

    def ensure(self) -> int:
        """Start llama-server if needed and wait until the model is loaded; returns its port."""
        with self._lock:
            if self._proc and self._proc.poll() is None and self._ready:
                return self._port
            if not (self._proc and self._proc.poll() is None):
                self._spawn()
            deadline = time.monotonic() + config.STARTUP_TIMEOUT
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    self._error = "The AI model stopped while loading. " + self._log_tail()
                    raise ParaphraseError(self._error)
                try:
                    with _NO_PROXY.open(f"http://127.0.0.1:{self._port}/health", timeout=2) as r:
                        if r.status == 200:
                            self._ready, self._error = True, ""
                            return self._port
                except (urllib.error.URLError, OSError):
                    pass
                time.sleep(0.25)
            self._stop_locked()
            self._error = "The AI model took too long to load."
            raise ParaphraseError(self._error)

    def _spawn(self) -> None:
        exe, model = self.server_exe(), self.model_path()
        if exe is None or not model.is_file():
            raise ParaphraseError("the AI model is not installed")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self._port = s.getsockname()[1]
        config.ai_home().mkdir(parents=True, exist_ok=True)
        log = (config.ai_home() / "llama-server.log").open("wb")
        flags = 0x0800_0000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        self._proc = subprocess.Popen(
            [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(self._port),
             "-c", str(config.CONTEXT_TOKENS), "-np", "1"],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            cwd=str(exe.parent), creationflags=flags,
        )
        log.close()
        self._ready = False
        self._job = _kill_with_parent(self._proc)

    def _log_tail(self) -> str:
        try:
            lines = (config.ai_home() / "llama-server.log").read_text("utf-8", "replace").strip().splitlines()
            return lines[-1] if lines else ""
        except OSError:
            return ""

    def _stop_locked(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc, self._ready = None, False

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    # ------------------------------------------------------------ inference

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        seed: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """One chat completion from the local model; returns the reply text."""
        port = self.ensure()
        body: dict = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "top_p": 0.9,
            "top_k": 40,
            "min_p": 0.05,
            "repeat_penalty": 1.05,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if seed is not None:
            body["seed"] = int(seed) % (2**31)
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with _NO_PROXY.open(req, timeout=600) as r:
                data = json.load(r)
        except urllib.error.HTTPError as exc:
            raise ParaphraseError(f"the AI model returned an error ({exc.code})") from exc
        except (urllib.error.URLError, OSError) as exc:
            self.stop()
            raise ParaphraseError("lost connection to the AI model; please try again") from exc
        return _THINK.sub("", data["choices"][0]["message"]["content"] or "").strip()


# ---------------------------------------------------------------- helpers


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 22):
            digest.update(block)
    return digest.hexdigest()


def _friendly(exc: Exception) -> str:
    if isinstance(exc, urllib.error.URLError):
        return "Could not reach the download server. Check your internet connection and try again."
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return "There is not enough free disk space for the AI model (about 2.5 GB is needed)."
    return str(exc)


def _migrate_legacy_home() -> None:
    """Move a model downloaded by an early build from the old "Mero Paraphraser" folder."""
    if sys.platform != "win32" or os.environ.get("MERO_AI_HOME"):
        return
    legacy = Path(os.environ.get("LOCALAPPDATA", "")) / "Mero Paraphraser" / "ai"
    target = config.ai_home()
    if legacy.is_dir() and not target.exists():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(legacy, target)
            legacy.parent.rmdir()  # only if now empty
        except OSError:
            pass


def _kill_with_parent(proc: subprocess.Popen) -> object | None:
    """Put ``proc`` in a Windows job object that is closed (killing it) when we exit."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC_LIMIT(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        job = k32.CreateJobObjectW(None, None)
        info = EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        k32.AssignProcessToJobObject(job, int(proc._handle))  # type: ignore[attr-defined]
        return job  # keep the handle open for our lifetime
    except Exception:
        return None
