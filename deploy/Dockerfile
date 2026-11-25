# syntax=docker/dockerfile:1
#
# The Schnaps site in one image: the built client, pyspiel from the schnaps
# branch of the OpenSpiel fork, the bots' models and the server. It serves
# plain HTTP on 8000; HTTPS comes from a proxy in front (deploy/Caddyfile).
# The all-cards watch app (8001) is off.
#
# The build context is the folder that holds both schnaps-web/ and
# open_spiel/ (Docker/), so the image gets the local OpenSpiel tree as it is,
# uncommitted changes included. Only the files deploy/Dockerfile.dockerignore
# lets through are sent. From schnaps-web/, in PowerShell:
#
#   docker build -f deploy/Dockerfile -t schnaps-web ..
#
# Run it locally (data in a Docker volume, not in data/db):
#
#   docker run --rm -p 8000:8000 -v schnaps-data:/data schnaps-web

ARG PYTHON=3.14

# --- 1. the client (client/dist) ----------------------------------------------
FROM node:22-trixie-slim AS client
WORKDIR /src
COPY schnaps-web/client/package.json schnaps-web/client/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY schnaps-web/client/ ./
RUN npm run build

# --- 2. pyspiel.so -------------------------------------------------------------
FROM python:${PYTHON}-slim-trixie AS pyspiel
# Parallel compile jobs: each takes about 1 GB of RAM.
ARG JOBS=2
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake ninja-build \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/open_spiel
# The C++ dependencies (abseil-cpp, json, pybind11_abseil, pybind11_json, the
# bridge solver) are already in the local tree, fetched by install.sh, and
# pybind11 sits next to it, so nothing is downloaded here.
COPY open_spiel/pybind11 pybind11
COPY open_spiel/open_spiel open_spiel
RUN cmake -S open_spiel -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DPython3_EXECUTABLE="$(command -v python)" \
      -DOPEN_SPIEL_ENABLE_JAX=OFF -DOPEN_SPIEL_ENABLE_PYTORCH=OFF \
 && ninja -C build -j "${JOBS}" python/pyspiel.so

# --- 3. the site -----------------------------------------------------------------
FROM python:${PYTHON}-slim-trixie
RUN useradd --create-home --uid 1000 schnaps \
 && mkdir -p /data/db && chown -R schnaps:schnaps /data
COPY schnaps-web/deploy/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# The OpenSpiel Python package (the scale framework, the JAX schnaps game)
# and the engine.
COPY open_spiel/open_spiel/__init__.py /opt/open_spiel/open_spiel/__init__.py
COPY open_spiel/open_spiel/python /opt/open_spiel/open_spiel/python
COPY --from=pyspiel /opt/open_spiel/build/python/pyspiel.so /opt/open_spiel/build/python/pyspiel.so

# config.py finds models/ and client/dist next to server/.
COPY schnaps-web/server/schnaps_web /app/server/schnaps_web
COPY schnaps-web/models /app/models
COPY --from=client /src/dist /app/client/dist

# The site's settings (server/schnaps_web/config.py), as decided in
# docs/hosting-options.md section 8: the watch app off, at most 8 tables,
# at most 10 logins or registrations per address and minute.
ENV PYTHONPATH=/app/server:/opt/open_spiel:/opt/open_spiel/build/python \
    PYTHONUNBUFFERED=1 \
    JAX_PLATFORMS=cpu \
    SCHNAPS_WEB_HOST=0.0.0.0 \
    SCHNAPS_WEB_PORT=8000 \
    SCHNAPS_WEB_WATCH_PORT=0 \
    SCHNAPS_WEB_MAX_TABLES=8 \
    SCHNAPS_WEB_LOGIN_RATE=10 \
    SCHNAPS_WEB_DB_DIR=/data/db

USER schnaps
WORKDIR /app/server
VOLUME /data
EXPOSE 8000
# The players load and compile for about a minute and a half before the
# site answers.
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/site', timeout=4)"]
CMD ["python", "-m", "schnaps_web.app"]
