"""The examples behind "Try it with our example first".

Every sample is copied into the studio's output folder before it is used, so a
plain ``pip install`` works: nothing is read from a source checkout and nothing
is written inside the installed package. The studio's own bundles live in
``examples/``; the conversion plugins' small fixtures stay in
fairscape_conversion and are copied the same way.

A bundle that recorded absolute paths (a Cromwell metadata.json, an MLflow
store) has them replaced by ``@@SAMPLE_DIR@@``; the copy gets its own folder
written back in, in text files and in SQLite databases alike.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from . import access

EXAMPLES = Path(__file__).resolve().parent / "examples"
OUT_DIR = Path(os.environ.get("ROCRATE_STUDIO_OUT", Path.home() / "rocrate-studio-out"))
PLACEHOLDER = "@@SAMPLE_DIR@@"

#: sample option keys that hold a path relative to the sample's folder
PATH_KEYS = ("source", "crate_dir", "records", "document", "output_path")


def user_out_dir() -> Path:
    """``OUT_DIR``, or the visitor's own folder in it on a multi-user studio."""
    return access.user_dir(OUT_DIR)


def copy(src: Path, name: str, fresh: bool = True, out_dir: Path | None = None) -> Path:
    """Copy a sample folder to ``OUT_DIR/examples/<name>`` and fill in its paths.

    ``fresh`` starts from a clean copy (a conversion sample: the previous try's
    package is thrown away). Without it the bundled files are refreshed but a
    workflow's earlier results are kept.
    """
    dst = Path(out_dir or user_out_dir()) / "examples" / name
    if fresh and dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.py", "*.pyc", ".snakemake", "work", ".nextflow*"))
    _fill_paths(dst)
    return dst


def _fill_paths(root: Path) -> None:
    here = str(root.resolve())
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix == ".db":
            _fill_sqlite(p, here)
            continue
        data = p.read_bytes()
        if PLACEHOLDER.encode() in data:
            p.write_bytes(data.replace(PLACEHOLDER.encode(), here.encode()))


def _fill_sqlite(db: Path, here: str) -> None:
    con = sqlite3.connect(db)
    try:
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        for t in tables:
            for col in [r[1] for r in con.execute(f'pragma table_info("{t}")')]:
                con.execute(f'update "{t}" set "{col}" = replace("{col}", ?, ?) '
                            f'where typeof("{col}") = \'text\' and "{col}" like ?',
                            (PLACEHOLDER, here, f"%{PLACEHOLDER}%"))
        con.commit()
    finally:
        con.close()


def materialize(plugin: str, sample: dict, out_dir: Path | None = None) -> tuple[dict, Path]:
    """A conversion sample, copied and with its relative paths made absolute.

    ``sample["dir"]`` is the folder to copy; the keys in ``PATH_KEYS`` are
    relative to it. Returns the resolved sample options and the copy's folder.
    """
    work = copy(Path(sample["dir"]), plugin, out_dir=out_dir)
    opts = {}
    for k, v in sample.items():
        if k == "dir":
            continue
        if k in PATH_KEYS:
            v = str((work / v).resolve())
        opts[k] = v
    return opts, work


def workflow(name: str) -> str | None:
    """A run-it-now example (Nextflow or Snakemake), copied where it can run."""
    src = EXAMPLES / name
    if not src.is_dir():
        return None
    try:
        return str(copy(src, name, fresh=False))
    except OSError:
        return None
