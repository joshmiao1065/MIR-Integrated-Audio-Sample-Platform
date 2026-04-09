import concurrent.futures
import io
import logging
import multiprocessing
import os
import tempfile
import threading

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Subprocess isolation
# ---------------------------------------------------------------------------
# musicnn/extractor.py calls tf.compat.v1.disable_eager_execution() at module
# import time.  If that import runs in the main process it silently disables
# TF2 eager mode globally, which breaks YAMNet (a TF Hub SavedModel that
# requires eager tensors).
#
# Solution: run every musicnn call in a dedicated *subprocess* via a
# persistent ProcessPoolExecutor (max_workers=1).  The subprocess gets its
# own TF state so eager execution in the main process is never touched.
#
# The 'spawn' start method is used instead of the Linux default 'fork'
# because forking a process that has already imported TF / CUDA can cause
# deadlocks.  'spawn' starts a clean Python interpreter each time.
# ---------------------------------------------------------------------------

_executor: concurrent.futures.ProcessPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> concurrent.futures.ProcessPoolExecutor:
    global _executor
    with _executor_lock:
        # Recreate the executor if it was never started or if the worker
        # process crashed (BrokenProcessPool).
        if _executor is None:
            _executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
            )
    return _executor


def _predict_subprocess(tmp_path: str, top_k: int) -> list[str]:
    """
    Runs in an isolated subprocess.

    Importing musicnn.tagger here calls tf.compat.v1.disable_eager_execution()
    only inside this subprocess, leaving the parent process's TF state intact.

    IMPORTANT: Do NOT import librosa (or any library that loads numpy/scipy
    extension modules) before importing musicnn/TF here.  Doing so causes a
    segfault in libprotobuf.so inside TF — the shared-library initialisation
    order conflicts.  The duration guard lives in the parent process instead
    (MusiCNNWorker.predict), where librosa is already safely loaded.
    """
    import os as _os
    _os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

    from musicnn.tagger import top_tags  # type: ignore[import]

    try:
        tags = top_tags(tmp_path, model="MTT_musicnn", topN=top_k, print_tags=False)
        return list(tags)
    except UnboundLocalError as exc:
        # musicnn's batch_data() raises UnboundLocalError when the audio clip is
        # shorter than the 3-second analysis window (n_frames=187 @ 16 kHz).
        # Return an empty tag list rather than propagating an error.
        if "batch" in str(exc):
            return []
        raise


class MusiCNNWorker:
    """
    Music tagger using MTG's MusiCNN (MTT_musicnn checkpoint).

    Produces high-level semantic tags — genre, mood, instrumentation — from the
    MagnaTagATune label set (~50 classes: 'guitar', 'classical', 'ambient', etc.).

    MusiCNN is run in an isolated subprocess so that its
    tf.compat.v1.disable_eager_execution() call does not pollute the main
    process, which needs TF2 eager mode for YAMNet and CLAP.
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
        """
        # Duration guard — musicnn needs >= 3 s of audio.  Check here in the
        # parent process using soundfile (fast header read, no TF involved).
        # Do NOT do this inside the subprocess: importing librosa before TF in
        # a spawned process causes a libprotobuf segfault (see LESSONS.md §27).
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
            executor = _get_executor()
            try:
                future = executor.submit(_predict_subprocess, tmp_path, top_k)
                return future.result(timeout=300)  # 5-minute timeout per file
            except concurrent.futures.process.BrokenProcessPool:
                # Worker crashed; recreate the pool and retry once.
                log.warning("MusiCNN subprocess pool broken — recreating and retrying.")
                with _executor_lock:
                    global _executor
                    _executor = None
                executor = _get_executor()
                future = executor.submit(_predict_subprocess, tmp_path, top_k)
                return future.result(timeout=300)
        finally:
            os.unlink(tmp_path)
