"""The specialised properties fairscape_models knows about, grouped for humans.

Everything (names, aliases, descriptions, required flags, value kinds) is read
from the pydantic models at import time, so this stays in step with
fairscape_models. Only the grouping and the plain-language group blurbs are
hand-written here.
"""
from __future__ import annotations

import re

from fairscape_models.computation import Computation
from fairscape_models.dataset import Dataset
from fairscape_models.mlmodel import MLModel
from fairscape_models.rocrate import ROCrateMetadataElem
from fairscape_models.software import Software

MODELS = {"root": ROCrateMetadataElem, "dataset": Dataset, "software": Software,
          "computation": Computation, "mlmodel": MLModel}

# never offered in the editor: structural, auto-derived, or edited elsewhere
SKIP = {"@id", "@type", "@context", "conformsTo", "hasPart", "isPartOf", "fairscapeVersion",
        "additionalType", "additionalProperty", "prov:used", "prov:wasAssociatedWith",
        "prov:wasGeneratedBy", "prov:wasDerivedFrom", "prov:wasAttributedTo", "evi:annotatedBy"}

# (group title, blurb, [aliases]) — first match wins; prefixes handled after
GROUPS = {
    "root": [
        ("Basics", "What it is, when, and in what state.",
         ["name", "description", "keywords", "version", "datePublished", "dateCreated", "dateModified",
          "url", "language", "creativeWorkStatus", "about", "correction"]),
        ("People & credit", "Who made it, paid for it, and how to cite it. Feeds Findability and Provenance scores.",
         ["author", "publisher", "principalInvestigator", "funder", "contactEmail", "citation",
          "associatedPublication", "identifier"]),
        ("Access & licensing", "Can others use it, and under what terms?",
         ["license", "conditionsOfAccess", "copyrightNotice", "usageInfo", "prohibitedUses"]),
        ("Ethics & governance", "Human subjects, IRB, sensitivity, oversight.",
         ["humanSubjectResearch", "ethicalReview", "irb", "irbProtocolId", "humanSubjectExemption",
          "deidentified", "fdaRegulated", "confidentialityLevel", "dataGovernanceCommittee",
          "d4d:informedConsent", "d4d:atRiskPopulations", "d4d:participantPrivacy", "d4d:contentWarning"]),
        ("Responsible AI (Croissant RAI)", "How the data was collected, cleaned, annotated, and where it falls short. The core of an AI-Ready description.",
         []),  # rai:* filled below
        ("Datasheet for Datasets (D4D)", "Remaining datasheet questions: gaps, anomalies, subsets, sampling.",
         []),  # d4d:* filled below
        ("Content & integrity", "Size, checksums, completeness, summary statistics.",
         ["contentSize", "md5", "sha256", "hash", "completeness", "hasSummaryStatistics"]),
        ("Computed roll-ups (evi:)", "Filled in automatically by the FAIRSCAPE server when a release is processed. You rarely set these by hand.",
         []),  # evi:* filled below
    ],
    "dataset": [
        ("Basics", "", ["name", "description", "author", "keywords", "version", "datePublished"]),
        ("File & format", "Where the bytes are and how to read them.", ["contentUrl", "format", "contentSize", "md5", "sha256", "hash"]),
        ("Shape & schema", "Helps tools and people understand the table.", ["rowCount", "columnCount", "sampleSize", "dataSchema", "splits", "hasSummaryStatistics"]),
        ("Provenance", "How this data came to be.", ["generatedBy", "derivedFrom", "usedByComputation"]),
        ("Documentation", "", ["associatedPublication", "additionalDocumentation"]),
    ],
    "software": [
        ("Basics", "", ["name", "description", "author", "version", "dateModified"]),
        ("File & format", "", ["contentUrl", "format", "md5", "sha256", "hash"]),
        ("Provenance", "", ["usedByComputation"]),
        ("Documentation", "", ["associatedPublication", "additionalDocumentation"]),
    ],
    "computation": [
        ("Basics", "", ["name", "description", "runBy", "dateCreated"]),
        ("What ran", "", ["command", "parameter", "usedSoftware", "usedContainer"]),
        ("Inputs & outputs", "", ["usedDataset", "usedMLModel", "generated"]),
        ("Documentation", "", ["associatedPublication", "additionalDocumentation"]),
    ],
    "mlmodel": [
        ("Basics", "", ["name", "description", "author", "version", "dateModified"]),
        ("Model", "", ["modelTask", "modelArchitecture", "trainedOn"]),
        ("File & format", "", ["contentUrl", "format", "md5", "sha256", "hash"]),
        ("Provenance", "", ["generatedBy", "derivedFrom", "usedByComputation"]),
        ("Documentation", "", ["associatedPublication", "additionalDocumentation"]),
    ],
}
PREFIX_GROUP = {"rai:": "Responsible AI (Croissant RAI)", "d4d:": "Datasheet for Datasets (D4D)",
                "evi:": "Computed roll-ups (evi:)"}


def _kind(annotation: str) -> str:
    a = annotation
    if "bool" in a:
        return "bool"
    if "int" in a and "Identifier" not in a and "str" not in a:
        return "int"
    if any(t in a for t in ("IdentifierValue", "Person", "Organization", "DefinedTerm")) and "str" not in a:
        return "ref"
    if "List[str]" in a or "list[str]" in a:
        return "list"
    return "text"


def _nice(alias: str) -> str:
    base = alias.split(":", 1)[-1]
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", base).replace("_", " ")
    words = words[0].upper() + words[1:]
    fix = {"Url": "URL", "Irb": "IRB", "Fda": "FDA", "Md5": "MD5", "Sha256": "SHA-256", "Id": "ID", "Ml": "ML"}
    return " ".join(fix.get(w, w) for w in words.split(" "))


def fields_for(kind: str) -> list[dict]:
    model = MODELS[kind]
    groups = {title: {"title": title, "blurb": blurb, "fields": []} for title, blurb, _ in GROUPS[kind]}
    where = {alias: title for title, _, aliases in GROUPS[kind] for alias in aliases}
    other = {"title": "Other", "blurb": "", "fields": []}
    for name, f in model.model_fields.items():
        alias = f.alias or name
        if alias in SKIP:
            continue
        ann = str(f.annotation)
        entry = {"key": alias, "label": _nice(alias), "help": (f.description or "").strip(),
                 "required": f.is_required(), "kind": _kind(ann)}
        title = where.get(alias) or next((g for p, g in PREFIX_GROUP.items() if alias.startswith(p)), None)
        (groups[title] if title in groups else other)["fields"].append(entry)
    out = [g for g in groups.values() if g["fields"]]
    if other["fields"]:
        out.append(other)
    return out


ALL = {k: fields_for(k) for k in MODELS}
