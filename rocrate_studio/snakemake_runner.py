"""Drive Snakemake: run a workflow, then report on it with the FAIRSCAPE reporter.

The Nextflow path has a plugin that writes the crate while the pipeline runs.
Snakemake works the other way round: a *report* plugin is a second, read-only
pass over the finished DAG, so a run here is two invocations —

    snakemake --cores N [--use-conda] [targets]         # run the workflow
    snakemake --cores N --reporter fairscape ...        # report on what ran

and the reporter has to live in the same environment as Snakemake, because
Snakemake loads it as a plugin inside its own interpreter. That is the one
thing that goes wrong, so ``info()`` checks it explicitly (and against the
Snakemake that will actually run, not against this process) and
``install_command()`` says exactly how to fix it.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

REPORTER_PACKAGE = "snakemake-report-plugin-fairscape"
REPORTER_MODULE = "snakemake_report_plugin_fairscape"
CRATE_NAME = "ro-crate-metadata.json"
RECORDS_NAME = "records.json"

FIELDS = [
    {"name": "workflow", "label": "Workflow folder (has a Snakefile)", "type": "dir", "required": True},
    {"name": "snakefile", "label": "Snakefile", "type": "string", "default": "Snakefile",
     "help": "Relative to the workflow folder. Change it for workflow/Snakefile layouts."},
    {"name": "targets", "label": "Targets to build", "type": "string",
     "placeholder": "leave empty for the default target"},
    {"name": "cores", "label": "Cores", "type": "string", "default": "4"},
    {"name": "use_conda", "label": "Use the rules' conda environments (--use-conda)",
     "type": "bool", "default": True},
    {"name": "report_only", "label": "Already ran it — just build the crate", "type": "bool", "default": False,
     "help": "Skips the run and reports on the finished one in that folder."},
    {"name": "schemas", "label": "Infer schemas for tabular outputs", "type": "bool", "default": True},
    {"name": "name", "label": "Crate name", "type": "string"},
    {"name": "description", "label": "Description", "type": "text", "help": "At least 10 characters or it is ignored."},
    {"name": "author", "label": "Author", "type": "string"},
    {"name": "keywords", "label": "Keywords", "type": "string", "placeholder": "comma, separated"},
    {"name": "license", "label": "License (SPDX URL)", "type": "string",
     "default": "https://spdx.org/licenses/CC-BY-4.0"},
    {"name": "naan", "label": "ARK NAAN", "type": "string", "default": "59853"},
    {"name": "extra_args", "label": "Extra snakemake arguments", "type": "string",
     "placeholder": "--configfile config/other.yaml --rerun-incomplete"},
]


def candidates() -> list[str]:
    """Every snakemake this machine has: PATH first, then the conda envs.

    The studio does not run inside the environment Snakemake lives in — the
    workflow's own tools (bwa, samtools, …) usually pull it into an env of its
    own — so look the same way ``nextflow_runner.find_java`` looks for a JVM.
    """
    found = []
    on_path = shutil.which("snakemake")
    if on_path:
        found.append(on_path)
    for root in ("~/anaconda3/envs/*/bin/snakemake", "~/miniconda3/envs/*/bin/snakemake",
                 "~/miniforge3/envs/*/bin/snakemake", "~/mambaforge/envs/*/bin/snakemake"):
        found += sorted(glob.glob(os.path.expanduser(root)))
    seen, out = set(), []
    for path in found:
        real = os.path.realpath(path)
        if real not in seen:
            seen.add(real)
            out.append(path)
    return out


def _snakemake() -> str | None:
    """The snakemake to use: the first one that can also load the reporter,
    else the first one at all (so ``info`` can say what is missing)."""
    found = candidates()
    for path in found:
        if _imports(interpreter_for(path), REPORTER_MODULE):
            return path
    return found[0] if found else None


def interpreter_for(snakemake_path: str | None) -> str:
    """The python that will import the reporter — Snakemake's, not ours.

    A console script's first line names its interpreter, which is how a
    snakemake installed in another conda environment is found from here.
    """
    if not snakemake_path:
        return sys.executable
    try:
        first = Path(snakemake_path).read_text(errors="ignore").splitlines()[0]
    except (OSError, IndexError):
        return sys.executable
    if first.startswith("#!") and "python" in first:
        candidate = first[2:].strip().strip('"')
        if Path(candidate).exists():
            return candidate
    return sys.executable


def _imports(python: str, module: str) -> bool:
    try:
        return subprocess.run([python, "-c", f"import {module}"],
                              capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def install_command(python: str | None = None) -> list[str]:
    """What to run so the reporter lands in the same env as Snakemake."""
    python = python or interpreter_for(_snakemake())
    return [python, "-m", "pip", "install", f"{REPORTER_PACKAGE}[artifacts]"]


def info() -> dict:
    """What the GUI needs to decide whether this path is usable."""
    snakemake_path = _snakemake()
    python = interpreter_for(snakemake_path)
    version = ""
    reason = []
    if not snakemake_path:
        reason.append("no snakemake found on PATH or in a conda environment")
    else:
        try:
            version = subprocess.run([snakemake_path, "--version"], capture_output=True,
                                     text=True, timeout=120).stdout.strip()
        except (OSError, subprocess.SubprocessError) as e:  # noqa: BLE001
            reason.append(f"snakemake --version failed: {e}")
    have_reporter = bool(snakemake_path) and _imports(python, REPORTER_MODULE)
    if snakemake_path and not have_reporter:
        reason.append(f"the FAIRSCAPE reporter is not installed in Snakemake's own "
                      f"environment ({python})")
    example = next((str(p) for p in (
        Path(__file__).resolve().parents[2] / "fairscape_conversion" / "examples"
        / "snakemake-variant-calling",
        Path.home() / "fairscape" / "fairscape_conversion" / "examples"
        / "snakemake-variant-calling")
        if (p / "Snakefile").exists()), None)
    return {"available": not reason, "reason": "; ".join(reason), "version": version,
            "python": python, "reporter_installed": have_reporter,
            "install_command": " ".join(install_command(python)),
            "fields": FIELDS, "example": example}


def _report_args(form: dict, crate_path: Path) -> list[str]:
    args = ["--reporter", "fairscape", "--report-fairscape-path", str(crate_path)]
    for key, flag in (("name", "--report-fairscape-name"),
                      ("description", "--report-fairscape-description"),
                      ("author", "--report-fairscape-author"),
                      ("keywords", "--report-fairscape-keywords"),
                      ("license", "--report-fairscape-license"),
                      ("naan", "--report-fairscape-naan")):
        value = str(form.get(key) or "").strip()
        if value:
            args += [flag, value]
    if form.get("schemas", True):
        args.append("--report-fairscape-schemas")
    return args


def plan(form: dict) -> dict:
    """The commands a run would issue — shown in the GUI before it starts."""
    workflow = Path(str(form.get("workflow") or "")).expanduser()
    if not workflow.is_dir():
        raise FileNotFoundError(f"no such folder: {workflow}")
    snakefile = str(form.get("snakefile") or "Snakefile")
    if not (workflow / snakefile).is_file():
        raise FileNotFoundError(f"no {snakefile} in {workflow}")

    snakemake_path = _snakemake() or "snakemake"
    common = [snakemake_path, "--snakefile", snakefile,
              "--cores", str(form.get("cores") or "4")]
    if form.get("use_conda", True):
        common.append("--use-conda")
    extra = str(form.get("extra_args") or "").split()

    steps = []
    if not form.get("report_only"):
        run = list(common) + extra
        run += [t for t in str(form.get("targets") or "").split() if t]
        steps.append(run)
    steps.append(list(common) + extra + _report_args(form, Path(CRATE_NAME)))
    return {"workflow": str(workflow), "steps": steps,
            "crate": str(workflow / CRATE_NAME)}


class Job:
    """Runs the steps in order, streaming both into one log.

    ``TOOL`` names the process in the log lines; ``_on_stopped`` is what a
    stopped run needs cleaned up. Both exist so ``artifacts_runner`` can reuse
    the loop for a process that is not Snakemake.
    """

    TOOL = "snakemake"

    def __init__(self, steps, cwd, env, crate_file: Path):
        self.id = uuid.uuid4().hex[:8]
        self.lines: list[str] = []
        self.done = False
        self.ok = False
        self.stopped = False
        self.crate_file = crate_file
        self.proc: subprocess.Popen | None = None
        self._steps = steps
        self._cwd = cwd
        self._env = env
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        code = 0
        for step in self._steps:
            if self.stopped:
                code = 1
                break
            self.lines.append("$ " + " ".join(step) + f"   (in {self._cwd})")
            try:
                self.proc = subprocess.Popen(step, cwd=self._cwd, env=self._env,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, text=True, bufsize=1)
            except OSError as e:  # noqa: BLE001
                self.lines.append(f"could not start {self.TOOL}: {e}")
                code = 1
                break
            for line in self.proc.stdout:
                self.lines.append(line.rstrip("\n"))
            self.proc.wait()
            code = self.proc.returncode
            if code != 0:
                self.lines.append("stopped" if self.stopped else f"{self.TOOL} exited {code}; stopping here")
                break
        if self.stopped:
            self._on_stopped()
        self._finish(code)

    def _on_stopped(self):
        self._unlock()

    def _unlock(self):
        """A killed Snakemake leaves its workdir locked and the next run refuses
        to start. We are the ones who killed it, so it is safe to unlock."""
        cmd = [self._steps[0][0], "--snakefile", self._steps[0][2], "--unlock"]
        self.lines.append("$ " + " ".join(cmd) + "   (releasing the lock the stopped run left)")
        try:
            out = subprocess.run(cmd, cwd=self._cwd, env=self._env, capture_output=True,
                                 text=True, timeout=120)
            self.lines += [l for l in (out.stdout + out.stderr).splitlines() if l.strip()]
        except (OSError, subprocess.SubprocessError) as e:  # noqa: BLE001
            self.lines.append(f"could not unlock: {e} — run `snakemake --unlock` in the folder by hand")

    def stop(self):
        """Stop the current step and skip the remaining ones. SIGTERM lets
        Snakemake clean up (unlock the workdir, mark incomplete outputs)."""
        self.stopped = True
        if self.proc is not None and self.proc.poll() is None:
            self.lines.append(f"stopping the run (SIGTERM to {self.TOOL})…")
            self.proc.terminate()

    def _finish(self, code):
        """Decide success once the steps are done — last thing before done."""
        self.ok = code == 0 and self.crate_file.exists()
        if code == 0 and not self.crate_file.exists():
            self.lines.append(
                f"snakemake finished but {self.crate_file} was not written — the "
                "reporter writes the crate only when it can load; check the log above")
        self.done = True


JOBS: dict[str, Job] = {}


def start(form: dict) -> Job:
    described = plan(form)
    workflow = Path(described["workflow"])
    env = dict(os.environ)
    # the reporter writes its plain records document too when asked, which is
    # what fairscape_conversion's snakemake plugin consumes on its own
    env["SNAKEMAKE_FAIRSCAPE_DUMP_RECORDS"] = str(workflow / RECORDS_NAME)
    # a snakemake living in a conda env brings that env's tools with it: put
    # its bin directory first so the rules find bwa, samtools and friends
    # exactly as they would from an activated shell
    bindir = str(Path(described["steps"][0][0]).resolve().parent)
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    job = Job(described["steps"], cwd=str(workflow), env=env,
              crate_file=Path(described["crate"]))
    JOBS[job.id] = job
    return job


class InstallJob(Job):
    """Same streaming, but the 'crate' it waits for is an importable module."""

    def __init__(self, python: str):
        self._python = python
        super().__init__([install_command(python)], cwd=str(Path.home()),
                         env=dict(os.environ), crate_file=Path("/nonexistent"))

    def _finish(self, code):
        self.ok = code == 0 and _imports(self._python, REPORTER_MODULE)
        self.lines.append(
            f"the reporter now imports in {self._python}" if self.ok else
            "the reporter still does not import — install it by hand with: "
            + " ".join(install_command(self._python)))
        self.done = True


def start_install() -> InstallJob:
    job = InstallJob(interpreter_for(_snakemake()))
    JOBS[job.id] = job
    return job
