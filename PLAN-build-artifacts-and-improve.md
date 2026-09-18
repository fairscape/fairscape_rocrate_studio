# Plan: "Build all artifacts" and an "Improve" panel for RO-Crate Studio

Status: **implemented 2026-09-15** (both parts). Written 2026-09-14 after the
Artifacts dropdown and the `/api/aiready` grading route landed. What shipped:
`artifacts_runner.py` (build + install jobs), `improve_meta.py` (the ranked
list), routes `/api/artifacts/{info,build,log,stop,install}` and `/api/improve`,
the dropdown entry, the drawer toggle (*All fields* | *Improve*), README.
`/api/aiready` is gone. Decisions on the open questions at the bottom: online
checks off by default with a checkbox in the confirm box; the datasheet opens
after a build; one Improve list for the whole crate (software properties
collapse into one row per property with a line per Software box). Not done:
persisting dismissed rows in localStorage (was optional).

## Where things stand

* `rocrate_studio/static/index.html` — the toolbar above the map has one
  **Artifacts ▾** `<select>` (`artifactLinks()`, `gradeCrate()`). It lists files
  found next to the saved crate and ends with **Grade AI-readiness…**, which
  calls `POST /api/aiready`.
* `rocrate_studio/app.py` — `ARTIFACT_FILES` (patterns the dropdown looks for),
  `GET /api/artifacts?path=`, `POST /api/aiready`. The grading route imports
  `aireadiness_evidence` / `aireadiness_improve` directly and writes
  `ai-ready-review/ai-ready-review.html`, `ai-ready-review/ai-ready-presentation.json`
  and `ai-ready-improve.html` beside the crate, then returns a mechanical
  estimate per rubric domain that the status bar shows.
* The right-hand drawer's **AI-Ready details** block (`#aireadyGroups`, rendered
  around line 600 of `index.html` from `GET /api/fields` = `fields_meta.ALL`)
  lists *every* specialised property fairscape_models knows, grouped. It is a
  catalogue, not advice.
* `touched()` sets `S.cratePath = null` on any edit, so "saved on disk" is the
  only state in which artifacts and grading make sense. Keep that rule.

Two things are wanted next:

1. **Part A** — the dropdown should offer to run
   [fairscape_artifacts](https://github.com/fairscape/fairscape_artifacts)'
   `all` build (datasheet + preview + evidence graph + AI-Ready review) instead
   of only the grader. Offer it always: "Build all artifacts…" when there is no
   build yet, "Rebuild all artifacts & re-score…" when there is one.
2. **Part B** — an **Improve** view on the right that turns the grade into a
   curated to-do list ordered easy → hard, the way the grader's improvements
   form does, rather than the full property catalogue.

---

## Part A — Build all with fairscape_artifacts

### Facts to build on

* Repo is cloned at `/home/oj/fairscape/fairscape_artifacts` (package
  `fairscape_artifacts`, console script `fairscape-artifacts`). It is **not**
  installed in the `fairscape` conda env yet (`import fairscape_artifacts`
  fails there). Install with `pip install -e /home/oj/fairscape/fairscape_artifacts`
  in that env. Its only hard dependency is jinja2. The `[review]` extra names
  the distribution `fairscape-wizard>=0.3.0`; check `pip show fairscape-wizard`
  in the env — the grader's packages are already importable there
  (`aireadiness_evidence`, `aireadiness_improve`, `aireadiness_grader`), so the
  extra may be satisfied already or may need the pin relaxed. Verify before
  relying on it.
* `fairscape-artifacts all <crate>` (`cli.py: cmd_all`) writes, beside the crate
  unless `-d` says otherwise:

  | file | what |
  |---|---|
  | `ro-crate-evidence-graph.html` + `.json` | interactive provenance graph |
  | `ro-crate-preview.html` (one per constituent for release crates) | every entity tabulated |
  | `ro-crate-datasheet.html` | datasheet, rendered once before the review and again after so it carries the review |
  | `ai-ready-presentation.json`, `ai-ready-review.html` | the grader's evidence and review page, **at the crate root**, not in `ai-ready-review/` |

  Options that matter: `--network` (URL / registry lookups, off by default,
  slow when on), `--no-review`, `--condense-threshold`, `--link-base`,
  `-q`. If the grader is missing it prints a warning and skips the review
  (`grading.GraderUnavailable`) rather than failing.
* It does **not** write `ai-ready-improve.html`; the studio's current route
  does (via `aireadiness_improve.cli.render_improve`). Keep producing it after
  the build so the improvements form stays in the dropdown.
* It overwrites `ro-crate-datasheet.html` that nf-fairscape / the Snakemake
  reporter may have written. That is the intent of a rebuild; say so in the
  confirm text.

### Changes

1. **Backend: one build route, streamed.** Replace `POST /api/aiready` with
   `POST /api/artifacts/build {path, network=false}` that runs
   `fairscape-artifacts all <crate>` as a subprocess and streams its output
   through the existing job / server-sent-events pattern
   (`_job_stream`, same shape as `/api/snakemake/log/{id}`). Reasons for a
   subprocess over importing `cmd_all`: the review step can take a minute with
   `--network`, the user should watch it like a workflow run, and a crash in
   the renderer must not take the studio down. Use the studio's own
   interpreter (`sys.executable -m fairscape_artifacts …`) so the install
   check is simply "does it import here". After the process exits 0:
   * render `ai-ready-improve.html` (what `/api/aiready` does today);
   * read `ai-ready-presentation.json` and compute the same per-domain
     estimate summary `/api/aiready` returns now (sum of integer
     `criterion.estimate.score`, max = 2 × criteria); put it in the final
     SSE payload alongside `done/ok`.
   Add a small `GET /api/artifacts/info` → `{installed: bool, version,
   grader: bool, install_command}` so the dropdown can say what is missing and
   offer the pip install the way the Snakemake reporter install works
   (`start_install` in `snakemake_runner.py` is the template).
2. **`ARTIFACT_FILES`**: add `ro-crate-evidence-graph.html`, and accept the
   review/presentation at the crate root as well as in `ai-ready-review/`
   (patterns are lists already). Drop the `ai-ready-review/` layout once the
   build route replaces `/api/aiready`, or keep both patterns — cheap.
3. **Dropdown wording** (`artifactLinks()`): the action entry is always
   present. Label = `Build all artifacts…` when none of datasheet / graph /
   review exist, else `Rebuild all artifacts & re-score…`. When
   `fairscape_artifacts` is not importable: `Build all artifacts (install
   fairscape-artifacts first)…` and choosing it triggers the install job. Keep
   the "save first" alert when `S.cratePath` is null.
4. **Follow-along**: reuse `streamJob()` with the run log in the left panel
   and status-bar lines (`progressOf()` can learn the build's step names:
   "evidence graph", "datasheet", "review", "previews"). On `done`, refresh the
   dropdown, open the datasheet (or the review — pick one, the datasheet now
   embeds the review at a glance), and show the estimate in the status bar
   exactly as `gradeCrate()` does today, plus the delta from the previous
   presentation JSON if one existed ("28 → 33 of 56").
5. **README**: replace the Artifacts paragraph's "Grade AI-readiness…" with the
   build entry and the install line for fairscape_artifacts.

### Verify

* Install in the env, `fairscape-artifacts all` on the scratch Snakemake crate
  and on `examples/letters-chain-slow/results` by hand first; note timing with
  and without `--network`.
* Through the UI: open a crate → dropdown shows *Build all…* → run → files
  appear → dropdown now says *Rebuild… & re-score* → run again → status shows
  the estimate and the delta. The headless-Chrome driver approach used on
  2026-09-14 (Chrome `--headless=new --remote-debugging-port --remote-allow-origins=*`,
  `Runtime.evaluate` over the DevTools websocket with `websocket-client`) works
  well for this; `node` lives at `~/anaconda3/envs/fairscape/bin/node` for
  `node --check` on the extracted `<script>`.
* Confirm nothing else in the studio still calls `/api/aiready`.

---

## Part B — "Improve" panel on the right

### What the grader already provides

* `aireadiness_improve/fields.py::catalogue()` — the quick-wins catalogue: each
  entry is a property on the crate **root** or on a **Software** entity with
  `label`, `help`, `type`, the `criteria` ids it feeds (first one is where it
  counts most), `win` (true = a cheap, sure point), and `effort`
  1 / 2 / 3 mapped by `EFFORT_LABELS` to *Quick* / *A sentence or two* /
  *In depth*. `OUT_OF_SCOPE_NOTES` lists the improvements that need new
  entities or links (ORCIDs, ontology terms, checksums, summary statistics,
  ethics questionnaire, portability) and are deliberately not in the form.
* `ai-ready-presentation.json` — per criterion: `estimate.score` ('0'/'1'/'2'
  or absent) and `estimate.basis` (the plain-language reasons), plus the
  evidence items. This says *which* criteria are short and why.
* Skills in `/home/oj/fairscape/AIreadiness-grader/.claude/skills/`:
  `post-grade-improve` (the orchestration), and the six leaves
  `compute-summary-stats`, `ethics-questionnaire`, `hash-coverage`,
  `link-authors-orcids`, `link-subjects-ontologies`, `portability-interview`.
  Read `post-grade-improve` first: it is the existing definition of "easy to
  hard" and of what each bigger job needs.
* Scope rule already decided for the improvements form (2026-09-03, see memory
  `fairscape-improve-tool`): v0.1 sets single properties on entities that
  already exist. No new entities, no new links, from the inline UI. The
  bigger jobs are listed and pointed at, not performed.

### Changes

1. **Backend `GET /api/improve?path=`** — merge the two sources into one list:
   for every catalogue entry, look up the value on the crate (root, or each
   Software entity), and the estimate of each criterion it feeds from the
   latest `ai-ready-presentation.json`. Emit
   `{effort, effort_label, target: {"@id", kind}, property, label, help, type,
   criteria: [{id, name, score, max: 2}], win, have: bool, current}` and sort:
   items that lift a criterion currently below 2 first, then by `effort`, then
   `win`, then by number of criteria lifted. Append the out-of-scope jobs as a
   trailing `bigger_jobs` list (`{title, why, skill, criteria}`) built from
   `OUT_OF_SCOPE_NOTES` + which of their criteria are short. If no presentation
   exists, return `{needs_grade: true}` and the catalogue unranked.
2. **Frontend: a second view in the drawer.** Add a two-way toggle to the
   drawer header (`#editor .head`): **All properties** (today's
   `#aireadyGroups`) | **Improve**. Improve renders three sections in order —
   Quick / A sentence or two / In depth — each row: the property label, a
   one-line "lifts 0.a, 5.a (now 1/2)" note, ✓ when already filled, and the
   same **Add** button the catalogue rows use, which selects the target entity
   (root or that Software node), adds the field to the editor and focuses it.
   A fourth section **Bigger jobs** lists the out-of-scope items with the
   skill name to run in Claude Code and no button. When `needs_grade`, show one
   line: "Build the artifacts to get a grade first" with a button that runs the
   Part A action.
3. **Loop closure**: after Save the status bar should suggest
   *Rebuild & re-score* (dropdown) and the Improve list should refresh on the
   next grade. Persist which rows the user dismissed in `localStorage` keyed
   by crate path — optional.
4. **Root-first**: the Improve view is about the crate, not the selected box,
   so open it from the crate badge / *Edit crate details* too, not only after
   clicking a node. When a Software node is selected, the same view filtered
   to that entity is a reasonable v2; not needed first.
5. **Keep `fields_meta` untouched** — All properties stays the exhaustive view.
   Improve is a ranking over the grader's catalogue, so the ranking logic
   lives with the grader's data (`aireadiness_improve`), and the studio only
   merges it with the estimate. If the merge turns out to be generally useful,
   move it into `aireadiness_improve` as a function and call that.

### Verify

* Grade the scratch Snakemake crate (estimate was 15/56 on 2026-09-14, weak on
  Characterization and Ethics), open Improve, confirm Quick rows come first
  and each names criteria that are actually short in the presentation JSON.
* Fill two Quick rows, Save, Rebuild & re-score, confirm the estimate rises and
  the rows show ✓.
* A crate with no grade shows the "grade first" line and nothing misleading.

---

## Order of work

1. Install `fairscape_artifacts` in the env; run `all` by hand on two crates.
2. Part A backend (build job + info route), then dropdown wording, then
   README. Remove `/api/aiready`.
3. Part B backend `/api/improve`, then the drawer toggle and rendering.
4. Headless-Chrome pass over both, screenshot the toolbar (it wrapped once
   before; `.toolbar button{white-space:nowrap}` and the 128px select width
   fixed it).

## Open questions for the user

* Should a rebuild run the review with `--network` (slower, better evidence
  for identifier / repository checks)? Suggest: off by default, checkbox in
  the confirm.
* Where should the built pages open — datasheet or review — after a build?
* Is one Improve list for the whole crate enough for v1, or is a per-Software
  view wanted straight away?
