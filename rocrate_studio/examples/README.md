# Studio examples

What "Try it with our example first" uses. Each folder is copied into the studio's
output folder (`ROCRATE_STUDIO_OUT`, default `~/rocrate-studio-out`) before it is
used, so nothing is written inside the installed package. `@@SAMPLE_DIR@@` in a
file (or in `mlflow.db`) is replaced by the copy's folder at that point.

| folder | used by | what it is |
|---|---|---|
| `cromwell-variant-calling` | Cromwell / WDL run | a real Cromwell 92 run (bwa, samtools, bcftools over three samples): its `metadata.json`, the WDL, the reference and the reads — trimmed to the first 1000 reads per sample; the run's intermediate and output files are not included |
| `mlflow-iris` | MLflow experiment | an MLflow store (`mlflow.db` + `mlruns/`) with the iris-classifier experiment: two runs, a logged dataset and a model |
| `snakemake-records` | Snakemake run | the records file the FAIRSCAPE reporter wrote for a real variant-calling run |
| `galaxy-invocation` | Galaxy invocation | an unpacked Galaxy invocation export |
| `nextflow-letters` | A Nextflow pipeline (run it now) | three coreutils steps, ~3 s each; needs Nextflow, Java and the nf-fairscape plugin |
| `snakemake-letters` | A Snakemake workflow (run it now) | the same letters chain in plain shell; needs Snakemake and the FAIRSCAPE reporter |

The other importers' samples (D4D, WRROC, Frictionless, C2M2, CPM, REDCap) ship
inside fairscape-conversion and are copied the same way.
