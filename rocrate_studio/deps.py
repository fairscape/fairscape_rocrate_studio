"""What the studio needs before it will start.

The studio is a thin GUI over the other fairscape repos: without
``fairscape_models`` there is nothing to validate against and without
``fairscape_conversion`` there is nothing to import a run with. Starting and
then failing on the first click is worse than not starting, so the required
set is checked up front — in :func:`main` and again when ``app`` is imported,
which covers ``uvicorn rocrate_studio.app:app`` too.

Optional dependencies are the ones a *particular panel* needs (artifacts,
grader, Nextflow, Snakemake). They never block startup; the panels that use
them already report them in the UI and offer to install them.

Stdlib only — this module has to be importable before anything is installed.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)

# repos that live beside this one when the studio runs from source
SIBLINGS = (Path(__file__).resolve().parents[2], Path.home() / "fairscape")

# module, distribution, repo dir / GitHub slug, why it is needed
REQUIRED = [
    ("fairscape_models", "fairscape-models", "fairscape_models",
     "the entity models every box is validated against"),
    ("fairscape_conversion", "fairscape-conversion", "fairscape_conversion",
     "the converters behind every Import and Export choice"),
    ("fastapi", "fastapi", None, "the local web server"),
    ("uvicorn", "uvicorn", None, "runs the local web server"),
    ("pydantic", "pydantic", None, "request models"),
    ("yaml", "pyyaml", None, "reads the converters' mapping files"),
]

OPTIONAL = [
    ("fairscape_artifacts", "fairscape-artifacts", "fairscape_artifacts",
     "Artifacts ▾ → Build all artifacts (datasheet, preview, evidence graph)"),
    ("aireadiness_evidence", "aireadiness-grader", "AIreadiness-grader",
     "the AI-readiness review page and the Improve list"),
]


def checkout(name: str) -> Path | None:
    """A sibling checkout of one of the other fairscape repos, if there is one."""
    for parent in SIBLINGS:
        p = parent / name
        if (p / "pyproject.toml").is_file():
            return p
    return None


def install_command(dist: str, repo: str | None) -> str:
    """Editable from the checkout beside us when there is one, else from PyPI.

    Always the *running* interpreter, so it lands in the env the studio will
    start in rather than whatever ``pip`` happens to be first on PATH.
    """
    src = checkout(repo) if repo else None
    target = f"-e {src}" if src else dist
    return f"{sys.executable} -m pip install {target}"


def _state(module: str) -> tuple[bool, str]:
    """(importable, note). A directory of the same name in the current working
    directory shadows the installed package and imports as an empty namespace —
    it is the usual reason a correct install still does not work."""
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return False, ""
    if spec is None:
        return False, ""
    if spec.origin is None:  # namespace package: a bare directory, no __init__
        where = (spec.submodule_search_locations or [""])[0]
        return False, (f"a directory named {module}/ in this folder shadows the "
                       f"installed package ({where})")
    return True, ""


def _clone_hint(repo: str) -> str:
    return (f"git clone https://github.com/fairscape/{repo}  "
            f"# then: {sys.executable} -m pip install -e {repo}")


def report(table) -> list[dict]:
    out = []
    for module, dist, repo, why in table:
        ok, note = _state(module)
        out.append({"module": module, "package": dist, "repo": repo, "why": why,
                    "ok": ok, "note": note,
                    "install": install_command(dist, repo),
                    "checkout": str(checkout(repo)) if repo else ""})
    return out


def missing() -> list[dict]:
    return [d for d in report(REQUIRED) if not d["ok"]]


def _tool(name: str) -> str:
    return shutil.which(name) or ""


def env_name() -> str:
    """The environment the studio is actually running in — taken from the
    interpreter, not from CONDA_DEFAULT_ENV, which names the *shell's* env and
    is routinely a different one."""
    prefix = Path(sys.prefix)
    if (prefix / "conda-meta").is_dir():
        return (f"conda env {prefix.name}" if prefix.parent.name == "envs"
                else f"conda base ({prefix})")
    if prefix != Path(sys.base_prefix):
        return f"venv {prefix}"
    return "(none — this is a base/system python)"


def environment() -> dict:
    """Everything the --check output and /api/info want to say about this env."""
    return {
        "python": sys.executable,
        "python_version": ".".join(str(n) for n in sys.version_info[:3]),
        "env": env_name(),
        "cwd": os.getcwd(),
        "required": report(REQUIRED),
        "optional": report(OPTIONAL),
        "nextflow": _tool("nextflow"),
        "snakemake": _tool("snakemake"),
    }


def problem_text() -> str:
    """The message for a refused start: what is missing, why, and the exact
    command that fixes it in *this* interpreter."""
    bad = missing()
    if sys.version_info < MIN_PYTHON and not bad:
        return (f"RO-Crate Studio needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer; "
                f"this is {sys.version.split()[0]} ({sys.executable}).")
    shadowed = [d for d in bad if d["note"]]
    absent = [d for d in bad if not d["note"]]
    headline = ("RO-Crate Studio will not start: it is a GUI over the other fairscape "
                "repos,\nand this environment cannot import "
                + ("them." if len(bad) > 1 else "one of them."))
    lines = [headline, "",
             f"  python      {sys.executable}",
             f"  environment {env_name()}",
             f"  folder      {os.getcwd()}",
             ""]
    for d in shadowed:
        lines += [f"  ✗ {d['module']} — {d['why']}",
                  f"      {d['note']}."]
    if shadowed:
        lines += ["",
                  "  The package is probably installed and fine; it is the folder you",
                  "  started from. cd somewhere else and run it again."]
    for d in absent:
        lines += [f"  ✗ {d['module']} — {d['why']}", f"      {d['install']}"]
        if d["repo"] and not d["checkout"]:
            lines.append(f"      or  {_clone_hint(d['repo'])}")
    if absent:
        lines += ["",
                  "  Or install the studio itself, which pulls in the required ones:",
                  f"      {sys.executable} -m pip install -e {Path(__file__).resolve().parents[1]}"]
    lines += ["",
              "  INSTALL.md has the whole setup, including the optional panels.",
              "  ROCRATE_STUDIO_SKIP_CHECKS=1 starts anyway; every panel that needs a",
              "  missing package then fails when it is used."]
    return "\n".join(lines)


def require() -> None:
    """Refuse to start when a required package is missing. Never raises for the
    optional ones."""
    if os.environ.get("ROCRATE_STUDIO_SKIP_CHECKS"):
        return
    if sys.version_info >= MIN_PYTHON and not missing():
        return
    sys.stderr.write(problem_text() + "\n")
    raise SystemExit(1)


def print_report() -> int:
    """``--check``: the whole picture, required and optional. Exit 1 if the
    studio would refuse to start."""
    env = environment()
    print(f"python       {env['python']}  ({env['python_version']})")
    print(f"environment  {env['env']}")
    print(f"cwd          {env['cwd']}")
    print("\nrequired — the studio will not start without these")
    for d in env["required"]:
        mark = "✓" if d["ok"] else "✗"
        print(f"  {mark} {d['module']:<24} {d['why']}")
        if not d["ok"]:
            print(f"      {d['note'] or d['install']}")
    print("\noptional — each one is a panel, missing only disables that panel")
    for d in env["optional"]:
        mark = "✓" if d["ok"] else "·"
        print(f"  {mark} {d['module']:<24} {d['why']}")
        if not d["ok"]:
            print(f"      {d['install']}")
    nf = env["nextflow"] or "not on PATH — the Nextflow run-live choice is unavailable"
    sm = env["snakemake"] or "not on PATH — found in any conda env at run time"
    print(f"\n  nextflow   {nf}")
    print(f"  snakemake  {sm}")
    bad = bool(missing()) or sys.version_info < MIN_PYTHON
    print("\n" + ("some required packages are missing — see above"
                  if bad else "ready: rocrate-studio will start"))
    return 1 if bad else 0


def startup_note() -> str:
    """One line after the required check passes: which panels this environment
    cannot run. Empty when everything is there."""
    absent = [d for d in report(OPTIONAL) if not d["ok"]]
    if not absent:
        return ""
    names = ", ".join(d["package"] for d in absent)
    return (f"note: {names} not installed — "
            f"the Artifacts and Improve panels will offer to install what they need")
