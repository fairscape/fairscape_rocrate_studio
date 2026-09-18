"""The Improve list: the grader's quick-wins catalogue ranked by the crate's
latest AI-readiness estimate.

Two sources, merged here and nowhere else:

* ``aireadiness_improve.fields.catalogue()`` — every single property the
  improvements form knows how to set on the crate root or on a Software
  entity, with the criteria it feeds, whether filling it is a sure point
  (``win``) and how much work it is (``effort`` 1/2/3).
* ``ai-ready-presentation.json`` beside the crate — per criterion, the
  mechanical estimate (``'0'``/``'1'``/``'2'`` or absent) and its basis. This
  says which criteria are short.

The ranking is: rows that lift a criterion currently below 2 first, then by
effort, then sure points, then by how many short criteria they lift. The
out-of-scope jobs (new entities, links, hashes, statistics — the things the
inline editor deliberately does not do) come back separately with the Claude
Code skill that performs each one.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import artifacts_runner

# the post-grade-improve skill's table: which leaf skill closes which criterion
SKILLS = [
    ("link-authors-orcids", "Link authors to their ORCIDs", ["1.d"],
     "Turns author strings into Person entities carrying ORCID URLs."),
    ("link-subjects-ontologies", "Ground the subject in ontology terms", ["2.a", "2.c"],
     "Adds DefinedTerm entities (MeSH, OBO, NCIt, …) for what the data is about."),
    ("ethics-questionnaire", "Ethics questionnaire", ["4.a", "4.b", "4.d"],
     "Interviews you for the ethics framework, IRB, consent, de-identification and "
     "the HL7 confidentiality code, and writes them all at once."),
    ("compute-summary-stats", "Per-variable summary statistics", ["2.b"],
     "Computes row/column counts and per-column statistics for tabular files and "
     "attaches them as SummaryStats entities."),
    ("hash-coverage", "Checksums on every file", ["3.c"],
     "Computes md5 and sha256 for the crate's Datasets and Software."),
    ("portability-interview", "Compute environment", ["6.c"],
     "Records the container image, environment file and hardware each step ran on."),
]

# criteria the catalogue cannot move and no skill covers: the note says why
NO_SKILL_TITLES = {
    "1.a": "Ground-truth entities (Sample, Instrument, Experiment)",
    "1.b": "Computation steps from the workflow recorder",
    "5.d": "Sub-crates and provenance links",
    "6.b": "Data hosted at accessible URLs",
}


def _root_of(crate: dict) -> dict | None:
    graph = crate.get("@graph", [])
    desc = next((n for n in graph if n.get("@id") == "ro-crate-metadata.json"), None)
    about = desc.get("about") if desc else None
    rid = about.get("@id") if isinstance(about, dict) else about
    return next((n for n in graph if n.get("@id") == rid), None)


def _types(node: dict) -> set[str]:
    out = set()
    for t in [node.get("@type")] if not isinstance(node.get("@type"), list) else node["@type"]:
        if t:
            out.add(str(t).split("#")[-1].split(":")[-1])
    return out


def _filled(v) -> bool:
    return not (v is None or v == "" or (isinstance(v, (list, dict)) and not v))


def _criterion_scores(presentation: dict | None) -> dict[str, dict]:
    """id -> {name, score (int|None), basis}. Names fall back to the rubric so a
    crate with no grade still labels its criteria."""
    out: dict[str, dict] = {}
    if presentation:
        for sec in presentation.get("sections", []):
            for c in sec.get("criteria", []):
                raw = (c.get("estimate") or {}).get("score")
                try:
                    score = int(raw)
                except (TypeError, ValueError):
                    score = None
                out[c["id"]] = {"name": c.get("name", ""), "score": score,
                                "basis": list((c.get("estimate") or {}).get("basis") or [])}
    if not out:
        try:
            from aireadiness_evidence.rubric import load_rubric
            for cid, c in load_rubric().get("criteria", {}).items():
                out[cid] = {"name": c.get("name", ""), "score": None, "basis": []}
        except Exception:  # noqa: BLE001
            pass
    return out


def _short(score) -> bool:
    return score is None or score < 2


def improve(crate_dir: Path) -> dict:
    from aireadiness_improve.fields import EFFORT_LABELS, OUT_OF_SCOPE_NOTES, catalogue

    crate = json.loads((crate_dir / artifacts_runner.CRATE_NAME).read_text(encoding="utf-8"))
    pres_path = artifacts_runner.find_presentation(crate_dir)
    presentation = json.loads(pres_path.read_text(encoding="utf-8")) if pres_path else None
    scores = _criterion_scores(presentation)
    graded = presentation is not None

    root = _root_of(crate)
    software = [n for n in crate.get("@graph", []) if "Software" in _types(n)]

    def crit(cid):
        s = scores.get(cid, {})
        return {"id": cid, "name": s.get("name", ""), "score": s.get("score"), "max": 2}

    items = []
    for entry in catalogue():
        targets = ([("root", root)] if entry["entity"] == "root"
                   else [("software", n) for n in software])
        for kind, node in targets:
            if node is None:
                continue
            criteria = [crit(c) for c in entry["criteria"]]
            lifts = [c for c in criteria if _short(c["score"])] if graded else []
            current = node.get(entry["prop"])
            items.append({
                "effort": entry["effort"],
                "effort_label": EFFORT_LABELS.get(entry["effort"], ""),
                "target": {"@id": node.get("@id"), "kind": kind,
                           "name": node.get("name") or node.get("@id")},
                "property": entry["prop"],
                "label": entry["label"],
                "help": entry.get("help", ""),
                "type": entry["type"],
                "placeholder": entry.get("placeholder", ""),
                "options": entry.get("options"),
                "criteria": criteria,
                "lifts": [c["id"] for c in lifts],
                "win": bool(entry.get("win")),
                "have": _filled(current),
                "current": current,
            })
    if graded:
        items.sort(key=lambda i: (not i["lifts"], i["have"], i["effort"], not i["win"], -len(i["lifts"])))
    else:
        items.sort(key=lambda i: (i["have"], i["effort"], not i["win"]))

    jobs = []
    covered = set()
    for skill, title, cids, why in SKILLS:
        criteria = [crit(c) for c in cids]
        covered.update(cids)
        jobs.append({"title": title, "why": why, "skill": skill, "criteria": criteria,
                     "note": " ".join(OUT_OF_SCOPE_NOTES.get(c, "") for c in cids).strip(),
                     "short": any(_short(c["score"]) for c in criteria) if graded else True})
    for cid, note in OUT_OF_SCOPE_NOTES.items():
        if cid in covered:
            continue
        c = crit(cid)
        jobs.append({"title": NO_SKILL_TITLES.get(cid, c["name"]), "why": note, "skill": None,
                     "criteria": [c], "note": "",
                     "short": _short(c["score"]) if graded else True})
    if graded:
        jobs.sort(key=lambda j: (not j["short"], j["criteria"][0]["id"]))

    out = {"items": items, "bigger_jobs": jobs, "effort_labels": EFFORT_LABELS,
           "needs_grade": not graded, "presentation": str(pres_path) if pres_path else None}
    if graded:
        out["estimate"] = artifacts_runner.estimate_summary(presentation)
    return out
