# COSMIC TRAIL backend (FastAPI + uvicorn). Used by docker-compose.yml for the
# "backend" service and for the one-time "data" download service.
# The data/ folder is NOT baked in: it lives in the cosmic-data volume (see DOCKER.md).
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Unprivileged user; /app/data is created here so the named volume inherits its owner.
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /app/data \
 && chown -R app:app /app
WORKDIR /app

# rasterio, pyproj and numba ship manylinux wheels (GDAL/PROJ/LLVM included), so no
# compilers are needed. rasterio's bundled GDAL still expects the system libexpat,
# which the slim image lacks (without it the HiRISE photo layer is unavailable).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app app/ app/
COPY --chown=app:app scripts/ scripts/
COPY --chown=app:app tests/ tests/
COPY --chown=app:app conftest.py pytest.ini ./

USER app
# Compile the numba route search now and keep numba's cache in the image, so the
# container starts quickly. (If the CPU differs from the build machine, numba simply
# recompiles at startup.)
RUN python -c "from app.routing import warmup; warmup()"
# Fail the build (rather than silently losing the photo layer) if rasterio can't load.
RUN python -c "import rasterio, pyproj; print('rasterio', rasterio.__version__, 'GDAL', rasterio.__gdal_version__)"

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
