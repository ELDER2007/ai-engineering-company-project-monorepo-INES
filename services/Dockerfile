# FastAPI service (services/api). Build context: ./services; packages/shared comes in as the named
# context "shared" (see docker-compose.yml) because requirements.txt installs the incidents_analyzer
# package from ../../packages/shared by relative path; ./data comes in as the named context "data".
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/services/api

RUN pip install --no-cache-dir uv

COPY --from=shared incidents_analyzer /app/packages/shared/incidents_analyzer
COPY --from=shared incidents /app/packages/shared/incidents

# The reporting module of the API imports the `data` package (data/pipelines and data/process), which lives at the root of the repository, outside
# ./services: it comes in as the named context "data" (see docker-compose.yml). Only those two folders: never data/raw or data/eval, which hold
# runtime output (telemetry exports, reports) that must not be baked into an image. The API adds /app to its path (reporting/__init__.py).
COPY --from=data __init__.py /app/data/__init__.py
COPY --from=data pipelines /app/data/pipelines
COPY --from=data process /app/data/process
COPY api/requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY api .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
