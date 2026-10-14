# Install guide

This guide takes you from nothing to your first real job search in about 15 minutes. Pick **one** way to install:

| way | best for | you need |
|---|---|---|
| [W. Windows app](#w-windows-app-easiest) | **Windows, the easiest way** | nothing, Python is included |
| [A. Python](#a-install-with-python) | macOS and Linux, or if you like the terminal | Python 3.11 or newer |
| [B. Docker](#b-install-with-docker) | if you already use Docker, or Python gives you trouble | Docker Desktop (Windows, Mac) or Docker Engine (Linux) |

After installing, continue with [First day setup](#first-day-setup). It is the same for every way.

---

## W. Windows app (easiest)

1. Open [the latest release](https://github.com/srvskr1/stellenpilot/releases/latest) and download **Stellenpilot-Setup-X.Y.Z.exe** (about 26 MB).
2. Run it. Windows may show **"Windows protected your PC"**, because the app is not code signed yet (signing costs money every year). Click **More info**, then **Run anyway**. The code is open, and the installer is built by GitHub from this repository (see `.github/workflows/windows.yml`).
3. Click through: it installs for your user only, no administrator rights needed. Leave **Put a Stellenpilot icon on the desktop** ticked.
4. Stellenpilot starts and opens in your browser. A small window says it is running; keep it open while you use Stellenpilot.

From then on: double click **Stellenpilot** on the desktop or in the Start menu. Your files live in **Documents\Stellenpilot**.

**Update:** download and run the newest installer. Your files are kept. **Uninstall:** Windows Settings, Apps, Stellenpilot, Uninstall. This also removes the daily search task. Your files in Documents\Stellenpilot stay until you delete them.

Prefer a version without installing? The release also has **Stellenpilot-Portable-X.Y.Z.zip**: unzip it anywhere and double click `Stellenpilot.exe`.

---

## A. Install with Python

### Step 1: Install Python (once)

**Windows**
1. Download Python 3.12 or newer from https://www.python.org/downloads/
2. In the installer, tick **"Add python.exe to PATH"** at the bottom, then click **Install Now**.
3. Open **PowerShell** (Start menu, type "PowerShell") and check:
   ```powershell
   python --version
   ```
   It should show 3.11 or higher.

**macOS**
1. Download Python 3.12 or newer from https://www.python.org/downloads/ and run the installer. The Python that comes with macOS is too old.
2. Open **Terminal** and check: `python3 --version`

**Linux (Ubuntu, Debian)**
```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git
python3 --version
```
Ubuntu 24.04 and Debian 13 ship 3.12 or newer. On older versions, install a newer Python first.

### Step 2: Install Stellenpilot

**The quick way** (Windows, macOS, Linux):
```bash
python -m venv stellenpilot-env
# Windows: stellenpilot-env\Scripts\Activate.ps1    macOS or Linux: source stellenpilot-env/bin/activate
pip install stellenpilot
```
Then skip to [Step 4](#step-4-make-your-workspace). Each time you open a new terminal, activate `stellenpilot-env` again. Update later with `pip install -U stellenpilot`.

**From the source code** instead (if you want to change it), follow the rest of Step 2 and Step 3.

#### Get the project

With git:
```bash
git clone https://github.com/srvskr1/stellenpilot.git
```
Without git: on the GitHub page click **Code**, then **Download ZIP**, and unzip it in your user folder. The unzipped folder is called `stellenpilot-main`; rename it to `stellenpilot` so the commands below match.

### Step 3: Install it

**Windows (PowerShell)**
```powershell
cd $HOME\stellenpilot
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```
If PowerShell says "running scripts is disabled on this system", run this once, then try `Activate.ps1` again:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**macOS and Linux (Terminal)**
```bash
cd ~/stellenpilot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Check that it worked:
```bash
stellenpilot --help
```

> **Every time you open a new terminal**, activate first: `.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` on macOS and Linux (from inside the `stellenpilot` folder). You will see `(.venv)` at the start of the line when it is active.

### Step 4: Make your workspace

Keep your own files (CV, keys, database, generated documents) in a separate folder, outside the project:

**Windows**
```powershell
mkdir $HOME\my-hunt
cd $HOME\my-hunt
stellenpilot init
```

**macOS and Linux**
```bash
mkdir ~/my-hunt
cd ~/my-hunt
stellenpilot init
```

`stellenpilot init` creates three files: `config.toml` (what to search), `profile.toml` (your CV facts) and `.env` (your API keys). Continue with [First day setup](#first-day-setup).

### Optional: PDF export

Without LibreOffice you get Word files (DOCX). With it you also get PDFs. Install it from https://www.libreoffice.org/download/ (Linux: `sudo apt install libreoffice-writer`). Nothing else to configure.

---

## B. Install with Docker

1. Install **Docker Desktop** from https://www.docker.com/products/docker-desktop/ (Windows, macOS) or Docker Engine on Linux, and start it.
2. Get the project (see [Step 2](#step-2-get-the-project) above), then in a terminal:
   ```bash
   cd stellenpilot
   mkdir data
   docker compose pull || docker compose build
   docker compose run --rm stellenpilot init
   ```
3. Your files are now in the `data` folder inside `stellenpilot`. The container can only see this folder, so put your CV file there too before importing it: `docker compose run --rm stellenpilot import your_cv.pdf`.

In the rest of this guide, wherever it says `stellenpilot something`, type `docker compose run --rm stellenpilot something` instead, and start the dashboard with `docker compose up -d`. More details: [docs/docker.md](docs/docker.md).

---

## First day setup

Everything from here happens in your browser. In your workspace folder (`my-hunt`, or the project folder for Docker), start the dashboard:

```bash
stellenpilot serve
```
Your browser opens http://127.0.0.1:8765 by itself (if not, type that address). Leave the terminal open while you use it; **Ctrl+C** stops it.

**From the second time on you don't need the terminal.** In the last setup step, leave **Put a Stellenpilot icon on my desktop** ticked (or later: **Settings, Desktop icon**). Then just double click **Stellenpilot** on your desktop. A small window opens (keep it open while you use Stellenpilot) and your browser shows the dashboard. Double clicking again while it runs simply shows the open dashboard.

A short setup opens by itself the first time: your CV, what jobs you want, who writes your documents, and the daily search, with a check at the end. You can run it again from the left menu or from **Settings**. Below is the longer version in writing, including the optional job sources.

### 1. My CV (5 minutes)

The **My CV** panel opens by itself the first time.
1. Drop your CV file (PDF, DOCX or TXT) on the box, or click it to choose the file.
2. The form fills in. A CV with clear headings (Experience, Projects, Education, Skills) is sorted in about a second, even without an AI model. If the headings are unclear and no AI is on, only your contact details and skills are filled; your CV text is shown above the form so you can copy the rest in.
3. Check every field. Add jobs, projects and degrees with the **+ Add** buttons. Keep bullets short and true: they are copied word for word into your tailored CVs.
4. Put skills you are still learning in a group called `Learning`. They are never presented as experience.
5. Click **Save my CV**.

Your languages matter: your German level decides which ads get skipped and whether letters are written in German (only at B2 or better).

### 2. Settings (3 minutes)

Click **Settings** in the left menu:
* **What you are looking for**: job titles (one per line), city, distance, remote.
* **Job sources**: the Bundesagentur and Arbeitnow need no key. For Adzuna and TheirStack, tick the box and paste your free key ([where to get them](docs/sources.md)).
* **AI model**: optional but recommended. Without one, jobs are scored by keywords and letters come from a template.

| choice | pick | then |
|---|---|---|
| Free, on your computer | Ollama, model `qwen3.5:4b` | install Ollama from https://ollama.com and run `ollama pull qwen3.5:4b` once |
| Claude | Claude, paste your Anthropic API key | nothing else |
| OpenAI | OpenAI, a model name, your API key | nothing else |

Which local model fits your computer: [docs/local-llm.md](docs/local-llm.md).

Click **Save settings**.

### 3. Run your first search

On **Home**, click **Search now**. The agent office shows what it is doing. When it is done, good matches have a tailored CV and cover letter in the `output` folder. Read every document before you send it.

To search every morning by itself, open **Settings**, switch on **Automatic search** and pick a time. Your computer must be on; the dashboard does not need to be open.

Something not working? In the terminal (Ctrl+C first), `stellenpilot doctor` tells you in plain words what is missing.

### Want to look around first?

`stellenpilot demo` loads fictional sample jobs. Delete `jobhunt.db` afterwards to remove them.

---

## Optional extras

| want | how | guide |
|---|---|---|
| More job sources | free keys for Adzuna and TheirStack, in `.env` | [docs/sources.md](docs/sources.md) |
| Watch your dream companies | `stellenpilot watch <careers page link>`, then add the entry to `[watch] companies` | [README](README.md) |
| Add a job you found yourself | `stellenpilot add <link>` or the **Add a job** button on the dashboard | [README](README.md) |
| A daily message with your top matches | Telegram or email | [docs/digest.md](docs/digest.md) |
| Status updates from your inbox | read only Gmail sync | [docs/gmail.md](docs/gmail.md) |
| Run every morning by itself | Task Scheduler, cron or launchd | [docs/scheduling.md](docs/scheduling.md) |

---

## Updating

```bash
cd stellenpilot
git pull
pip install -e .        # with the virtual environment active
```
Docker: `git pull`, then `docker compose pull || docker compose build`. Your workspace files are never touched by an update.

## Uninstalling

Turn off **Automatic search** in Settings first, then remove the program and delete your workspace folder (`my-hunt`, or `data` for Docker). Full step by step list, including API keys and Gmail access: [Uninstall completely](https://github.com/srvskr1/stellenpilot#uninstall-completely) in the README.

---

## Troubleshooting

| problem | fix |
|---|---|
| `python` or `stellenpilot` is "not recognized" or "command not found" | Start it with `python -m stellenpilot serve` (works without PATH changes). Windows: reinstall Python with "Add python.exe to PATH" ticked, or activate the virtual environment first (see Step 3). |
| "running scripts is disabled" in PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, once. |
| `error: externally-managed-environment` on Linux | You are outside the virtual environment. Run `source .venv/bin/activate` first. |
| `No module named venv` on Linux | `sudo apt install python3-venv` |
| The dashboard does not open | The small Stellenpilot window (or `stellenpilot serve` in its terminal) must keep running. Use http://127.0.0.1:8765 , not https. |
| Port 8765 is already in use | `stellenpilot serve --port 8800`, then open http://127.0.0.1:8800 |
| No PDFs, only DOCX | Install LibreOffice; `stellenpilot doctor` shows whether it is found. |
| `stellenpilot import` says the PDF has almost no text | Your PDF is a scanned image. Export your CV from Word or Google Docs as DOCX and import that. |
| "could not reach the AI model" | Start Ollama or your model server, then check with `stellenpilot doctor`. |
| Docker: permission errors in `data` on Linux | `sudo chown -R 1000 data` |
| Something else | Run the command again with `-v` for more detail, for example `stellenpilot -v run`, and open an issue with the output. Leave out your keys and personal data. |
