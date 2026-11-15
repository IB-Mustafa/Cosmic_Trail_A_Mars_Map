# Running COSMIC TRAIL with Docker

The easiest way to run the app: Docker builds and starts everything, so you **don't need to
install Python or Node.js**, create a virtual environment or download the data by hand.
It works the same on Windows, macOS and Linux.

(Want to edit the code with live reload instead? Use the manual setup in
[LOCAL_SETUP.md](LOCAL_SETUP.md).)

```
 browser ──► http://localhost:8080 ──► frontend container (nginx: built app)
                                          │  /api/*, /docs
                                          ▼
                                       backend container (FastAPI) ──► cosmic-data volume
                                          ▲                              (~236 MB from Hugging Face)
                                       data container (one-time download, then exits)
```

---

## 1. Install Docker

- **Windows / macOS:** install **Docker Desktop** from https://www.docker.com/products/docker-desktop/
  and **start it** (wait until it says *Engine running*). On Windows it may ask to enable WSL 2;
  accept and restart if asked.
- **Linux:** install Docker Engine and the Compose plugin: https://docs.docker.com/engine/install/

✅ **Check** in a terminal:
```bash
docker --version
docker compose version
```
Both should print a version (Compose **v2.20 or newer**). If you get "cannot connect to the Docker
daemon", Docker Desktop isn't running yet.

**Disk space:** about **4 GB** free during the first build: images ~1 GB (backend ~930 MB,
frontend ~95 MB), data volume ~236 MB, and ~2.4 GB of build cache that you can free afterwards
with `docker builder prune`.

## 2. Get the code

```bash
git clone https://github.com/IB-Mustafa/Cosmic_Trail_A_Mars_Map.git
cd Cosmic_Trail_A_Mars_Map
```

## 3. Start

```bash
docker compose up --build
```

The **first** run takes a few minutes. It:
1. builds the backend image (Python packages; the route search is compiled ahead of time),
2. builds the frontend image (`npm ci` + production build),
3. runs the **data** container once, which downloads the ~236 MB the app needs from the Hugging Face
   dataset [irhabatool/cosmic-trail-data](https://huggingface.co/datasets/irhabatool/cosmic-trail-data)
   into a Docker volume and checks its checksums,
4. starts the backend, waits until it is healthy, then starts the frontend.

You're ready when the log shows the frontend started (and `backend-1 | ... Application startup complete`).

👉 Open **http://localhost:8080**

Later starts skip the download and take only seconds. To run in the background instead of
keeping the terminal busy, add `-d`: `docker compose up -d` (see logs with `docker compose logs -f`).

## 4. Check that it works

- The globe opens on Gale Crater, and the dataset badge starts with **`DTEEC_018854_1755…`**
  (the real HiRISE data), not *(synthetic)*.
- **Layers → 📷 HiRISE photo** shows the photo mosaic.
- Pick A and B in the *Route planner* → **Find Route**: two routes in about a second.
- API: http://localhost:8080/api/health · interactive docs: http://localhost:8080/docs
- `docker compose ps` shows `backend` and `frontend` as **running (healthy)**;
  `data` has exited (code 0), which is expected.

## 5. Everyday commands

| Task | Command |
|------|---------|
| Start (foreground) | `docker compose up` |
| Start in the background | `docker compose up -d` |
| Follow the logs | `docker compose logs -f` (one service: `docker compose logs -f backend`) |
| Status | `docker compose ps` |
| Stop | **Ctrl + C** (foreground), or `docker compose down` |
| After `git pull` (new code) | `docker compose up --build` |
| Run the backend tests | `docker compose run --rm backend python -m pytest tests -q` |
| Re-download / update the data | `docker compose run --rm data python scripts/download_data.py` |
| Open a shell in the backend | `docker compose exec backend bash` |
| Use another port than 8080 | `COSMIC_PORT=9000 docker compose up` (PowerShell: `$env:COSMIC_PORT=9000; docker compose up`) |
| Remove containers **and** the data volume | `docker compose down -v` (next start downloads the data again; saved route plans are lost) |

`docker compose down` keeps the **cosmic-data** volume (data + saved route plans in `plans.db`);
only `down -v` deletes it.

## 6. Troubleshooting

| Problem | Fix |
|---------|-----|
| `docker: command not found` / "cannot connect to the Docker daemon" | Install and **start** Docker Desktop (step 1) |
| `Bind for 127.0.0.1:8080 failed: port is already allocated` | Something else uses 8080; use another port: `COSMIC_PORT=9000 docker compose up` |
| `data-1 exited with code 1` / download errors | Network or proxy problem. Run `docker compose up` again: it resumes. Behind a proxy, configure it in Docker Desktop → Settings → Resources → Proxies. Rate-limited: set `HF_TOKEN` (a free Hugging Face token) before starting |
| `dependency failed to start: container ... backend is unhealthy` | `docker compose logs backend` shows the error; usually the data is incomplete: `docker compose run --rm data python scripts/download_data.py`, then `docker compose up` |
| Page loads but shows "Backend not reachable" | `docker compose ps`: is backend healthy? `docker compose logs backend` |
| Dataset shows *(synthetic)* | The real data is missing in the volume; re-run the data download (row above) and `docker compose restart backend` |
| Old version still shown after `git pull` | Rebuild: `docker compose up --build`; hard-refresh the browser (Ctrl + Shift + R) |
| Plain globe without the coloured Mars surface | No internet: the basemap streams from NASA Mars Trek; the HiRISE layers still work |
| Apple Silicon (M1/M2/M3) | Should work: all base images and Python wheels exist for arm64, so the images build natively (only tested on x86-64 so far) |

## 7. How it is put together (for developers)

| File | Role |
|------|------|
| `docker-compose.yml` | the three services, the `cosmic-data` volume, port 8080 |
| `Dockerfile` | backend image: Python 3.12, `requirements.txt`, `app/`, `scripts/`, `tests/`; runs as a non-root user; numba compiled at build time |
| `frontend/Dockerfile` | builds the frontend with Node 22, serves `dist/` with nginx |
| `frontend/nginx.conf` | static files + forwards `/api/`, `/docs`, `/openapi.json` to `backend:8000` |
| `.dockerignore`, `frontend/.dockerignore` | keep `data/`, `node_modules/`, `.venv/` and `frontend/.env.local` out of the images |

- The frontend is built with an empty `VITE_API_BASE`, so the browser calls `/api/...` on the same
  address and nginx forwards it. To point the image at another backend, build with
  `docker compose build --build-arg VITE_API_BASE=https://your-backend frontend`.
- The backend is **not** published on a host port; everything goes through the frontend on 8080.
  For direct access, add `ports: ["127.0.0.1:8000:8000"]` under `backend` in `docker-compose.yml`.
- The data lives only in the `cosmic-data` volume; the images contain no data, so they stay small
  and rebuilding never re-downloads it.
