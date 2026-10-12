# FAIRSCAPE Studio as a shared demo: the studio, the fairscape packages,
# Nextflow + nf-fairscape and Snakemake + the FAIRSCAPE reporter. No conda, so
# the live Cell Maps pipeline is off; its finished package is still there.
#
# Build with deploy/build-image.sh, which stages the sibling repos into src/.
# Sign-in is on by default in this image; pass the password at run time:
#
#   docker run -p 8765:8765 -e ROCRATE_STUDIO_PASSWORD=... fairscape-studio
#
# Everything visitors make lives in /work; mount nothing there to have it go
# away with the container.

FROM eclipse-temurin:21-jre AS jre

FROM python:3.12-slim

ARG NXF_VER=26.04.6
ENV JAVA_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:$PATH \
    NXF_VER=${NXF_VER} \
    NXF_ANSI_LOG=false \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY --from=jre /opt/java/openjdk /opt/java/openjdk

# procps: Nextflow reads task metrics with ps
RUN apt-get update \
 && apt-get install -y --no-install-recommends procps \
 && rm -rf /var/lib/apt/lists/*

# the -dist launcher carries the framework jar, so nothing downloads at run time
ADD --chmod=755 https://github.com/nextflow-io/nextflow/releases/download/v${NXF_VER}/nextflow-${NXF_VER}-dist /usr/local/bin/nextflow

COPY src /src
# the grader without its own deps: the studio only needs the offline rubric
# (aireadiness_evidence / aireadiness_improve), not the pydantic-ai grading
# client and its three provider SDKs. pulp ships CBC builds for every
# platform; only linux x86_64 stays.
RUN pip install /src/fairscape_models /src/fairscape_conversion /src/fairscape_artifacts \
        snakemake /src/snakemake-report-plugin-fairscape /src/rocrate_studio \
 && pip install --no-deps /src/AIreadiness-grader \
 && rm -rf /src \
 && SD=$(python -c 'import pulp,os;print(os.path.join(os.path.dirname(pulp.__file__),"solverdir","cbc"))') \
 && find "$SD" -mindepth 1 -maxdepth 1 ! -name linux -exec rm -rf {} + \
 && find "$SD/linux" -mindepth 1 -maxdepth 1 ! -name i64 -exec rm -rf {} +

RUN useradd --create-home --uid 1000 studio && mkdir /work && chown studio /work
USER studio
WORKDIR /home/studio

RUN nextflow -v
COPY --chown=studio plugins/nf-fairscape-0.2.0 /home/studio/.nextflow/plugins/nf-fairscape-0.2.0

ENV ROCRATE_STUDIO_OUT=/work \
    ROCRATE_STUDIO_MULTI_USER=1

EXPOSE 8765
# one process: running jobs live in memory
CMD ["uvicorn", "rocrate_studio.app:app", "--host", "0.0.0.0", "--port", "8765"]
