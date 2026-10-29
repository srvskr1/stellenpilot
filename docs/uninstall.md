# Uninstall completely

Do these steps in order. Steps 1 and 2 matter most: they stop the daily search before the program is gone.

**1. Stop the dashboard.** Press **Ctrl+C** in the terminal where `stellenpilot serve` runs (Docker: `docker compose down`).

**2. Remove the automatic daily search**, if you switched it on. Easiest: in the dashboard open **Settings**, switch off **Search every day** under Automatic search and press **Save changes**. If the dashboard is already gone:

* Windows (PowerShell): `schtasks /Delete /TN "Stellenpilot daily search" /F`
* macOS and Linux: run `crontab -e` and delete the line that ends with `# jobhunt-daily`

**3. Remove the program.**

* Windows app: Windows Settings, Apps, Stellenpilot, Uninstall. It also removes the daily search task. Your files in `Documents\Stellenpilot` stay; delete that folder too if you want everything gone.
* Installed with Homebrew: `brew uninstall stellenpilot`, then `brew untap srvskr1/stellenpilot`. Your workspace folder (for example `~/Stellenpilot`) stays until you delete it.
* Installed with pip: activate the environment you installed it in, then `pip uninstall stellenpilot`. Delete that environment folder too if you made one just for it (for example `stellenpilot-env` or `.venv`).
* Installed from source: delete the `stellenpilot` folder you cloned or unzipped (the environment `.venv` is inside it).
* Docker: in the project folder run `docker compose down`, then `docker rmi ghcr.io/srvskr1/stellenpilot` (and `docker image prune` to free the space of any self built image).

**4. Delete your data.** Your workspace folder (`my-hunt`, or `data` for Docker) holds everything personal: your CV profile, `.env` with your API keys, the job database, the generated CVs and cover letters, `run.log`, backups and the Gmail `token.json`. Delete the whole folder. The only other place is the Built-in AI folder `.stellenpilot` in your home folder, if you downloaded it (see step 5).

**5. Close your accounts and keys** (optional, but good practice):

* API keys you created for it: delete them at Adzuna, TheirStack, Anthropic or OpenAI.
* Gmail sync: remove access at https://myaccount.google.com/permissions and delete the Google Cloud project you made for it.
* Telegram digest: send `/deletebot` to @BotFather.
* Built-in AI: press **Remove the AI files** in Settings, or delete the folder `.stellenpilot` in your home folder (`C:\Users\<you>\.stellenpilot` on Windows). It holds the engine and the model, about 1.5 to 4 GB.
* Ollama model: `ollama rm qwen3.5:4b` (or the model you pulled), and uninstall Ollama or LM Studio if you only used them for this.

LibreOffice and Python stay installed; remove them like any other app if you no longer need them.


[Back to the README](https://github.com/srvskr1/stellenpilot#readme)
