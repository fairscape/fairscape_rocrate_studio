"""The examples page: what each worked example needs, and whether this machine has it.

Most examples reuse what the studio already offers (a conversion plugin's
sample, the bundled Nextflow and Snakemake workflows), so the page only needs
the extra facts about the Cell Maps demo: a finished package anyone can open,
and the real pipeline, which runs live only where Nextflow, conda and
nf-fairscape >= 0.2.0 are set up.
"""
from __future__ import annotations

import shutil

from . import crate_ops, nextflow_runner, samples

#: the Cell Maps pipeline is pinned to this plugin release in its nextflow.config
CELLMAPS_PLUGIN = (0, 2, 0)
#: finished packages that open straight onto the map
FINISHED = {"cellmaps": "cellmaps-finished"}


def cellmaps() -> dict:
    nf = nextflow_runner.info()
    reason = [nf["reason"]] if nf["reason"] else []
    newest = nextflow_runner.plugin_versions()
    if not newest or tuple(int(x) for x in newest[-1].split(".")) < CELLMAPS_PLUGIN:
        reason.append("the Cell Maps pipeline needs nf-fairscape 0.2.0 or newer")
    if not (shutil.which("conda") or shutil.which("mamba") or shutil.which("micromamba")):
        reason.append("conda is not on PATH (each step builds its own conda environment)")
    out = {"available": not reason, "reason": "; ".join(r for r in reason if r)}
    # copied only when it could run, so an unready machine does not get a stray folder
    out["pipeline"] = samples.workflow("cellmaps-pipeline") if not reason else None
    return out


def info() -> dict:
    return {"cellmaps": cellmaps()}


def open_finished(name: str) -> tuple[dict, str]:
    folder = FINISHED.get(name)
    if not folder:
        raise KeyError(f"no finished example called {name!r}")
    dst = samples.copy(samples.EXAMPLES / folder, folder, fresh=True)
    crate, path = crate_ops.read_crate(str(dst))
    return crate, str(path)
