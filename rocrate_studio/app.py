"""FastAPI app behind RO-Crate Studio. Run with ``python -m rocrate_studio``."""
from __future__ import annotations

import asyncio
import copy
import importlib
import json
import os
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import (artifacts_runner, crate_ops, fields_meta, improve_meta, nextflow_runner,
               snakemake_runner)
from .plugins_meta import PLUGINS, public_list

STATIC = Path(__file__).parent / "static"
OUT_DIR = Path(os.environ.get("ROCRATE_STUDIO_OUT", Path.home() / "rocrate-studio-out"))

app = FastAPI(title="RO-Crate Studio")


def _fail(e: Exception, prefix: str = ""):
    msg = f"{prefix}{type(e).__name__}: {e}"
    raise HTTPException(400, detail=msg)


# ------------------------------------------------------------------ static / info

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/info")
def info():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return {"home": str(Path.home()), "suggest_dir": str(OUT_DIR / "my-crate"), "out_dir": str(OUT_DIR)}


@app.get("/api/fs")
def fs(path: str = "~"):
    p = Path(path).expanduser()
    if p.is_file():
        p = p.parent
    if not p.is_dir():
        raise HTTPException(404, f"not a folder: {p}")
    entries = []
    for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
        if child.name.startswith("."):
            continue
        entries.append({"name": child.name, "dir": child.is_dir()})
    return {"path": str(p), "entries": entries[:500]}


# what the "Artifacts" dropdown above the map lists: files the converters, the
# workflow plugins, fairscape_artifacts and the AI-readiness grader leave next
# to a crate. The review/presentation may sit at the crate root (fairscape-
# artifacts) or under ai-ready-review/ (the studio's former grading route).
ARTIFACT_FILES = [
    ("datasheet", "Datasheet", ["ro-crate-datasheet.html"]),
    ("preview", "Crate preview", ["ro-crate-preview.html"]),
    ("graph", "Provenance graph", ["provenance-graph.html", "ro-crate-prov-graph.html"]),
    ("evidence_graph", "Evidence graph", ["ro-crate-evidence-graph.html", "*-evidence-graph.html"]),
    ("review", "AI-readiness review", ["ai-ready-review.html", "ai-ready-review/ai-ready-review.html"]),
    ("improve", "AI-readiness improvements form", ["ai-ready-improve.html"]),
    ("plugin_score", "Plugin AI-ready score (JSON)", ["ai_ready_score.json"]),
    ("linkml", "D4D / LinkML datasheet (YAML)", ["ro-crate-linkml.yaml"]),
    ("croissant", "Croissant (JSON)", ["croissant.json"]),
]
BUILT_KEYS = ("datasheet", "evidence_graph", "review")   # what "Build all" produces


@app.get("/api/artifacts")
def artifacts(path: str):
    d = Path(path).expanduser()
    items = []
    for key, label, patterns in ARTIFACT_FILES:
        for pat in patterns:
            hit = next((f for f in sorted(d.glob(pat)) if f.is_file()), None)
            if hit:
                items.append({"key": key, "label": label, "path": str(hit), "name": hit.name})
                break
    return {"items": items, "built": any(i["key"] in BUILT_KEYS for i in items),
            "estimate": artifacts_runner.read_estimate(d)}


@app.get("/api/artifacts/info")
def artifacts_info():
    """Is fairscape-artifacts importable here, and the grader with it?"""
    return artifacts_runner.info()


class BuildReq(BaseModel):
    path: str
    network: bool = False


@app.post("/api/artifacts/build")
def artifacts_build(req: BuildReq):
    """Run ``fairscape-artifacts all`` over the saved crate as a streamed job:
    evidence graph, previews, datasheet, AI-readiness review, then the
    improvements form. Follow it on /api/artifacts/log/{job}."""
    try:
        job = artifacts_runner.start(req.path, req.network)
    except Exception as e:  # noqa: BLE001
        _fail(e)
    return {"job": job.id}


@app.post("/api/artifacts/install")
def artifacts_install():
    """pip install fairscape-artifacts into the studio's own interpreter."""
    try:
        job = artifacts_runner.start_install()
    except Exception as e:  # noqa: BLE001
        _fail(e)
    return {"job": job.id}


@app.post("/api/artifacts/stop/{job_id}")
def artifacts_stop(job_id: str):
    return _stop(artifacts_runner.JOBS, job_id)


@app.get("/api/artifacts/log/{job_id}")
async def artifacts_log(job_id: str):
    job = artifacts_runner.JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return StreamingResponse(_job_stream(job, final=lambda j: j.payload()),
                             media_type="text/event-stream")


@app.get("/api/improve")
def improve(path: str):
    """The grader's quick-wins catalogue ranked by the crate's latest estimate,
    plus the bigger jobs the inline editor does not do."""
    d = Path(path).expanduser()
    if d.is_file():
        d = d.parent
    if not (d / "ro-crate-metadata.json").is_file():
        raise HTTPException(400, f"no ro-crate-metadata.json in {d} — save the crate first")
    try:
        return improve_meta.improve(d)
    except ImportError as e:
        raise HTTPException(400, "the AI-readiness grader is not installed in the studio's "
                                 f"environment ({e}); pip install -e AIreadiness-grader there")
    except Exception as e:  # noqa: BLE001
        _fail(e)


@app.get("/api/file")
def file_(path: str):
    p = Path(path).expanduser()
    if not p.is_file() or p.suffix not in (".html", ".json", ".yaml", ".yml", ".txt", ".csv"):
        raise HTTPException(404, "not a servable file")
    return FileResponse(p)


@app.get("/api/fields")
def fields():
    """Specialised properties per entity kind, grouped, straight from fairscape_models."""
    return fields_meta.ALL


@app.get("/api/plugins")
def plugins():
    return public_list()


# ------------------------------------------------------------------ convert

class ConvertReq(BaseModel):
    plugin: str
    options: dict[str, Any] = {}
    sample: bool = False


def _mlflow_uri(source: str) -> str:
    """Folder with mlflow.db / mlruns, a .db file, an mlruns dir, or a URI -> tracking URI."""
    if "://" in source:
        return source
    p = Path(source).expanduser()
    if p.is_file() and p.suffix in (".db", ".sqlite", ".sqlite3"):
        return f"sqlite:///{p.resolve()}"
    if p.is_dir():
        if (p / "mlflow.db").is_file():
            return f"sqlite:///{(p / 'mlflow.db').resolve()}"
        if (p / "mlruns").is_dir():
            return str((p / "mlruns").resolve())
        if p.name == "mlruns" or any(c.is_dir() and (c / "meta.yaml").exists() for c in p.iterdir()):
            return str(p.resolve())
        raise FileNotFoundError(f"{p} has no mlflow.db and no mlruns folder")
    raise FileNotFoundError(f"{source} is not a file, folder or tracking URI")


def _mlflow_experiments(uri: str) -> list[dict]:
    import mlflow
    client = mlflow.MlflowClient(tracking_uri=uri)
    out = []
    for e in client.search_experiments():
        if e.name == "Default" and e.experiment_id == "0":
            continue
        runs = client.search_runs([e.experiment_id], max_results=1000)
        out.append({"name": e.name, "id": e.experiment_id, "runs": len(runs)})
    return out


@app.get("/api/lookup/mlflow_experiments")
def lookup_mlflow(source: str):
    try:
        uri = _mlflow_uri(source)
        return {"uri": uri, "choices": [f"{e['name']}" for e in _mlflow_experiments(uri)],
                "detail": [f"{e['name']} ({e['runs']} runs)" for e in _mlflow_experiments(uri)]}
    except Exception as e:  # noqa: BLE001
        _fail(e)


def _read_doc(path: str):
    p = Path(path).expanduser()
    text = p.read_text()
    if p.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


@app.post("/api/convert")
def convert(req: ConvertReq):
    meta = PLUGINS.get(req.plugin)
    if not meta or not meta["import"]:
        raise HTTPException(400, f"{req.plugin} cannot import")
    mod = importlib.import_module(f"fairscape_conversion.plugins.{req.plugin}")
    opts = {k: v for k, v in req.options.items() if v not in ("", None)}
    log = []
    crate_path = None
    try:
        if req.sample:
            s = meta["sample"]
            if "records" in s or "document" in s:
                source = _read_doc(str(s.get("records") or s.get("document")))
                opts = {k: v for k, v in opts.items() if k in ("validate", "naan")}
                log.append(f"sample input: {s.get('records') or s.get('document')}")
            else:
                sample_opts = {k: (str(v) if isinstance(v, Path) else v) for k, v in s.items()}
                source = sample_opts.pop("source")
                opts = {**opts, **sample_opts}
                log.append(f"sample input: {source}")
        else:
            if "source" not in opts:
                raise ValueError("pick a source first")
            source = opts.pop("source")
            if meta["source_kind"] == "document":
                source = _read_doc(source)

        # plugin-specific plumbing
        if req.plugin == "c2m2":
            if req.sample:
                work = Path(tempfile.mkdtemp(prefix="c2m2-", dir=OUT_DIR))
                shutil.copytree(source, work / "input-datapackage")
                source = str(work / "input-datapackage")
            out = opts.pop("output_path", None) or str(Path(source).parent / "c2m2-crate")
            old = os.getcwd(); os.chdir(Path(source).parent)
            try:
                crate = mod.convert("import", Path(source).name, output_path=out, **opts)
            finally:
                os.chdir(old)
            crate_path = str(Path(out).resolve())
            log.append(f"plugin wrote {crate_path}/ro-crate-metadata.json")
        elif req.plugin in ("mlflow", "cromwell"):
            if req.plugin == "mlflow" and isinstance(source, str):
                source = _mlflow_uri(source)
                log.append(f"tracking store: {source}")
                if not opts.get("experiment") and not opts.get("run_id"):
                    exps = _mlflow_experiments(source)
                    if len(exps) == 1:
                        opts["experiment"] = exps[0]["name"]
                        log.append(f"only one experiment, using '{exps[0]['name']}'")
                    elif not exps:
                        raise ValueError("this store has no experiments")
                    else:
                        raise ValueError("this store has several experiments; pick one: "
                                         + ", ".join(e["name"] for e in exps))
            if isinstance(source, str) and not opts.get("crate_dir"):
                opts["crate_dir"] = str(OUT_DIR / f"{req.plugin}-crate")
            crate = mod.convert("import", source, **opts)
            if isinstance(source, str):
                # a sample is read-only: its crate_dir anchors the relative
                # contentUrls (so it has to be the example's own folder), but
                # the crate itself lands in the studio's output folder rather
                # than overwriting the one checked in beside the example
                cd = (OUT_DIR / f"{req.plugin}-sample-crate" if req.sample
                      else Path(opts["crate_dir"]))
                cd.mkdir(parents=True, exist_ok=True)
                crate_ops.write_crate(crate, cd); crate_path = str(cd.resolve())
                log.append(f"wrote {crate_path}/ro-crate-metadata.json")
                if req.sample:
                    log.append(f"(file paths in it point at {opts['crate_dir']})")
        else:
            crate = mod.convert("import", source, **opts)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        _fail(e, f"{req.plugin} import failed — ")
    crate = json.loads(json.dumps(crate, default=str))
    log.append(f"{len(crate['@graph'])} entities")
    return {"crate": crate, "crate_path": crate_path, "log": "\n".join(log)}


# ------------------------------------------------------------------ crate ops

class CrateReq(BaseModel):
    crate: dict


class NewReq(BaseModel):
    name: str = ""
    author: str = ""
    description: str = ""


class EntityReq(CrateReq):
    type: str
    name: str


class SaveReq(CrateReq):
    path: str


class OpenReq(BaseModel):
    path: str


class ExportReq(CrateReq):
    plugin: str


@app.post("/api/new")
def new(req: NewReq):
    return {"crate": crate_ops.new_crate(req.name, req.author, req.description)}


@app.post("/api/open")
def open_(req: OpenReq):
    try:
        crate, folder = crate_ops.read_crate(req.path)
    except Exception as e:  # noqa: BLE001
        _fail(e)
    return {"crate": crate, "crate_path": str(folder)}


@app.post("/api/entity/new")
def entity_new(req: EntityReq):
    crate = copy.deepcopy(req.crate)
    try:
        gid = crate_ops.add_entity(crate, req.type.strip(), req.name)
    except Exception as e:  # noqa: BLE001
        _fail(e)
    return {"crate": crate, "id": gid}


@app.post("/api/validate")
def validate(req: CrateReq):
    try:
        return crate_ops.validate(req.crate)
    except Exception as e:  # noqa: BLE001
        _fail(e)


@app.post("/api/save")
def save(req: SaveReq):
    try:
        written = crate_ops.write_crate(req.crate, req.path)
    except Exception as e:  # noqa: BLE001
        _fail(e)
    return {"path": str(Path(req.path).expanduser().resolve()), "written": written}


@app.post("/api/export")
def export(req: ExportReq):
    meta = PLUGINS.get(req.plugin)
    if not meta or not meta["export"]:
        raise HTTPException(400, f"{req.plugin} cannot export")
    mod = importlib.import_module(f"fairscape_conversion.plugins.{req.plugin}")
    try:
        result = mod.convert("export", copy.deepcopy(req.crate))
    except Exception as e:  # noqa: BLE001
        _fail(e, f"{req.plugin} export failed — ")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ext = meta.get("export_ext", ".json")
    target = OUT_DIR / f"{req.plugin}-export{ext}"
    if isinstance(result, str):
        text = result
    elif ext == ".yaml":
        text = yaml.dump(json.loads(json.dumps(result, default=str)), sort_keys=False, allow_unicode=True)
    else:
        text = json.dumps(result, indent=2, default=str)
    target.write_text(text)
    return {"path": str(target), "preview": text[:4000]}


# ------------------------------------------------------------------ nextflow

@app.get("/api/nextflow/info")
def nf_info():
    return nextflow_runner.info()


@app.post("/api/nextflow/config")
def nf_config(form: dict):
    try:
        p = nextflow_runner.write_config(form)
    except Exception as e:  # noqa: BLE001
        _fail(e)
    return {"path": str(p), "config": p.read_text()}


@app.post("/api/nextflow/run")
def nf_run(form: dict):
    try:
        job = nextflow_runner.start(form)
    except Exception as e:  # noqa: BLE001
        _fail(e)
    return {"job": job.id}


@app.get("/api/snakemake/info")
def smk_info():
    return snakemake_runner.info()


@app.post("/api/snakemake/plan")
def smk_plan(form: dict):
    try:
        return snakemake_runner.plan(form)
    except Exception as e:  # noqa: BLE001
        _fail(e)


@app.post("/api/snakemake/run")
def smk_run(form: dict):
    try:
        job = snakemake_runner.start(form)
    except Exception as e:  # noqa: BLE001
        _fail(e)
    return {"job": job.id}


@app.post("/api/snakemake/install")
def smk_install():
    """Install the reporter into the environment Snakemake itself runs in."""
    try:
        job = snakemake_runner.start_install()
    except Exception as e:  # noqa: BLE001
        _fail(e)
    return {"job": job.id}


def _stop(jobs, job_id):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    if job.done:
        return {"stopped": False, "done": True}
    job.stop()
    return {"stopped": True, "done": False}


@app.post("/api/nextflow/stop/{job_id}")
def nf_stop(job_id: str):
    return _stop(nextflow_runner.JOBS, job_id)


@app.post("/api/snakemake/stop/{job_id}")
def smk_stop(job_id: str):
    return _stop(snakemake_runner.JOBS, job_id)


@app.get("/api/snakemake/log/{job_id}")
async def smk_log(job_id: str):
    job = snakemake_runner.JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return StreamingResponse(_job_stream(job), media_type="text/event-stream")


@app.get("/api/nextflow/log/{job_id}")
async def nf_log(job_id: str):
    job = nextflow_runner.JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")

    return StreamingResponse(_job_stream(job), media_type="text/event-stream")


def _crate_payload(job) -> dict:
    """What a workflow run adds to its final event: the crate it produced."""
    payload = {}
    if job.ok and Path(job.crate_file).exists():
        try:
            crate, folder = crate_ops.read_crate(job.crate_file)
            payload.update(crate=crate, crate_path=str(folder))
        except Exception as e:  # noqa: BLE001
            payload.update(ok=False, error=f"the run wrote {job.crate_file} but it "
                                            f"could not be read: {type(e).__name__}: {e}")
    elif getattr(job, "stopped", False):
        payload["error"] = "the run was stopped before it produced a crate"
    return payload


async def _job_stream(job, final=_crate_payload):
    """Server-sent events for a running job: every log line, then the verdict
    plus whatever ``final(job)`` adds (the crate for a workflow run, the
    estimate for an artifacts build)."""
    sent = 0
    while True:
        while sent < len(job.lines):
            yield f"data: {json.dumps({'line': job.lines[sent]})}\n\n"
            sent += 1
        if job.done:
            payload = {"done": True, "ok": job.ok}
            payload.update(final(job))
            yield f"data: {json.dumps(payload)}\n\n"
            return
        await asyncio.sleep(0.5)
