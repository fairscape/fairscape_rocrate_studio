# Installing RO-Crate Studio

The studio is a window onto the other fairscape repos — it draws the crate and
calls them to do the work. Installing it means installing them too, into one
environment, and starting the studio from that same environment. Everything
runs on your machine; nothing is uploaded.

You need Python 3.10+, git, and a few minutes.

## Install

```bash
mkdir -p ~/fairscape && cd ~/fairscape
git clone https://github.com/fairscape/fairscape_models
git clone https://github.com/fairscape/fairscape_conversion
git clone https://github.com/fairscape/fairscape_artifacts
git clone https://github.com/fairscape/AIreadiness-grader
git clone https://github.com/fairscape/fairscape_rocrate_studio rocrate_studio

conda create -n fairscape python=3.11 -y && conda activate fairscape
# or: python3 -m venv ~/.venvs/fairscape && source ~/.venvs/fairscape/bin/activate

pip install -e fairscape_models -e fairscape_conversion \
            -e fairscape_artifacts -e AIreadiness-grader -e rocrate_studio
```

Install from the checkouts, editable (`-e`), so a `git pull` in any of them
updates what the studio runs with no reinstall. The last two are optional; they
power the Artifacts and Improve panels.

## Run

```bash
cd ~                      # anywhere except ~/fairscape — see below
rocrate-studio --check    # ends with "ready: rocrate-studio will start"
rocrate-studio            # opens http://127.0.0.1:8765
```

`--check` prints the interpreter it found, each required package, each optional
panel, and the exact command to install anything missing. The studio refuses to
start when a required package is missing rather than failing on your first
click; `ROCRATE_STUDIO_SKIP_CHECKS=1` starts it anyway.

`--port 9000` moves it, `--no-browser` leaves your browser alone, and
`python -m rocrate_studio` is the same thing as the `rocrate-studio` command.
Saved crates go to `~/rocrate-studio-out/`, or wherever `ROCRATE_STUDIO_OUT`
points.

## The optional panels

Each one disables exactly one thing.

* **Build all artifacts** needs `fairscape-artifacts` in the studio's
  environment. The menu entry offers to install it for you.
* **The AI-readiness review and Improve list** also need `AIreadiness-grader`.
  Without it you still get the datasheet, preview and evidence graph.
* **Run live → Nextflow** needs `nextflow` on your PATH, the `nf-fairscape`
  plugin installed for it (`make install` in that checkout), and a JDK. If
  `java` is not on your PATH the studio looks in your conda environments;
  `JAVA_HOME` overrides it.
* **Run live → Snakemake** needs the reporter **in Snakemake's own
  environment**, not the studio's — Snakemake loads report plugins inside its
  own interpreter, so a copy elsewhere does nothing. The studio finds Snakemake
  on your PATH or in any conda env and offers to install the reporter into the
  right one. By hand:

  ```bash
  conda create -n snakemake-fairscape -c conda-forge -c bioconda snakemake -y
  conda activate snakemake-fairscape
  pip install "snakemake-report-plugin-fairscape[artifacts]"
  conda activate fairscape
  ```

## If it does not start

**"a directory named fairscape_models/ in this folder shadows the installed
package"** — you started it from `~/fairscape`, and Python imported the folder
next to you instead of the package. `cd ~` and run it again. This is the most
common way a correct install still fails.

**A package you know you installed is reported missing** — you are running a
different interpreter than you installed into. `--check` prints it on the first
line; compare with `which python`. Activate the environment, or use
`python -m rocrate_studio`.

**Address already in use** — something holds port 8765, often an older copy.
Use `--port 8766`.

**A sample conversion fails** — the samples read real runs that ship inside the
`fairscape_conversion` checkout. Install that one editable from the clone, not
from PyPI.
