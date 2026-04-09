#!/usr/bin/env python3
"""
Persistent musicnn worker process.

This script is launched by MusiCNNWorker as a long-lived subprocess using
/usr/bin/python3 (NOT the Anaconda Python).  Using Anaconda's interpreter
causes libprotobuf.so.25.3.0 (from Anaconda's lib directory) to conflict
with TF's internal protobuf registry at sess.run() — producing a deterministic
NULL pointer dereference at offset 0x16d5fd.  The system Python (/usr/bin/python3)
does not have Anaconda's lib directory on its dynamic-linker search path, so
the correct libprotobuf is used and the crash never occurs.

Protocol (newline-delimited JSON over stdin / stdout):
  Parent → subprocess:  {"path": "/tmp/xyz.mp3", "top_k": 5}
  Subprocess → parent:  {"tags": ["guitar", ...], "error": null}
                     or  {"tags": [], "error": "message"}

The first output line is always "READY\n" (after TF and musicnn have loaded).
Subsequent lines are JSON responses, one per request.
stderr is not redirected — TF warnings flow through to the parent's stderr.
"""
import json
import os
import sys

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

# Import TF before musicnn so TF's protobuf registry is initialised first.
# musicnn/extractor.py imports librosa before tensorflow, but since we import
# tensorflow here first it is already cached in sys.modules when extractor
# runs its own 'import tensorflow as tf'.
import tensorflow as tf  # noqa: E402
tf.compat.v1.disable_eager_execution()

from musicnn.tagger import top_tags  # noqa: E402  # type: ignore[import]

# Signal to the parent that we are ready to accept requests.
sys.stdout.write("READY\n")
sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        tmp_path: str = req["path"]
        top_k: int = req.get("top_k", 5)

        # Redirect stdout so musicnn's "Computing spectrogram..." print
        # doesn't pollute our JSON channel.  Redirect to stderr so it's
        # still visible in logs if needed.
        _real_stdout = sys.stdout
        sys.stdout = sys.stderr
        try:
            tags = top_tags(tmp_path, model="MTT_musicnn", topN=top_k, print_tags=False)
            result: dict = {"tags": list(tags), "error": None}
        except UnboundLocalError as exc:
            # musicnn raises UnboundLocalError("batch") when audio is < 3 s.
            result = {"tags": [], "error": None}  # treat as "no tags", not a failure
        except Exception as exc:
            result = {"tags": [], "error": str(exc)}
        finally:
            sys.stdout = _real_stdout

    except Exception as exc:
        result = {"tags": [], "error": f"request parse error: {exc}"}

    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()
