# COSMIC TRAIL: setup for beginners (Windows)

This guide is for you if you've never run a Python or JavaScript project before. It takes about
20 minutes, most of it waiting for downloads. If you're comfortable with a terminal, the short
version in the [README](README.md#quick-start-windows) is enough. If something goes wrong,
[LOCAL_SETUP.md](LOCAL_SETUP.md) has a troubleshooting section.

COSMIC TRAIL has two parts that run at the same time on your computer:

- the **backend**, a Python server that holds the terrain, plans routes and runs ARIA
  (http://127.0.0.1:8000);
- the **frontend**, the web page with the 3D globe that you actually open
  (http://127.0.0.1:5173).

## 1. Install the tools

| Tool | Where to get it | Notes |
|------|-----------------|-------|
| Python 3.11–3.14 | https://www.python.org/downloads/ | In the installer, tick **"Add python.exe to PATH"** |
| Node.js 22 or newer (LTS) | https://nodejs.org/ | The default options are fine |
| Git | https://git-scm.com/downloads | The default options are fine |

Open a new **PowerShell** window (Start menu → type "PowerShell") and check all three:

```powershell
python --version
node --version
git --version
```

Each one should print a version number. If one says "not recognized", reinstall it, then close
PowerShell and open a new window.

## 2. Get the code

```powershell
cd $HOME\Documents
git clone https://github.com/IB-Mustafa/Cosmic_Trail_A_Mars_Map.git
cd Cosmic_Trail_A_Mars_Map
```

## 3. Set up Python

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The first line creates a private Python folder (`.venv`) just for this project. The second one
switches it on, and your prompt should now start with `(.venv)`. The third installs the packages,
which takes a few minutes.

> If PowerShell says running scripts is disabled, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer **Y**, and try again.

## 4. Download the data

```powershell
python scripts/download_data.py
```

This fetches about 236 MB of terrain and map data from our
[Hugging Face dataset](https://huggingface.co/datasets/irhabatool/cosmic-trail-data) into the
`data` folder, and checks the terrain grid against its recorded checksum.

## 5. Set up the frontend

```powershell
cd frontend
npm install
Set-Content -Path .env.local -Value "VITE_API_BASE=http://127.0.0.1:8000" -Encoding ascii
cd ..
```

The last line creates a small file that tells the web page where the backend is. Without it, some
Windows computers can't reach the backend, and the globe loads but nothing else works.

## 6. Start the app

You need **two** PowerShell windows.

**Window 1, the backend.** In the project folder:

```powershell
.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Wait until it says `Uvicorn running on http://127.0.0.1:8000`.

**Window 2, the frontend.** In the project folder:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

Now open **http://127.0.0.1:5173** in Chrome or Edge.

## 7. Plan your first route

1. Click **Find Route**. Two routes appear: the solid pink one is terrain-safe, and the dashed red
   one is the shortest. The first route can take a few seconds.
2. Look at the elevation profile under the map, and the comparison in the left panel.
3. Click **ARIA** (bottom-right) and ask "Am I safe here?".

To stop the app, press `Ctrl + C` in both windows. To start it again later, repeat step 6.

## Common problems

| Problem | Fix |
|---------|-----|
| `python` or `npm` is "not recognized" | Reinstall it (tick "Add to PATH" for Python), then open a new PowerShell window |
| `ModuleNotFoundError` when starting the backend | The venv isn't active: run `.venv\Scripts\Activate.ps1` first |
| The globe shows, but no terrain, routes or ARIA | Check the backend window is still running, and that `frontend\.env.local` exists |
| "Address already in use" | The app is already running in another window, so close it first |
| Routes take minutes | `numba` didn't install: run `pip install -r requirements.txt` again, then restart the backend |

## Run the tests (optional)

```powershell
python -m pytest
```

You should see 197 tests. One of them is a speed test for very long routes, and it can fail on
slower laptops even though the routes are correct.
