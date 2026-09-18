"""Build every artifact for a saved crate with ``fairscape-artifacts all``.

``fairscape_artifacts`` writes, beside the crate: the interactive evidence
graph (``ro-crate-evidence-graph.html`` + ``.json``), one ``ro-crate-preview.html``
per constituent crate, ``ro-crate-datasheet.html``, and — when the
AI-readiness grader is importable — ``ai-ready-presentation.json`` and
``ai-ready-review.html`` at the crate root. It does not write the grader's
improvements form, so after a successful build this module renders
``ai-ready-improve.html`` itself and summarises the mechanical estimate the
presentation carries, per rubric domain.

The build runs as a subprocess of the studio's own interpreter
(``python -m fairscape_artifacts all …``): the review can take a while with
``--network``, the user should be able to watch and stop it like a workflow
run, and a crash in a renderer must not take the studio down. "Installed"
therefore means "imports in this interpreter", and the install job pips it
into exactly that.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

from .snakemake_runner import Job, _imports

MODULE = "fairscape_artifacts"
PACKAGE = "fairscape-artifacts"
CRATE_NAME = "ro-crate-metadata.json"
PRESENTATION = "ai-ready-presentation.json"
REVIEW = "ai-ready-review.html"
DATASHEET = "ro-crate-datasheet.html"
EVIDENCE_GRAPH = "ro-crate-evidence-graph.html"
IMPROVE = "ai-ready-improve.html"

# where the presentation may sit: the build writes it at the crate root; the
# studio's old /api/aiready route wrote it under ai-ready-review/
PRESENTATION_PATHS = (PRESENTATION, "ai-ready-review/" + PRESENTATION)


def _source_checkout() -> Path | None:
    """A sibling checkout of fairscape_artifacts, if this studio runs from source."""
    for p in (Path(__file__).resolve().parents[2] / "fairscape_artifacts",
              Path.home() / "fairscape" / "fairscape_artifacts"):
        if (p / "pyproject.toml").is_file():
            return p
    return None


def install_command() -> list[str]:
    """pip into the studio's own interpreter: editable from the sibling checkout
    when there is one, else the released package."""
    src = _source_checkout()
    target = ["-e", str(src)] if src else [PACKAGE]
    return [sys.executable, "-m", "pip", "install", *target]


def installed() -> bool:
    return _imports(sys.executable, MODULE)


def grader_available() -> bool:
    try:
        import aireadiness_evidence  # noqa: F401
        return True
    except ImportError:
        return False


def info() -> dict:
    have = installed()
    version = ""
    if have:
        try:
            version = importlib.metadata.version(PACKAGE)
        except importlib.metadata.PackageNotFoundError:
            version = "?"
    return {"installed": have, "version": version, "grader": grader_available(),
            "python": sys.executable, "install_command": " ".join(install_command())}


def find_presentation(crate_dir: Path) -> Path | None:
    """The newest presentation JSON beside the crate, in either layout."""
    hits = [crate_dir / rel for rel in PRESENTATION_PATHS if (crate_dir / rel).is_file()]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def estimate_summary(presentation: dict) -> dict:
    """Sum of the integer mechanical estimates per rubric domain, max 2 per
    criterion. Criteria awaiting human review count 0 here — this is the
    floor, not the grade."""
    sections, total, maximum = [], 0, 0
    for sec in presentation.get("sections", []):
        score = 0
        for c in sec.get("criteria", []):
            try:
                score += int((c.get("estimate") or {}).get("score"))
            except (TypeError, ValueError):
                pass
        mx = 2 * len(sec.get("criteria", []))
        sections.append({"title": sec.get("title", ""), "score": score, "max": mx})
        total += score
        maximum += mx
    return {"total": total, "max": maximum, "sections": sections,
            "generated": presentation.get("generated", ""),
            "network": bool(presentation.get("network_checks"))}


def read_estimate(crate_dir: Path) -> dict | None:
    p = find_presentation(crate_dir)
    if not p:
        return None
    try:
        return estimate_summary(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def build_command(crate_dir: Path, network: bool) -> list[str]:
    cmd = [sys.executable, "-m", MODULE, "all", str(crate_dir)]
    if network:
        cmd.append("--network")
    return cmd


class BuildJob(Job):
    """``fairscape-artifacts all`` streamed; then the improvements form and the
    estimate, computed here once the process has exited cleanly."""

    TOOL = "fairscape-artifacts"

    def __init__(self, crate_dir: Path, network: bool):
        self.crate_dir = crate_dir
        self.network = network
        self.previous = read_estimate(crate_dir)
        self.estimate: dict | None = None
        self.written: dict[str, str] = {}
        env = dict(os.environ)
        env.setdefault("PYTHONUNBUFFERED", "1")   # progress lines as they happen
        super().__init__([build_command(crate_dir, network)], cwd=str(crate_dir),
                         env=env, crate_file=crate_dir / CRATE_NAME)

    def _on_stopped(self):
        pass   # nothing to unlock: the build only ever adds files

    def _finish(self, code):
        self.ok = code == 0 and not self.stopped
        if self.ok:
            self._render_improve()
            self._summarise()
        self.done = True

    def _render_improve(self):
        """The grader's offline quick-wins form, which the build does not write."""
        try:
            from aireadiness_improve.cli import find_prior_scores, render_improve
        except ImportError as e:
            self.lines.append(f"skipping {IMPROVE}: the grader's improve package is not "
                              f"importable here ({e})")
            return
        meta = self.crate_dir / CRATE_NAME
        try:
            html = render_improve(crate=json.loads(meta.read_text(encoding="utf-8")),
                                  prior=find_prior_scores(self.crate_dir, None),
                                  crate_label=str(meta))
            target = self.crate_dir / IMPROVE
            target.write_text(html, encoding="utf-8")
            self.lines.append(f"wrote {target}")
        except Exception as e:  # noqa: BLE001
            self.lines.append(f"could not render {IMPROVE}: {type(e).__name__}: {e}")

    def _summarise(self):
        for key, name in (("datasheet", DATASHEET), ("review", REVIEW),
                          ("evidence_graph", EVIDENCE_GRAPH), ("improve", IMPROVE)):
            p = self.crate_dir / name
            if p.is_file():
                self.written[key] = str(p)
        pres = self.crate_dir / PRESENTATION
        if not pres.is_file():
            self.lines.append("no AI-readiness review was written (the grader is not "
                              "installed in this environment, or the review was skipped)")
            return
        try:
            self.estimate = estimate_summary(json.loads(pres.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            self.lines.append(f"could not read {pres.name}: {e}")
            return
        est = self.estimate
        line = f"AI-readiness estimate {est['total']}/{est['max']}"
        if self.previous:
            line = f"AI-readiness estimate {self.previous['total']} → {est['total']} of {est['max']}"
        self.lines.append(line + "  —  " + " · ".join(
            f"{s['title']} {s['score']}/{s['max']}" for s in est["sections"]))

    def payload(self) -> dict:
        """What the final SSE event carries beyond done/ok."""
        out = {"estimate": self.estimate, "previous": self.previous,
               "written": self.written, "network": self.network}
        if not self.ok:
            out["error"] = ("the build was stopped" if self.stopped else
                            "fairscape-artifacts failed — see the log")
        return out


class InstallJob(Job):
    TOOL = "pip"

    def __init__(self):
        super().__init__([install_command()], cwd=str(Path.home()), env=dict(os.environ),
                         crate_file=Path("/nonexistent"))

    def _on_stopped(self):
        pass

    def _finish(self, code):
        self.ok = code == 0 and installed()
        self.lines.append(
            f"{PACKAGE} now imports in {sys.executable}" if self.ok else
            f"{PACKAGE} still does not import — install it by hand with: "
            + " ".join(install_command()))
        self.done = True

    def payload(self) -> dict:
        return {} if self.ok else {"error": "the install did not succeed — see the log"}


JOBS: dict[str, Job] = {}


def start(path: str, network: bool = False) -> BuildJob:
    d = Path(path).expanduser()
    if d.is_file():
        d = d.parent
    if not (d / CRATE_NAME).is_file():
        raise FileNotFoundError(f"no {CRATE_NAME} in {d} — save the crate first")
    if not installed():
        raise RuntimeError(f"{PACKAGE} is not installed in the studio's environment; run: "
                           + " ".join(install_command()))
    job = BuildJob(d.resolve(), network)
    JOBS[job.id] = job
    return job


def start_install() -> InstallJob:
    job = InstallJob()
    JOBS[job.id] = job
    return job
