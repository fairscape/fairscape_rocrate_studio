"""Linked crates in the studio: the conversion option, the action for a crate
that is already open, what the validator must stop complaining about, and the
pointer being rewritten when a crate is saved somewhere new.

The convention itself lives in ``fairscape_conversion.core.linking`` and is
tested there; these are the studio's own rules about it. Everything runs
against crates written into ``tmp_path``, so no workflow runs and no network.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient          # noqa: E402

from rocrate_studio import crate_ops               # noqa: E402
from rocrate_studio.app import app                 # noqa: E402

EVI = "https://w3id.org/EVI#"
UP_ROOT = "ark:59853/rocrate-upstream-1111111"
UP_RUN = "ark:59853/computation-run-2222222"
UP_FILE = "ark:59853/dataset-table-tsv-3333333"
C_ROOT = "ark:59853/rocrate-consumer-9999999"
C_IN = "ark:59853/dataset-table-tsv-aaaaaaa"
C_RUN = "ark:59853/computation-analysis-ddddddd"
C_OUT = "ark:59853/dataset-result-json-fffffff"

client = TestClient(app)


def _write(path: Path, crate: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(crate))
    return path


@pytest.fixture
def upstream(tmp_path):
    """A crate that produced table.tsv, with the file really on disk."""
    d = tmp_path / "upstream"
    d.mkdir()
    (d / "table.tsv").write_text("a\tb\n1\t2\n")
    _write(d / "ro-crate-metadata.json", {"@context": {}, "@graph": [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": UP_ROOT},
         "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"}},
        {"@id": UP_ROOT, "@type": ["Dataset", EVI + "ROCrate"], "name": "Upstream run",
         "description": "the producer", "author": "Up Stream", "keywords": ["up"],
         "license": "https://spdx.org/licenses/CC-BY-4.0", "datePublished": "2026-01-01",
         "version": "1.0", "hasPart": [{"@id": UP_RUN}, {"@id": UP_FILE}],
         EVI + "outputs": [{"@id": UP_FILE}]},
        {"@id": UP_RUN, "@type": ["prov:Activity", EVI + "Computation"], "name": "RUN",
         "description": "the step that produced the table", "runBy": "Up Stream", "dateCreated": "2026-01-01",
         "generated": [{"@id": UP_FILE}]},
        {"@id": UP_FILE, "@type": ["prov:Entity", EVI + "Dataset"], "name": "table.tsv",
         "description": "File 'table.tsv' produced by RUN", "author": "Up Stream",
         "datePublished": "2026-01-01", "keywords": ["up"], "format": "text/tab-separated-values",
         "contentUrl": "table.tsv", "generatedBy": [{"@id": UP_RUN}]},
    ]})
    return d


def _consumer(up: Path) -> dict:
    """A crate that used that file, with its own identifier for it."""
    return {"@context": {}, "@graph": [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": C_ROOT},
         "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"}},
        {"@id": C_ROOT, "@type": ["Dataset", EVI + "ROCrate"], "name": "Consumer",
         "description": "the consumer", "author": "Down Stream", "keywords": ["down"],
         "license": "https://spdx.org/licenses/CC-BY-4.0", "datePublished": "2026-02-01",
         "version": "1.0",
         "hasPart": [{"@id": C_IN}, {"@id": C_RUN}, {"@id": C_OUT}],
         EVI + "inputs": [{"@id": C_IN}], EVI + "outputs": [{"@id": C_OUT}]},
        {"@id": C_IN, "@type": ["prov:Entity", EVI + "Dataset"], "name": "table",
         "description": "the table this run read in", "author": "Down Stream", "datePublished": "2026-02-01",
         "keywords": ["down"], "format": "text/tab-separated-values",
         "localPath": str(up / "table.tsv"), "generatedBy": []},
        {"@id": C_RUN, "@type": ["prov:Activity", EVI + "Computation"], "name": "analysis",
         "description": "read the upstream table and counted its rows", "runBy": "Down Stream", "dateCreated": "2026-02-01",
         "usedDataset": [{"@id": C_IN}], "generated": [{"@id": C_OUT}]},
        {"@id": C_OUT, "@type": ["prov:Entity", EVI + "Dataset"], "name": "result.json",
         "description": "what the analysis wrote out", "author": "Down Stream", "datePublished": "2026-02-01",
         "keywords": ["down"], "format": "application/json", "contentUrl": "result.json",
         "generatedBy": [{"@id": C_RUN}]},
    ]}


def _by_id(crate):
    return {n["@id"]: n for n in crate["@graph"]}


# -- the pass, through the studio --------------------------------------------

def test_link_route_rewrites_the_crate_and_writes_it_back(upstream, tmp_path):
    folder = tmp_path / "consumer"
    folder.mkdir()
    r = client.post("/api/link", json={"crate": _consumer(upstream), "path": str(folder),
                                       "linked": [str(upstream)]})
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] == 1
    assert "1 input(s) resolved" in body["log"]

    nodes = _by_id(body["crate"])
    assert C_IN not in nodes and UP_FILE in nodes            # the upstream's identifier
    assert "generatedBy" not in nodes[UP_FILE]               # a stub carries no provenance
    assert nodes[UP_FILE]["isPartOf"] == [{"@id": UP_ROOT}]
    assert nodes[C_RUN]["usedDataset"] == [{"@id": UP_FILE}]
    assert nodes[UP_ROOT]["ro-crate-metadata"] == "../upstream/ro-crate-metadata.json"
    # written back, so the crate on disk and the one on screen stay the same thing
    assert _by_id(json.loads((folder / "ro-crate-metadata.json").read_text()))[UP_FILE]


def test_link_route_needs_somewhere_to_link_to(upstream, tmp_path):
    r = client.post("/api/link", json={"crate": _consumer(upstream), "path": str(tmp_path),
                                       "linked": []})
    assert r.status_code == 400 and "at least one" in r.json()["detail"]


def test_link_route_says_which_folder_has_no_crate(upstream, tmp_path):
    r = client.post("/api/link", json={"crate": _consumer(upstream), "path": str(tmp_path),
                                       "linked": [str(tmp_path / "empty")]})
    assert r.status_code == 400
    assert "no ro-crate-metadata.json to link to" in r.json()["detail"]


def test_converting_with_the_option_links_in_one_step(upstream, tmp_path):
    """The Snakemake importer, whose records name a path relative to where the
    run happened rather than to the crate — the case the search folders are
    for."""
    records = {
        "settings": {"naan": "59853", "name": "Counting run", "description": "d" * 20,
                     "author": "Down Stream", "keywords": ["down"],
                     "license": "https://spdx.org/licenses/CC-BY-4.0", "version": "1.0",
                     "date_published": "2026-02-01T00:00:00-05:00"},
        "run": {"name": "Counting run", "snakefile": "Snakefile",
                "snakefile_key": str(tmp_path / "run" / "Snakefile"),
                "engine_version": "9.26.1", "starttime": "2026-02-01T00:00:00-05:00",
                "endtime": "2026-02-01T00:00:10-05:00"},
        "jobs": [{"rule": "count", "wildcards": {}, "shellcmd": "wc -l ../upstream/table.tsv",
                  "inputs": ["../upstream/table.tsv"], "outputs": ["count.txt"],
                  "starttime": "2026-02-01T00:00:00-05:00",
                  "endtime": "2026-02-01T00:00:05-05:00"}],
        "rules": {"count": {"name": "count", "docstring": "count the rows"}},
        "files": {"../upstream/table.tsv": {"path": "../upstream/table.tsv",
                                            "locator": "localPath",
                                            "locator_value": "../upstream/table.tsv",
                                            "ark_source": "table.tsv"},
                  "count.txt": {"path": "count.txt", "locator": "contentUrl",
                                "locator_value": "count.txt", "ark_source": "count.txt"}},
        "schemas": {},
    }
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    source = run_dir / "records.json"
    source.write_text(json.dumps(records))

    r = client.post("/api/convert", json={"plugin": "snakemake", "sample": False,
                                          "options": {"source": str(source),
                                                      "linked_crates": [str(upstream)]}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "1 input(s) resolved" in body["log"]
    nodes = _by_id(body["crate"])
    assert UP_FILE in nodes and nodes[UP_FILE]["isPartOf"] == [{"@id": UP_ROOT}]
    assert nodes[UP_ROOT]["ro-crate-metadata"]


def test_converting_without_the_option_is_untouched(upstream, tmp_path):
    r = client.post("/api/convert", json={"plugin": "wrroc", "sample": True, "options": {}})
    assert r.status_code == 200
    assert "linked" not in r.json()["log"]
    assert not any(n.get("ro-crate-metadata") for n in r.json()["crate"]["@graph"])


# -- what the studio must not call a mistake ---------------------------------

def test_a_pointer_is_not_reported_as_missing_from_the_root(upstream, tmp_path):
    """A linked crate is a pointer, not a part of this crate, and neither are
    the stubs that belong to it. Before this rule the validator flagged all
    three as 'not listed in the crate root's hasPart'."""
    folder = tmp_path / "consumer"
    folder.mkdir()
    crate = client.post("/api/link", json={"crate": _consumer(upstream), "path": str(folder),
                                           "linked": [str(upstream)]}).json()["crate"]
    result = client.post("/api/validate", json={"crate": crate}).json()
    assert result["problems"] == {}, result["problems"]
    assert result["ok"]


def test_an_ordinary_entity_missing_from_the_root_is_still_reported(upstream, tmp_path):
    crate = _consumer(upstream)
    crate["@graph"].append({"@id": "ark:59853/dataset-stray-0000000",
                            "@type": ["prov:Entity", EVI + "Dataset"], "name": "stray",
                            "description": "in the graph, not in hasPart",
                            "author": "Down Stream", "datePublished": "2026-02-01",
                            "keywords": ["down"], "format": "text/plain"})
    problems = client.post("/api/validate", json={"crate": crate}).json()["problems"]
    assert "not listed in the crate root's hasPart" in problems["ark:59853/dataset-stray-0000000"]


def test_linked_crates_are_the_pointers_the_root_does_not_contain(upstream, tmp_path):
    folder = tmp_path / "consumer"
    folder.mkdir()
    crate = client.post("/api/link", json={"crate": _consumer(upstream), "path": str(folder),
                                           "linked": [str(upstream)]}).json()["crate"]
    assert list(crate_ops.linked_crates(crate)) == [UP_ROOT]

    # the same node listed in hasPart is a constituent of a release, not a link
    _by_id(crate)[C_ROOT]["hasPart"].append({"@id": UP_ROOT})
    assert crate_ops.linked_crates(crate) == {}


# -- saving somewhere else ----------------------------------------------------

def test_saving_a_crate_makes_its_pointer_right_from_where_it_lands(upstream, tmp_path):
    """The studio only learns where a crate lives when it is saved, and it is
    rarely where it was built, so each pointer is recomputed on the way out."""
    built = tmp_path / "built"
    built.mkdir()
    crate = client.post("/api/link", json={"crate": _consumer(upstream), "path": str(built),
                                           "linked": [str(upstream)]}).json()["crate"]
    assert _by_id(crate)[UP_ROOT]["ro-crate-metadata"] == "../upstream/ro-crate-metadata.json"

    elsewhere = tmp_path / "a" / "b" / "saved"
    assert client.post("/api/save", json={"crate": crate, "path": str(elsewhere)}).status_code == 200
    saved = _by_id(json.loads((elsewhere / "ro-crate-metadata.json").read_text()))[UP_ROOT]
    assert saved["ro-crate-metadata"] == "../../../upstream/ro-crate-metadata.json"
    assert os.path.normpath(os.path.join(elsewhere, saved["ro-crate-metadata"])) == \
        str(upstream / "ro-crate-metadata.json")
    assert saved["localPath"] == str(upstream / "ro-crate-metadata.json")


def test_a_pointer_too_far_away_to_be_relative_stays_absolute(upstream, tmp_path):
    crate = _consumer(upstream)
    crate["@graph"].append({"@id": UP_ROOT, "@type": ["Dataset", EVI + "ROCrate"],
                            "name": "Upstream run", "hasPart": [],
                            "ro-crate-metadata": str(upstream / "ro-crate-metadata.json"),
                            "localPath": str(upstream / "ro-crate-metadata.json")})
    deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "saved"
    client.post("/api/save", json={"crate": crate, "path": str(deep)})
    saved = _by_id(json.loads((deep / "ro-crate-metadata.json").read_text()))[UP_ROOT]
    assert saved["ro-crate-metadata"] == str(upstream / "ro-crate-metadata.json")


def test_a_pointer_whose_crate_has_vanished_is_left_alone(tmp_path):
    crate = _consumer(tmp_path / "gone")
    crate["@graph"].append({"@id": UP_ROOT, "@type": ["Dataset", EVI + "ROCrate"],
                            "name": "Upstream run", "hasPart": [],
                            "ro-crate-metadata": "../gone/ro-crate-metadata.json",
                            "localPath": str(tmp_path / "gone" / "ro-crate-metadata.json")})
    folder = tmp_path / "consumer"
    client.post("/api/save", json={"crate": crate, "path": str(folder)})
    saved = _by_id(json.loads((folder / "ro-crate-metadata.json").read_text()))[UP_ROOT]
    assert saved["ro-crate-metadata"] == "../gone/ro-crate-metadata.json"


# -- a live workflow run -------------------------------------------------------

def test_a_finished_run_links_the_crate_it_wrote_and_says_so(upstream, tmp_path):
    """The Nextflow and Snakemake paths write the crate themselves, so the
    pass runs over what the run left on disk, and what it did has to reach the
    log the browser is reading — the lines are added while the final event is
    being built, after the stream has already sent everything else."""
    import asyncio

    from rocrate_studio.app import _crate_payload, _job_stream

    folder = tmp_path / "run-output"
    folder.mkdir()
    _write(folder / "ro-crate-metadata.json", _consumer(upstream))

    class FakeJob:
        id = "test"
        lines = ["$ nextflow run .", "[SUCCESS]"]
        done = True
        ok = True
        crate_file = str(folder / "ro-crate-metadata.json")
        linked_crates = [str(upstream)]

    job = FakeJob()

    async def collect():
        return [chunk async for chunk in _job_stream(job, final=_crate_payload)]

    events = [json.loads(c.removeprefix("data: ").strip()) for c in asyncio.run(collect())]
    lines = [e["line"] for e in events if "line" in e]
    assert "1 input(s) resolved" in " ".join(lines)
    assert events[-1]["done"] and events[-1]["ok"]

    linked = _by_id(events[-1]["crate"])
    assert UP_FILE in linked and C_IN not in linked
    # and the crate the run wrote is the crate on screen
    assert UP_FILE in _by_id(json.loads((folder / "ro-crate-metadata.json").read_text()))


def test_a_run_with_nothing_to_link_is_untouched(upstream, tmp_path):
    from rocrate_studio.app import _crate_payload

    folder = tmp_path / "run-output"
    folder.mkdir()
    before = _consumer(upstream)
    _write(folder / "ro-crate-metadata.json", before)

    class FakeJob:
        lines = []
        done = True
        ok = True
        crate_file = str(folder / "ro-crate-metadata.json")
        linked_crates = []

    payload = _crate_payload(FakeJob())
    assert payload["crate"] == before and FakeJob.lines == []


def test_a_bad_link_folder_never_costs_a_finished_run_its_crate(upstream, tmp_path):
    from rocrate_studio.app import _crate_payload

    folder = tmp_path / "run-output"
    folder.mkdir()
    _write(folder / "ro-crate-metadata.json", _consumer(upstream))

    class FakeJob:
        lines: list = []
        done = True
        ok = True
        crate_file = str(folder / "ro-crate-metadata.json")
        linked_crates = [str(tmp_path / "typo")]

    payload = _crate_payload(FakeJob())
    assert payload["crate"]["@graph"]                      # the run's crate survives
    assert "ok" not in payload                             # and the run still counts as fine
    assert "linking failed, crate left unlinked" in " ".join(FakeJob.lines)


# -- the form ------------------------------------------------------------------

def test_every_importer_that_describes_files_offers_the_option():
    plugins = {p["name"]: p for p in client.get("/api/plugins").json()}
    has = {n for n, p in plugins.items()
           if any(o["name"] == "linked_crates" for o in p["options"])}
    assert {"mlflow", "cromwell", "snakemake", "galaxy", "frictionless"} <= has
    assert "d4d" not in has                     # a datasheet names no files on disk
    for name in has:
        field = next(o for o in plugins[name]["options"] if o["name"] == "linked_crates")
        assert field["type"] == "dirs"          # the frontend renders a list of folders
        assert not plugins[name]["options"][0]["name"] == "linked_crates"   # never the first ask
