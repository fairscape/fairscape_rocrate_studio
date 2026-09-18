"""Drive nf-fairscape: write a config overlay and run Nextflow, streaming its log.

The overlay is a separate file passed with ``-c``, so the user's own
nextflow.config is never edited. Java is not on this machine's PATH but lives
in a conda env, so the runner finds one and hands it to the launcher through
NXF_JAVA_HOME.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

PLUGIN_VERSION = "0.1.0"
CONFIG_NAME = "rocrate-studio.config"

FIELDS = [
    {"name": "pipeline", "label": "Pipeline folder (has main.nf)", "type": "dir", "required": True},
    {"name": "outdir", "label": "Results folder (crate lands here)", "type": "dir", "default": "results",
     "help": "Relative paths are inside the pipeline folder."},
    {"name": "author", "label": "Author", "type": "string"},
    {"name": "organization", "label": "Organization", "type": "string"},
    {"name": "description", "label": "Description", "type": "text", "help": "At least 10 characters or it is ignored."},
    {"name": "keywords", "label": "Keywords", "type": "string", "placeholder": "comma, separated"},
    {"name": "license", "label": "License (SPDX URL)", "type": "string", "default": "https://spdx.org/licenses/MIT"},
    {"name": "naan", "label": "ARK NAAN", "type": "string", "default": "59853"},
    {"name": "schemas", "label": "Infer schemas for CSV/TSV outputs", "type": "bool", "default": True},
    {"name": "checksums", "label": "Compute file checksums", "type": "bool", "default": False},
    {"name": "containerProvenance", "label": "Record container provenance", "type": "bool", "default": False},
    {"name": "resume", "label": "Resume a previous run (-resume)", "type": "bool", "default": True},
    {"name": "extra_args", "label": "Extra nextflow arguments", "type": "string", "placeholder": "-profile docker --input data.csv"},
]


def find_java() -> str | None:
    if shutil.which("java"):
        return None  # already on PATH, nothing to set
    for cand in ("NXF_JAVA_HOME", "JAVA_HOME"):
        if os.environ.get(cand) and Path(os.environ[cand], "bin", "java").exists():
            return os.environ[cand]
    for java in sorted(glob.glob(os.path.expanduser("~/anaconda3/envs/*/bin/java"))
                       + sorted(glob.glob(os.path.expanduser("~/miniconda3/envs/*/bin/java")))):
        return str(Path(java).parent.parent)
    return None


def info() -> dict:
    nf = shutil.which("nextflow")
    java_home = find_java()
    have_java = bool(shutil.which("java") or java_home)
    plugin_dir = Path.home() / ".nextflow" / "plugins" / f"nf-fairscape-{PLUGIN_VERSION}"
    reason = []
    if not nf:
        reason.append("nextflow not on PATH")
    if not have_java:
        reason.append("no java found (PATH, JAVA_HOME or a conda env)")
    if not plugin_dir.exists():
        reason.append(f"plugin not installed at {plugin_dir} (run `make install` in nf-fairscape)")
    version = ""
    if nf:
        try:
            out = subprocess.run([nf, "-v"], capture_output=True, text=True, timeout=60,
                                 env=_env(java_home)).stdout
            version = out.strip().split()[-1] if out.strip() else ""
        except Exception as e:  # noqa: BLE001
            reason.append(f"nextflow -v failed: {e}")
    # the slow letters-chain first: three steps that sleep ~12 s each, so a run is
    # long enough to watch go by; the plugin's test pipeline as a fallback
    example = next((str(p) for p in (Path.home() / "cellmap" / "nf-fairscape" / "examples" / "letters-chain-slow",
                                       Path.home() / "nf-fairscape" / "examples" / "letters-chain-slow",
                                       Path.home() / "cellmap" / "nf-fairscape" / "nf-fairscape-test",
                                       Path.home() / "nf-fairscape" / "nf-fairscape-test")
                    if (p / "main.nf").exists()), None)
    return {"available": not reason, "reason": "; ".join(reason), "version": version,
            "java_home": java_home, "plugin_dir": str(plugin_dir), "fields": FIELDS,
            "example": example}


def _env(java_home):
    env = dict(os.environ)
    if java_home:
        env["NXF_JAVA_HOME"] = java_home
    env.setdefault("NXF_ANSI_LOG", "false")
    return env


def _groovy_str(s: str) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def render_config(form: dict) -> str:
    outdir = form.get("outdir") or "results"
    lines = [
        "// written by RO-Crate Studio — pass with `nextflow run . -c rocrate-studio.config`",
        f"plugins {{ id 'nf-fairscape@{PLUGIN_VERSION}' }}",
        f"outputDir = {_groovy_str(outdir)}",
        "fairscape {",
        f"    file      = {_groovy_str(outdir.rstrip('/') + '/ro-crate-metadata.json')}",
        "    overwrite = true",
    ]
    for key in ("author", "organization", "description", "license", "naan"):
        if form.get(key):
            lines.append(f"    {key:<9} = {_groovy_str(form[key])}")
    kws = [k.strip() for k in str(form.get("keywords") or "").split(",") if k.strip()]
    if kws:
        lines.append("    keywords  = [" + ", ".join(_groovy_str(k) for k in kws) + "]")
    for key in ("schemas", "checksums", "containerProvenance"):
        if key in form:
            lines.append(f"    {key:<9} = {'true' if form[key] else 'false'}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_config(form: dict) -> Path:
    pipeline = Path(form["pipeline"]).expanduser()
    if not (pipeline / "main.nf").exists() and not list(pipeline.glob("*.nf")):
        raise FileNotFoundError(f"no .nf script in {pipeline}")
    target = pipeline / CONFIG_NAME
    target.write_text(render_config(form))
    return target


class Job:
    def __init__(self, cmd, cwd, env, crate_file: Path):
        self.id = uuid.uuid4().hex[:8]
        self.lines: list[str] = []
        self.done = False
        self.ok = False
        self.stopped = False
        self.crate_file = crate_file
        self.proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.append(line.rstrip("\n"))
        self.proc.wait()
        self.ok = self.proc.returncode == 0 and self.crate_file.exists()
        if self.proc.returncode == 0 and not self.crate_file.exists():
            self.lines.append(f"nextflow finished but {self.crate_file} was not written "
                              "(the plugin only writes on a successful run)")
        self.done = True

    def stop(self):
        """Ask Nextflow to abort; SIGTERM makes it kill its tasks and exit non-zero."""
        self.stopped = True
        if self.proc.poll() is None:
            self.lines.append("stopping the run (SIGTERM to nextflow)…")
            self.proc.terminate()


JOBS: dict[str, Job] = {}


def start(form: dict) -> Job:
    cfg = write_config(form)
    pipeline = cfg.parent
    outdir = Path(form.get("outdir") or "results")
    if not outdir.is_absolute():
        outdir = pipeline / outdir
    cmd = [shutil.which("nextflow") or "nextflow", "run", ".", "-c", CONFIG_NAME,
           "-plugins", f"nf-fairscape@{PLUGIN_VERSION}"]
    if form.get("resume", True):
        cmd.append("-resume")
    if form.get("extra_args"):
        cmd += str(form["extra_args"]).split()
    job = Job(cmd, cwd=str(pipeline), env=_env(find_java()), crate_file=outdir / "ro-crate-metadata.json")
    job.lines.append("$ " + " ".join(cmd) + f"   (in {pipeline})")
    JOBS[job.id] = job
    return job
