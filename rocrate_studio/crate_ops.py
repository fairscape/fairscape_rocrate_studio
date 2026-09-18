"""Crate operations the GUI needs that neither library provides directly.

fairscape_conversion returns crates as JSON-LD dicts and fairscape_models only
validates them, so reading, writing, adding hand-made entities and per-entity
validation live here. Everything works on the plain dict the frontend holds.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
from pathlib import Path

from fairscape_conversion.core.arks import mint_ark
from fairscape_models.fairscape_base import DEFAULT_CONTEXT
from fairscape_models.rocrate import ROCrateMetadataElem, ROCrateV1_2

EVI = "https://w3id.org/EVI#"
DESCRIPTOR_ID = "ro-crate-metadata.json"

TYPE_IRI = {
    "Dataset": ["prov:Entity", EVI + "Dataset"],
    "Software": ["prov:Entity", EVI + "Software"],
    "MLModel": ["prov:Entity", EVI + "MLModel"],
    "Computation": ["prov:Activity", EVI + "Computation"],
    "Schema": EVI + "Schema",
}
PREFIX = {"Dataset": "dataset", "Software": "software", "MLModel": "mlmodel",
          "Computation": "computation", "Schema": "schema"}


# ------------------------------------------------------------------ read / write

def read_crate(path: str | os.PathLike) -> tuple[dict, Path]:
    p = Path(path).expanduser()
    if p.is_dir():
        p = p / DESCRIPTOR_ID
    if not p.is_file():
        raise FileNotFoundError(f"no {DESCRIPTOR_ID} at {p}")
    return json.loads(p.read_text()), p.parent


def write_crate(crate: dict, folder: str | os.PathLike) -> list[str]:
    d = Path(folder).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    target = d / DESCRIPTOR_ID
    target.write_text(json.dumps(crate, indent=2, default=str))
    return [str(target)]


# ------------------------------------------------------------------ build

def _now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def root_of(crate: dict) -> dict | None:
    desc = next((n for n in crate["@graph"] if n.get("@id") == DESCRIPTOR_ID), None)
    about = desc and desc.get("about")
    rid = about.get("@id") if isinstance(about, dict) else about
    if rid:
        return next((n for n in crate["@graph"] if n.get("@id") == rid), None)
    return next((n for n in crate["@graph"] if "ROCrate" in str(n.get("@type"))), None)


def new_crate(name: str, author: str = "", description: str = "", keywords=None,
              naan: str = "59853", license: str = "https://spdx.org/licenses/CC-BY-4.0") -> dict:
    name = name.strip() or "Untitled crate"
    rid = mint_ark(naan, "rocrate", name, f"{name}|{_now()}")
    root = {
        "@id": rid,
        "@type": ["Dataset", EVI + "ROCrate"],
        "conformsTo": {"@id": "https://w3id.org/fairscape/profile/0.1"},
        "name": name,
        "description": description.strip() or f"RO-Crate '{name}' created in RO-Crate Studio.",
        "author": author.strip() or os.environ.get("USER", "unknown"),
        "keywords": keywords or ["ro-crate"],
        "license": license,
        "version": "1.0",
        "datePublished": _now(),
        "hasPart": [],
    }
    descriptor = {
        "@id": DESCRIPTOR_ID,
        "@type": "CreativeWork",
        "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"},
        "about": {"@id": rid},
    }
    return {"@context": dict(DEFAULT_CONTEXT), "@graph": [descriptor, root]}


def add_entity(crate: dict, type_: str, name: str, naan: str = "59853") -> str:
    """Append a minimally valid entity of ``type_`` and register it in hasPart."""
    if type_ not in TYPE_IRI:
        raise ValueError(f"type must be one of {', '.join(TYPE_IRI)}")
    name = name.strip() or type_
    root = root_of(crate)
    author = (root or {}).get("author", "unknown")
    guid = mint_ark(naan, PREFIX[type_], name, f"{type_}|{name}|{_now()}")
    node = {"@id": guid, "@type": TYPE_IRI[type_], "name": name,
            "description": f"{type_} '{name}' added in RO-Crate Studio."}
    if type_ == "Computation":
        node.update(runBy=author, dateCreated=_now(), command="")
    elif type_ == "Schema":
        node.update(properties={})
    else:
        node.update(author=author, format="", version="1.0",
                    datePublished=_now(), keywords=list((root or {}).get("keywords") or ["data"]))
        if type_ == "Dataset":
            node["contentUrl"] = ""
    crate["@graph"].append(node)
    if root is not None:
        parts = [p if isinstance(p, dict) else {"@id": p} for p in root.get("hasPart") or []]
        parts.append({"@id": guid})
        root["hasPart"] = parts
    return guid


# ------------------------------------------------------------------ validate

def _ids(value) -> list[str]:
    out = []
    for v in value if isinstance(value, list) else [value]:
        if isinstance(v, dict) and "@id" in v:
            out.append(v["@id"])
        elif isinstance(v, str) and (v.startswith("ark:") or v.startswith("#")):
            out.append(v)
    return out


def _short(msg: str) -> str:
    return re.sub(r"\s+\[type=.*$", "", msg).strip()


def validate(crate: dict) -> dict:
    """Whole-crate validation plus per-entity problems the GUI can pin on nodes."""
    problems: dict[str, list[str]] = {}

    def add(guid, msg):
        problems.setdefault(guid, []).append(msg)

    # 1. per-entity pydantic errors, through the same dispatch ROCrateV1_2 uses
    for node in crate["@graph"]:
        one = {"@context": crate.get("@context", DEFAULT_CONTEXT), "@graph": [node]}
        try:
            ROCrateV1_2.model_validate(copy.deepcopy(one))
        except Exception as e:  # pydantic.ValidationError has .errors()
            errs = getattr(e, "errors", None)
            if callable(errs):
                for err in errs():
                    loc = ".".join(str(x) for x in err.get("loc", ()) if not isinstance(x, int) and x != "@graph")
                    add(node.get("@id", "?"), f"{loc or 'entity'}: {_short(err.get('msg', ''))}")
            else:
                add(node.get("@id", "?"), _short(str(e)))

    # 2. empty values and dangling references
    known = {n.get("@id") for n in crate["@graph"]}
    for node in crate["@graph"]:
        for key, value in node.items():
            if key.startswith("@"):
                continue
            if value == "":
                add(node["@id"], f"{key} is empty")
                continue
            for ref in _ids(value):
                if ref.startswith("ark:") and ref not in known:
                    add(node["@id"], f"{key} points at {ref}, which is not in this crate")

    # 3. root-level advice
    root = root_of(crate)
    advice = []
    if root is not None:
        parts = set(_ids(root.get("hasPart") or []))
        for node in crate["@graph"]:
            gid = node.get("@id")
            if gid not in (DESCRIPTOR_ID, root["@id"]) and gid not in parts and str(gid).startswith("ark:"):
                add(gid, "not listed in the crate root's hasPart")
        try:
            advice = ROCrateMetadataElem.model_validate(copy.deepcopy(root)).get_aiready_warnings()
        except Exception:
            pass

    ok = not problems
    counts = {}
    for n in crate["@graph"]:
        t = n.get("@type")
        t = t[-1] if isinstance(t, list) else t
        t = str(t).split("#")[-1].split(":")[-1]
        counts[t] = counts.get(t, 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    return {"ok": ok, "summary": summary, "problems": problems, "advice": advice}
