"""
MusiCNN worker — runs MTG MusiCNN inside a persistent subprocess.

WHY A SUBPROCESS AT ALL?
  musicnn/extractor.py calls tf.compat.v1.disable_eager_execution() at import
  time.  If that import runs in the main process it silently disables TF2 eager
  mode globally, breaking YAMNet (a TF Hub SavedModel that requires eager mode).

WHY /usr/bin/python3 AND NOT THE ANACONDA INTERPRETER?
  When Anaconda's Python is used (e.g. ~/anaconda3/bin/python3.12), the dynamic
  linker finds ~/anaconda3/lib/libprotobuf.so.25.3.0 on the library search path.
  This Anaconda-built libprotobuf conflicts with TF 2.20's internally compiled
  protobuf C++ code, producing a deterministic NULL pointer dereference at offset
  0x16d5fd inside libprotobuf.so.25.3.0 when sess.run() serialises RunOptions.

  /usr/bin/python3 does NOT have Anaconda's lib directory on its dynamic-linker
  search path, so TF uses the correct (system) libprotobuf and runs cleanly.

  Verified: running `top_tags(...)` via /usr/bin/python3 completes successfully
  on the same samples that segfault under the Anaconda interpreter.

ARCHITECTURE:
  A single long-lived subprocess is started lazily on the first predict() call.
  TF and the MTT_musicnn checkpoint load once; subsequent calls are fast (~1-2 s).
  Communication uses newline-delimited JSON over stdin / stdout (see _musicnn_proc.py).
  If the subprocess dies, it is restarted automatically (one retry per predict call).
  After two consecutive failures, predict() returns [] so the rest of the pipeline
  (CLAP, YAMNet, Librosa) can still complete.

  See also: LESSONS.md §2, §27, §28.
"""

import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time

log = logging.getLogger(__name__)

# Path to the worker script that runs inside the subprocess.
_PROC_SCRIPT = os.path.join(os.path.dirname(__file__), "_musicnn_proc.py")

# Python interpreter to use for the subprocess.  MUST be /usr/bin/python3 (or
# any Python that does NOT inherit Anaconda's LD_LIBRARY_PATH / lib directory).
_SUBPROCESS_PYTHON = "/usr/bin/python3"

# Per-request timeout (seconds).  musicnn inference on a 3–60 s clip takes
# roughly 2–10 s on CPU.  5 minutes is extremely conservative.
_TIMEOUT = 300


class _SubprocessWorker:
    """Manages a single persistent musicnn subprocess."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    # ── subprocess lifecycle ──────────────────────────────────────────────────

    def _start(self) -> None:
        """Start (or restart) the worker subprocess and wait for READY."""
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None

        log.debug("Starting musicnn subprocess (%s %s).", _SUBPROCESS_PYTHON, _PROC_SCRIPT)
        self._proc = subprocess.Popen(
            [_SUBPROCESS_PYTHON, _PROC_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,   # let TF warnings flow to the parent's stderr
            text=True,
            bufsize=1,     # line-buffered
        )

        # Wait up to 60 s for the subprocess to finish loading TF + musicnn.
        self._proc.stdout._CHUNK_SIZE = 1  # type: ignore[attr-defined]
        deadline = time.monotonic() + 60.0
        while True:
            if time.monotonic() > deadline:
                self._proc.kill()
                self._proc = None
                raise RuntimeError("musicnn subprocess did not send READY within 60 s")
            line = self._proc.stdout.readline().strip()
            if line == "READY":
                log.debug("musicnn subprocess ready (pid=%d).", self._proc.pid)
                return
            if not line and self._proc.poll() is not None:
                raise RuntimeError(
                    f"musicnn subprocess exited with code {self._proc.returncode} "
                    "before sending READY"
                )

    def _is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ── request / response ───────────────────────────────────────────────────

    def call(self, tmp_path: str, top_k: int) -> list[str]:
        """Send one inference request and return the tag list."""
        req = json.dumps({"path": tmp_path, "top_k": top_k}) + "\n"
        assert self._proc is not None
        self._proc.stdin.write(req)
        self._proc.stdin.flush()

        # Read the response with a timeout (via a background thread).
        result: list = []
        exc_holder: list = []

        def _read() -> None:
            try:
                line = self._proc.stdout.readline()  # type: ignore[union-attr]
                if line:
                    data = json.loads(line)
                    if data.get("error"):
                        log.warning("musicnn subprocess error: %s", data["error"])
                    result.extend(data.get("tags", []))
                else:
                    exc_holder.append(RuntimeError("subprocess stdout closed unexpectedly"))
            except Exception as exc:
                exc_holder.append(exc)

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout=_TIMEOUT)

        if t.is_alive():
            # Timeout — kill the subprocess; it will be restarted on next call.
            log.error("musicnn subprocess timed out after %ds — killing.", _TIMEOUT)
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None
            raise TimeoutError("musicnn subprocess timed out")

        if exc_holder:
            raise exc_holder[0]

        return result

    # ── public interface ─────────────────────────────────────────────────────

    def predict(self, tmp_path: str, top_k: int) -> list[str]:
        """
        Run inference, restarting the subprocess if it has died.
        Raises on second consecutive failure so the caller can return [].
        """
        with self._lock:
            if not self._is_alive():
                self._start()
            try:
                return self.call(tmp_path, top_k)
            except Exception as exc:
                log.warning("musicnn call failed (%s) — restarting subprocess.", exc)
                self._start()
                return self.call(tmp_path, top_k)  # let this exception propagate


# Module-level singleton.
_worker: _SubprocessWorker | None = None
_worker_lock = threading.Lock()


def _get_worker() -> _SubprocessWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = _SubprocessWorker()
    return _worker


class MusiCNNWorker:
    """
    Music tagger using MTG's MusiCNN (MTT_musicnn checkpoint).

    Produces high-level semantic tags — genre, mood, instrumentation — from the
    MagnaTagATune label set (~50 classes: 'guitar', 'classical', 'ambient', etc.).

    Inference runs inside a persistent /usr/bin/python3 subprocess to avoid the
    Anaconda libprotobuf.so conflict and to isolate tf.compat.v1.disable_eager_execution()
    from the parent process.
    """

    def predict(self, audio_bytes: bytes, top_k: int = 5) -> list[str]:
        """
        Return the top-k MagnaTagATune tags for the given audio.

        Args:
            audio_bytes: Raw audio file bytes (MP3 or WAV).
            top_k:       Number of top tags to return (default 5).

        Returns:
            List of tag name strings ordered by confidence, e.g.
            ['guitar', 'classical', 'slow', 'strings', 'not rock'].
            Returns [] on failure so the rest of the pipeline can complete.
        """
        # Duration guard — musicnn needs >= 3 s of audio.  Check here in the
        # parent process using soundfile (fast header-only read, no TF involved).
        try:
            import soundfile as sf
            with sf.SoundFile(io.BytesIO(audio_bytes)) as f:
                duration = len(f) / f.samplerate
            if duration < 3.0:
                log.debug("Audio too short for MusiCNN (%.1fs < 3.0s) — skipping.", duration)
                return []
        except Exception:
            pass  # unknown format / can't read header — let musicnn try

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            worker = _get_worker()
            try:
                return worker.predict(tmp_path, top_k)
            except Exception as exc:
                log.error(
                    "MusiCNN subprocess failed on retry (%s) — "
                    "returning [] so pipeline can complete without musicnn tags.",
                    exc,
                )
                return []
        finally:
            os.unlink(tmp_path)
