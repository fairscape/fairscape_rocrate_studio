# RO-Crate Studio

A point-and-click, runs-on-your-laptop GUI for making RO-Crates with the
fairscape tools. No code, no terminal beyond starting it.

```bash
conda activate fairscape        # the env with fairscape_models + fairscape_conversion
pip install -e .                # once
rocrate-studio                  # opens http://127.0.0.1:8765 in your browser
```

`python -m rocrate_studio --port 9000 --no-browser` also works.
Open `http://127.0.0.1:8765/?demo=mlflow` to land with a sample already converted.

## What it does

The dropdown at the top of the left panel has two groups. **Import a run you
already have** is the main path: point at something that exists on disk and
click **Build crate**. **Run a workflow live** is the secondary path: the studio
runs the workflow itself, the log streams into the left panel while it runs
(the status bar above the map counts steps as they finish), a **Stop the run**
button aborts it, and the crate loads on the right the moment it is written.

| Choice | What you do | Which tool runs |
|---|---|---|
| **Import a run you already have** — MLflow, Cromwell, Snakemake report, D4D datasheet, Workflow-Run RO-Crate, C2M2 datapackage, CPM crate | Point at it, click **Build crate**. **Try sample** converts a real run that ships with `fairscape_conversion`. | `fairscape_conversion.plugins.<name>.convert("import", …)` |
| **Import** — An RO-Crate I already have / Nothing yet | Open any `ro-crate-metadata.json`, or make an empty crate and add entities by hand. **Export** turns the loaded crate into a D4D datasheet, WRROC, Croissant or CPM PROV. | `crate_ops` + `convert("export", …)` |
| **Run live** — A Nextflow pipeline | Point at a pipeline folder, fill in author/description/keywords, click **Run pipeline and build crate**. The run log streams in; the crate loads when it finishes. | `nextflow run . -c rocrate-studio.config -plugins nf-fairscape@0.1.0` |
| **Run live** — A Snakemake workflow | Point at a folder with a `Snakefile`, click **Run workflow and build crate**. It runs the workflow, then runs the FAIRSCAPE reporter over the finished DAG; both logs stream in and the crate loads at the end. Tick *Already ran it* (under Advanced) to skip straight to the report. | `snakemake --cores N --use-conda`, then `snakemake --reporter fairscape …` |

**Artifacts ▾** above the map lists everything found next to the saved crate —
datasheet, crate preview, provenance graph, evidence graph, the D4D/LinkML
YAML, Croissant, the workflow plugin's own score file — and opens any of them in
a new tab. Its last entry, **Build all artifacts…** (or **Rebuild all artifacts
& re-score…** once there is a build), runs
[fairscape_artifacts](https://github.com/fairscape/fairscape_artifacts)'
`fairscape-artifacts all` over the saved crate as a streamed job: the evidence
graph, a crate preview, the datasheet and the AI-readiness review (evidence +
review page from `AIreadiness-grader`) land beside the crate, then the studio
adds the grader's improvements form. The log streams into the left panel like a
workflow run; when it ends the datasheet opens and the status bar shows the
mechanical estimate per rubric domain, with the change from the previous build
("28 → 33 of 56"). A rebuild overwrites those pages, including a datasheet a
workflow plugin wrote. Online identifier/URL checks are off unless you tick
them in the confirm box. The estimate is only the rubric rules applied to the
evidence found; the review page is where a person or a model sets the real
scores. Needs `fairscape-artifacts` in the studio's environment
(`pip install -e ../fairscape_artifacts`, which the entry offers to run for you)
and, for the review, `AIreadiness-grader` (`pip install -e ../AIreadiness-grader`).

The drawer on the right has two views, toggled in its header. **All properties**
is the exhaustive catalogue of everything `fairscape_models` can describe for the
selected box, grouped. **Improve** is the to-do list: the grader's quick-wins
catalogue (single properties on the crate root or a Software box) ranked by the
last build's estimate — rows that lift a criterion still below 2 first, easy
before hard, sure points before judgement calls — in three groups, *Quick*, *A
sentence or two*, *In depth*, each row naming the criteria it lifts and their
current score. **Add** puts the field in the editor above and focuses it; ✓
marks what is already filled. A fourth group, **Bigger jobs**, lists what needs
new entities, links, checksums or statistics and names the Claude Code skill
that does it; the studio does not perform those. With no build yet the view says
so and offers to run one.

The middle panel is the crate as a provenance graph: boxes are entities,
arrows run input → computation → output. Click a box to edit its fields on
the right, add properties, link it to other entities, or delete it.
**+ Add entity** mints an ARK and a minimal Dataset/Software/Computation/
MLModel/Schema. **Validate** runs every entity through `fairscape_models`
(same models the server uses) and pins problems on the boxes. **Save crate…**
writes `ro-crate-metadata.json`.

## Layout

```
rocrate_studio/
  app.py              FastAPI routes (/api/convert, /api/validate, /api/save, /api/artifacts[/info|build|log|stop|install], /api/improve, /api/{nextflow,snakemake}/{run,log,stop}, …)
  plugins_meta.py     per-plugin form fields + how to call convert()   <- add a plugin here
  crate_ops.py        new crate / add entity / validate / read / write
  nextflow_runner.py  config overlay + subprocess + log streaming + stop
  snakemake_runner.py finds snakemake + the reporter, runs both passes, streams both, stop
  artifacts_runner.py fairscape-artifacts all as a streamed job, then the improvements form + estimate
  improve_meta.py     the Improve list: grader catalogue × latest estimate, plus the bigger jobs
  static/index.html   the whole frontend, no build step
```

Outputs default to `~/rocrate-studio-out/` (override with `ROCRATE_STUDIO_OUT`).

## Notes

* Java is not on PATH on this machine; the runner finds a JDK in a conda env
  and passes it as `NXF_JAVA_HOME`. Set `JAVA_HOME` to override.
* nf-fairscape only writes a crate on a *successful* run. A stopped run therefore never
  produces one; the log says so and the previous crate (if any) stays loaded.
* A live run streams over server-sent events (`/api/<runner>/log/<job>`), polled
  from the job's line buffer twice a second, so the browser sees every line the
  process prints without the runner having to know about the browser.
* Snakemake needs `snakemake-report-plugin-fairscape` installed **in the same
  environment as Snakemake itself** — Snakemake loads a report plugin inside
  its own interpreter, so a copy in the studio's environment does nothing.
  The studio looks for `snakemake` on PATH and then in every conda env,
  prefers one whose interpreter can already import the reporter, and puts that
  env's `bin/` first on PATH for the run so the workflow's own tools (bwa,
  samtools, …) resolve the way they would from an activated shell. When the
  reporter is missing it says which interpreter needs it and offers to run
  `pip install snakemake-report-plugin-fairscape[artifacts]` into it.
* The Snakemake sample and the Cromwell sample are real runs, from
  `fairscape_conversion/examples/{snakemake,wdl}-variant-calling`. A sample
  conversion never writes into the example folder — its crate lands in the
  output folder instead.
* Everything is local: the server binds 127.0.0.1 and the file browser is the
  local filesystem.
# fairscape_rocrate_studio
