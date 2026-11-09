# Scheduler container (ticket DEV-53): runs scripts/nightly_export.py every night, as set in infra/scheduler/crontab.
# A process of its OWN, apart from the API: nothing in this image starts or imports FastAPI.
# Build context: the repository root (see the `scheduler` service of docker-compose.yml).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=UTC
WORKDIR /app

# supercronic: a cron made for containers. It runs in the foreground and passes what the jobs print to the container's logs, which is what
# `docker logs` shows. The binary is checked against the sha256 that its release publishes before it is trusted.
ARG TARGETARCH
ARG SUPERCRONIC_VERSION=v0.2.51
ARG SUPERCRONIC_SHA256_AMD64=cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123
ARG SUPERCRONIC_SHA256_ARM64=4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && arch="${TARGETARCH:-amd64}" \
 && case "$arch" in amd64) sha="$SUPERCRONIC_SHA256_AMD64" ;; arm64) sha="$SUPERCRONIC_SHA256_ARM64" ;; *) echo "no supercronic for $arch" >&2; exit 1 ;; esac \
 && curl -fsSL -o /usr/local/bin/supercronic "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${arch}" \
 && echo "${sha}  /usr/local/bin/supercronic" | sha256sum -c - \
 && chmod +x /usr/local/bin/supercronic \
 && apt-get purge -y --auto-remove curl \
 && rm -rf /var/lib/apt/lists/*

# The dependencies of the API's requirements.txt (the same ones the pipeline needs), with the versions of constraints.txt. It installs the
# incidents_analyzer package by a relative path.
RUN pip install --no-cache-dir uv
COPY packages/shared/incidents_analyzer /app/packages/shared/incidents_analyzer
COPY packages/shared/incidents /app/packages/shared/incidents
COPY services/api/requirements.txt /app/services/api/requirements.txt
COPY infra/scheduler/constraints.txt /app/infra/scheduler/constraints.txt
# -c: versions that work together (see constraints.txt: without it the resolver picks a Prefect that breaks with the newest FastAPI).
RUN cd /app/services/api && uv pip install --system --no-cache -c /app/infra/scheduler/constraints.txt -r requirements.txt

# Only what the job needs: the API's config and the job_runner (no router, no app), the pipeline it launches, the script and the schedule.
# Never services/api/.env: the credentials come from the environment (env_file of docker-compose.yml), not from the image.
COPY services/api/core /app/services/api/core
COPY services/api/job_runner /app/services/api/job_runner
COPY data/__init__.py /app/data/__init__.py
COPY data/pipelines /app/data/pipelines
COPY data/process /app/data/process
COPY scripts/nightly_export.py /app/scripts/nightly_export.py
COPY infra/scheduler/crontab /app/infra/scheduler/crontab
RUN mkdir -p /app/data/raw /app/data/eval

CMD ["supercronic", "-passthrough-logs", "/app/infra/scheduler/crontab"]
