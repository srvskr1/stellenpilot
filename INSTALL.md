# Install guide

This guide takes you from nothing to your first real job search in about 15 minutes. Pick **one** way to install:

| way | best for | you need |
|---|---|---|
| [A. Python](#a-install-with-python) | most people, uses the least disk space | Python 3.11 or newer |
| [B. Docker](#b-install-with-docker) | if you already use Docker, or Python gives you trouble | Docker Desktop (Windows, Mac) or Docker Engine (Linux) |

After installing, continue with [First day setup](#first-day-setup). It is the same for both ways.

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

### Step 2: Get the project

With git:
```bash
git clone https://github.com/srvskr1/job-hunt-pipeline.git
```
Without git: on the GitHub page click **Code**, then **Download ZIP**, and unzip it in your user folder. The unzipped folder is called `job-hunt-pipeline-master`; rename it to `job-hunt-pipeline` so the commands below match.

### Step 3: Install it

**Windows (PowerShell)**
```powershell
cd $HOME\job-hunt-pipeline
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
cd ~/job-hunt-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Check that it worked:
```bash
jobhunt --help
```

> **Every time you open a new terminal**, activate first: `.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` on macOS and Linux (from inside the `job-hunt-pipeline` folder). You will see `(.venv)` at the start of the line when it is active.

### Step 4: Make your workspace

Keep your own files (CV, keys, database, generated documents) in a separate folder, outside the project:

**Windows**
```powershell
mkdir $HOME\my-hunt
cd $HOME\my-hunt
jobhunt init
```

**macOS and Linux**
```bash
mkdir ~/my-hunt && cd ~/my-hunt
jobhunt init
```

`jobhunt init` creates three files: `config.toml` (what to search), `profile.toml` (your CV facts) and `.env` (your API keys). Continue with [First day setup](#first-day-setup).

### Optional: PDF export

Without LibreOffice you get Word files (DOCX). With it you also get PDFs. Install it from https://www.libreoffice.org/download/ (Linux: `sudo apt install libreoffice-writer`). Nothing else to configure.

---

## B. Install with Docker

1. Install **Docker Desktop** from https://www.docker.com/products/docker-desktop/ (Windows, macOS) or Docker Engine on Linux, and start it.
2. Get the project (see [Step 2](#step-2-get-the-project) above), then in a terminal:
   ```bash
   cd job-hunt-pipeline
   mkdir data
   docker compose pull || docker compose build
   docker compose run --rm jobhunt init
   ```
3. Your files are now in the `data` folder inside `job-hunt-pipeline`. The container can only see this folder, so put your CV file there too before importing it: `docker compose run --rm jobhunt import your_cv.pdf`.

In the rest of this guide, wherever it says `jobhunt something`, type `docker compose run --rm jobhunt something` instead, and start the dashboard with `docker compose up -d`. More details: [docs/docker.md](docs/docker.md).

---

## First day setup

Everything from here happens in your browser. In your workspace folder (`my-hunt`, or the project folder for Docker), start the dashboard:

```bash
jobhunt serve
```
Open http://127.0.0.1:8765 . Leave the terminal open while you use it; **Ctrl+C** stops it.

### 1. My CV (5 minutes)

The **My CV** panel opens by itself the first time.
1. Drop your CV file (PDF, DOCX or TXT) on the box, or click it to choose the file.
2. The form fills in. Without an AI model only your name, contact details and languages are filled; your CV text is shown above the form so you can copy the rest in.
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
| Free, on your computer | Ollama, model `qwen2.5:7b` | install Ollama from https://ollama.com and run `ollama pull qwen2.5:7b` once |
| Claude | Claude, paste your Anthropic API key | nothing else |
| OpenAI | OpenAI, a model name, your API key | nothing else |

Which local model fits your computer: [docs/local-llm.md](docs/local-llm.md).

Click **Save settings**.

### 3. Run your first search

Click **Run search now**. The little office shows what it is doing. When it is done, good matches have a tailored CV and cover letter in the `output` folder. Read every document before you send it.

Something not working? In the terminal (Ctrl+C first), `jobhunt doctor` tells you in plain words what is missing.

### Want to look around first?

`jobhunt demo` loads fictional sample jobs. Delete `jobhunt.db` afterwards to remove them.

---

## Optional extras

| want | how | guide |
|---|---|---|
| More job sources | free keys for Adzuna and TheirStack, in `.env` | [docs/sources.md](docs/sources.md) |
| Watch your dream companies | `jobhunt watch <careers page link>`, then add the entry to `[watch] companies` | [README](README.md) |
| Add a job you found yourself | `jobhunt add <link>` or the **Add a job** button on the dashboard | [README](README.md) |
| A daily message with your top matches | Telegram or email | [docs/digest.md](docs/digest.md) |
| Status updates from your inbox | read only Gmail sync | [docs/gmail.md](docs/gmail.md) |
| Run every morning by itself | Task Scheduler, cron or launchd | [docs/scheduling.md](docs/scheduling.md) |

---

## Updating

```bash
cd job-hunt-pipeline
git pull
pip install -e .        # with the virtual environment active
```
Docker: `git pull`, then `docker compose pull || docker compose build`. Your workspace files are never touched by an update.

## Uninstalling

Delete the `job-hunt-pipeline` folder. Your workspace (`my-hunt`, or `data` for Docker) holds your CV, keys and documents; delete it too if you want everything gone. Nothing else is installed on your system apart from Python (or Docker) and, optionally, LibreOffice and Ollama.

---

## Troubleshooting

| problem | fix |
|---|---|
| `python` or `jobhunt` is "not recognized" or "command not found" | Windows: reinstall Python with "Add python.exe to PATH" ticked. Everywhere: activate the virtual environment first (see Step 3). |
| "running scripts is disabled" in PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, once. |
| `error: externally-managed-environment` on Linux | You are outside the virtual environment. Run `source .venv/bin/activate` first. |
| `No module named venv` on Linux | `sudo apt install python3-venv` |
| The dashboard does not open | `jobhunt serve` must keep running in its terminal. Use http://127.0.0.1:8765 , not https. |
| Port 8765 is already in use | `jobhunt serve --port 8800`, then open http://127.0.0.1:8800 |
| No PDFs, only DOCX | Install LibreOffice; `jobhunt doctor` shows whether it is found. |
| `jobhunt import` says the PDF has almost no text | Your PDF is a scanned image. Export your CV from Word or Google Docs as DOCX and import that. |
| "could not reach the AI model" | Start Ollama or your model server, then check with `jobhunt doctor`. |
| Docker: permission errors in `data` on Linux | `sudo chown -R 1000 data` |
| Something else | Run the command again with `-v` for more detail, for example `jobhunt -v run`, and open an issue with the output. Leave out your keys and personal data. |
