"""What the GUI knows about each fairscape_conversion plugin.

fairscape_conversion has no registry and does not declare which direction a
plugin supports or which options it takes, so that knowledge lives here as
plain data: one entry per plugin with the form fields the left panel renders
and how to turn the filled-in form into a ``convert(...)`` call.

Field types the frontend understands: string, text, bool, path (file or
dir), file, dir, select.
"""
from __future__ import annotations

from pathlib import Path

import fairscape_conversion

CONVERSION_ROOT = Path(fairscape_conversion.__file__).resolve().parent
PLUGIN_ROOT = CONVERSION_ROOT / "plugins"
EXAMPLES = CONVERSION_ROOT / "examples"

DEFAULT_NAAN = "59853"
DEFAULT_LICENSE = "https://spdx.org/licenses/CC-BY-4.0"


def _crate_meta(name_help="Name of the crate"):
    """The metadata block every workflow importer accepts."""
    return [
        {"name": "name", "label": "Crate name", "type": "string", "help": name_help},
        {"name": "description", "label": "Description", "type": "text"},
        {"name": "author", "label": "Author", "type": "string"},
        {"name": "keywords", "label": "Keywords", "type": "string", "placeholder": "comma, separated"},
        {"name": "license", "label": "License (SPDX URL)", "type": "string", "default": DEFAULT_LICENSE},
        {"name": "naan", "label": "ARK NAAN", "type": "string", "default": DEFAULT_NAAN,
         "help": "Identifier namespace. Leave as-is unless you publish to a FAIRSCAPE server."},
    ]


PLUGINS = {
    "mlflow": {
        "title": "MLflow experiment",
        "blurb": "Runs, params, metrics, logged datasets and models from an MLflow tracking store.",
        "import": True, "export": False,
        "source_kind": "path",           # source is a URI / directory, passed straight to convert
        "sample": {"source": f"sqlite:///{EXAMPLES / 'mlflow' / 'mlflow.db'}",
                   "experiment": "iris-classifier", "copy_artifacts": False, "schemas": True,
                   "name": "Iris classifier — MLflow experiment", "author": "Example Researcher",
                   "keywords": "mlflow, iris, random forest"},
        "options": [
            {"name": "source", "label": "MLflow store: mlflow.db, mlruns folder, or tracking URI", "type": "path", "required": True,
             "placeholder": "/path/to/mlflow.db  or  /path/to/mlruns  or  http://host:5000",
             "help": "A folder that contains mlflow.db or mlruns works too."},
            {"name": "experiment", "label": "Experiment (name or id)", "type": "string", "lookup": "mlflow_experiments",
             "help": "Click Look up to list the experiments in the store. Picked for you if there is only one."},
            {"name": "run_id", "label": "Run id", "type": "string"},
            {"name": "crate_dir", "label": "Crate folder", "type": "dir",
             "help": "Where copied artifacts land. Required if copying artifacts."},
            {"name": "copy_artifacts", "label": "Copy run artifacts into the crate", "type": "bool", "default": False},
            {"name": "schemas", "label": "Infer schemas for tabular artifacts", "type": "bool", "default": True},
            *_crate_meta(),
        ],
    },
    "cromwell": {
        "title": "Cromwell / WDL run",
        "blurb": "A finished Cromwell workflow's metadata.json.",
        "import": True, "export": False,
        "source_kind": "path",
        # a real Cromwell 92 run — bwa/samtools/bcftools scattered over three
        # samples — rather than the toy fixture the plugin tests use
        "sample": {"source": EXAMPLES / "wdl-variant-calling" / "run" / "metadata.json",
                   "crate_dir": str(EXAMPLES / "wdl-variant-calling"),
                   "name": "Variant calling on three sequenced samples (WDL)",
                   "author": "Example Researcher",
                   "keywords": "cromwell, wdl, variant calling, genomics"},
        "options": [
            {"name": "source", "label": "Cromwell metadata.json", "type": "file", "required": True},
            {"name": "crate_dir", "label": "Crate folder", "type": "dir"},
            {"name": "schemas", "label": "Infer schemas for tabular outputs", "type": "bool", "default": False},
            *_crate_meta(),
        ],
    },
    "galaxy": {
        "title": "Galaxy invocation",
        "blurb": "An invocation export from Galaxy (Workflow Invocations → Export; .tar.gz, .zip, "
                 ".rocrate.zip or unpacked), a bare .ga workflow, or a Galaxy server + invocation id.",
        "import": True, "export": False,
        "source_kind": "path",
        "sample": {"source": PLUGIN_ROOT / "galaxy" / "input-store",
                   "crate_dir": PLUGIN_ROOT / "galaxy" / "input-store",
                   "author": "Example Researcher"},
        "options": [
            {"name": "source", "label": "Invocation export (archive or folder), .ga file, or Galaxy URL", "type": "path", "required": True,
             "placeholder": "/path/to/invocation-export.tar.gz  or  https://usegalaxy.org"},
            {"name": "invocation_id", "label": "Invocation id (Galaxy URL only)", "type": "string"},
            {"name": "api_key", "label": "API key (Galaxy URL only)", "type": "string"},
            {"name": "crate_dir", "label": "Crate folder", "type": "dir",
             "help": "File paths in the crate are written relative to this folder."},
            *_crate_meta("Defaults to the workflow's name"),
        ],
    },
    "snakemake": {
        "title": "Snakemake run",
        "blurb": "The records file written by snakemake --reporter fairscape. "
                 "To run the workflow itself, pick \"A Snakemake workflow (run it now)\".",
        "import": True, "export": False,
        "source_kind": "document",       # source is read and parsed before convert
        # the records a real variant-calling run left behind (12 jobs over six
        # rules); plugins/snakemake/input.json is the toy fixture the tests use
        "sample": {"records": EXAMPLES / "snakemake-variant-calling" / "run" / "records.json"},
        "options": [
            {"name": "source", "label": "Snakemake fairscape report (JSON)", "type": "file", "required": True},
        ],
    },
    "redcap": {
        "title": "REDCap project",
        "blurb": "A REDCap data dictionary (CSV download or API metadata JSON), optionally with "
                 "the records export, becomes a tabular schema of the export's columns.",
        "import": True, "export": False,
        "source_kind": "path",
        "sample": {"source": PLUGIN_ROOT / "redcap" / "input-dictionary.csv",
                   "records": PLUGIN_ROOT / "redcap" / "input-records.csv",
                   "crate_dir": PLUGIN_ROOT / "redcap",
                   "name": "Seasonal respiratory illness survey",
                   "author": "Example Public Health Group",
                   "keywords": "redcap, survey, public health, respiratory",
                   "redcap_version": "14.5.10"},
        "options": [
            {"name": "source", "label": "Data dictionary (CSV download or API metadata .json)", "type": "file", "required": True,
             "help": "Project Setup → Data Dictionary → Download, or the API's content=metadata export."},
            {"name": "records", "label": "Records export (CSV)", "type": "file",
             "help": "Data Exports → Export Data → CSV. Its header decides which columns the schema lists."},
            {"name": "labels", "label": "Export used labels rather than raw codes", "type": "bool", "default": False},
            {"name": "redcap_version", "label": "REDCap version", "type": "string",
             "help": "Shown under Help & FAQ in REDCap; it is not written into the files."},
            {"name": "crate_dir", "label": "Crate folder", "type": "dir",
             "help": "File paths in the crate are written relative to this folder."},
            *_crate_meta("Defaults to the project name REDCap put in the file name"),
        ],
    },
    "d4d": {
        "title": "Datasheet for Datasets",
        "blurb": "A D4D datasheet (YAML or JSON) becomes a crate with one dataset.",
        "import": True, "export": True,
        "source_kind": "document",
        "sample": {"document": PLUGIN_ROOT / "d4d" / "input.yaml"},
        "options": [
            {"name": "source", "label": "Datasheet file (.yaml / .json)", "type": "file", "required": True},
            {"name": "validate", "label": "Validate result with fairscape_models", "type": "bool", "default": True},
        ],
        "export_ext": ".yaml",
    },
    "wrroc": {
        "title": "Workflow Run RO-Crate",
        "blurb": "A WRROC (CWL, Galaxy, …) ro-crate-metadata.json, re-expressed as EVI provenance.",
        "import": True, "export": True,
        "source_kind": "document",
        "sample": {"document": PLUGIN_ROOT / "wrroc" / "input.json"},
        "options": [
            {"name": "source", "label": "WRROC ro-crate-metadata.json", "type": "file", "required": True},
            {"name": "naan", "label": "ARK NAAN", "type": "string", "default": DEFAULT_NAAN},
            {"name": "validate", "label": "Validate result with fairscape_models", "type": "bool", "default": True},
        ],
        "export_ext": ".json",
    },
    "frictionless": {
        "title": "Frictionless Data Package",
        "blurb": "Any datapackage.json: a Dataset per resource and a tabular schema per Table Schema. "
                 "Export writes a datapackage.json for any crate.",
        "import": True, "export": True,
        "source_kind": "path",
        "sample": {"source": PLUGIN_ROOT / "frictionless" / "input-datapackage",
                   "crate_dir": PLUGIN_ROOT / "frictionless" / "input-datapackage"},
        "options": [
            {"name": "source", "label": "Package folder or datapackage.json", "type": "path", "required": True},
            {"name": "crate_dir", "label": "Crate folder", "type": "dir",
             "help": "File paths in the crate are written relative to this folder."},
            *_crate_meta("Defaults to the package's title"),
        ],
        "export_ext": ".json",
    },
    "c2m2": {
        "title": "CFDE C2M2 datapackage",
        "blurb": "A folder of C2M2 TSVs plus C2M2_datapackage.json.",
        "import": True, "export": False,
        "source_kind": "path",
        "sample": {"source": PLUGIN_ROOT / "c2m2" / "input-datapackage"},
        "options": [
            {"name": "source", "label": "Datapackage folder", "type": "dir", "required": True},
            {"name": "output_path", "label": "Crate folder", "type": "dir",
             "help": "The plugin writes the crate and copies the tables here."},
            {"name": "author", "label": "Author", "type": "string"},
            {"name": "publisher", "label": "Publisher", "type": "string"},
            {"name": "naan", "label": "ARK NAAN", "type": "string", "default": DEFAULT_NAAN},
        ],
    },
    "cpm": {
        "title": "Common Provenance Model crate",
        "blurb": "A CPM RO-Crate folder with its PROV bundles.",
        "import": True, "export": True,
        "source_kind": "path",
        "sample": {"source": PLUGIN_ROOT / "cpm" / "input-crate"},
        "options": [
            {"name": "source", "label": "CPM crate folder", "type": "dir", "required": True},
            {"name": "naan", "label": "ARK NAAN", "type": "string", "default": DEFAULT_NAAN},
        ],
        "export_ext": ".json",
    },
    "croissant": {
        "title": "MLCommons Croissant",
        "blurb": "Export only: an EVI crate as a Croissant document.",
        "import": False, "export": True,
        "source_kind": "document",
        "options": [],
        "export_ext": ".json",
    },
}


def public_list():
    """What /api/plugins returns."""
    out = []
    for name, p in PLUGINS.items():
        out.append({
            "name": name, "title": p["title"], "blurb": p["blurb"],
            "import": p["import"], "export": p["export"],
            "options": p["options"], "sample": bool(p.get("sample")),
        })
    return out
