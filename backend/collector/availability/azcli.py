"""Thin wrapper that runs the Azure CLI as a child process.

Every Azure call made by the collector goes through `az` so the data matches what
an engineer sees in Cloud Shell. The CLI is installed as a Python package inside
the Function app (requirements.txt) and started with `python -m azure.cli`.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time


class AzError(RuntimeError):
    pass


def _python_path():
    """Import path for the child interpreter: the folder that holds azure/cli first."""
    paths = []
    try:
        spec = importlib.util.find_spec("azure.cli")
        if spec and spec.submodule_search_locations:
            paths.append(os.path.dirname(os.path.dirname(list(spec.submodule_search_locations)[0])))
    except (ImportError, ValueError):
        pass
    for p in sys.path:
        if p and p not in paths:
            paths.append(p)
    return os.pathsep.join(paths)


class AzCli:
    def __init__(self):
        self.config_dir = tempfile.mkdtemp(prefix="azcli-")
        env = dict(os.environ)
        env.update({
            "AZURE_CONFIG_DIR": self.config_dir,
            "AZURE_CORE_COLLECT_TELEMETRY": "false",
            "AZURE_CORE_ONLY_SHOW_ERRORS": "true",
            "AZURE_CORE_NO_COLOR": "true",
            "AZURE_CORE_SURVEY_MESSAGE": "false",
            "AZURE_EXTENSION_USE_DYNAMIC_INSTALL": "no",
            "PYTHONDONTWRITEBYTECODE": "1",
            # The CLI lives in the app's .python_packages folder; pass that import
            # path to the child interpreter so `-m azure.cli` resolves.
            "PYTHONPATH": _python_path(),
        })
        self.env = env
        self.calls = []
        self._lock = threading.Lock()

    def run(self, *args, output="json", timeout=900, retries=1):
        cmd = [sys.executable, "-m", "azure.cli", *args, "--output", output]
        last = None
        for attempt in range(retries + 1):
            t0 = time.monotonic()
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=timeout, env=self.env)
            except subprocess.TimeoutExpired:
                last = AzError("az %s timed out after %ss" % (" ".join(args[:3]), timeout))
                self._record(args, t0, -1)
                continue
            self._record(args, t0, proc.returncode)
            if proc.returncode == 0:
                out = proc.stdout.strip()
                if output != "json":
                    return out
                return json.loads(out) if out else None
            last = AzError("az %s failed: %s" % (" ".join(args[:3]), proc.stderr.strip()[-1200:]))
            time.sleep(3 * (attempt + 1))
        raise last

    def cleanup(self):
        shutil.rmtree(self.config_dir, ignore_errors=True)

    def _record(self, args, t0, rc):
        shown = []
        skip = False
        for a in args:
            if skip:
                shown.append("***")
                skip = False
                continue
            shown.append(a if len(a) < 120 else a[:117] + "...")
            if a in ("--client-id", "--subscription"):
                skip = True
        with self._lock:
            self.calls.append({"cmd": "az " + " ".join(shown),
                               "ms": int((time.monotonic() - t0) * 1000), "rc": rc})
