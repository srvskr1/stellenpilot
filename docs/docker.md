# Run with Docker

No Python install needed. Works the same on Windows, macOS and Linux with Docker Desktop or Docker Engine.

## Start

```bash
git clone https://github.com/srvskr1/job-hunt-pipeline.git
cd job-hunt-pipeline
mkdir data                                 # your files go here (create it yourself so you own it)
docker compose build                       # first time only, takes a few minutes
docker compose run --rm jobhunt init       # creates data/config.toml, data/profile.toml, data/.env
docker compose run --rm jobhunt demo       # optional: fictional sample jobs
docker compose up -d                       # dashboard at http://127.0.0.1:8765
```

Your files live in the `data` folder next to `docker-compose.yml`: config, profile, `.env` with your keys, the database and the generated documents in `data/output`. Edit them with any editor on your computer.

## Everyday commands

| what | command |
|---|---|
| check your setup | `docker compose run --rm jobhunt doctor` |
| search, score and tailor | `docker compose run --rm jobhunt run` |
| stop the dashboard | `docker compose down` |
| update after `git pull` | `docker compose build && docker compose up -d` |

## Smaller image without PDF export

LibreOffice makes the image about 920 MB. Without it, it is about 400 MB and you get DOCX files only:

```bash
docker compose build --build-arg WITH_PDF=false
```

## Daily run

Schedule `docker compose run --rm jobhunt run` on your computer, for example with cron on Linux:

```
45 8 * * * cd /path/to/job-hunt-pipeline && docker compose run --rm jobhunt run >> data/run.log 2>&1
```

On Windows use Task Scheduler with program `docker` and arguments `compose -f C:\path\to\job-hunt-pipeline\docker-compose.yml run --rm jobhunt run`.

## Good to know

* The dashboard port is published on 127.0.0.1 only, so other devices on your network cannot open it. The server also refuses requests that do not come from 127.0.0.1 or localhost.
* "Open folder" on the dashboard does not work inside Docker (the container cannot open your file manager). Open `data/output` yourself.
* Gmail: the first consent needs a browser, which a container does not have. Run `jobhunt gmail` once with a normal Python install to create `token.json`, then copy it into `data`. After that the container can sync until Google asks for consent again.
* On Linux the container runs as user id 1000. If your user has a different id and you get permission errors in `data`, run `sudo chown -R 1000 data`.
* Using Ollama on the same computer: set `base_url = "http://host.docker.internal:11434/v1"` in `config.toml`. On Linux also add `extra_hosts: ["host.docker.internal:host-gateway"]` to the service in `docker-compose.yml`.
