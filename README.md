# Job Hunt Pipeline

A local, open source job hunt assistant for Germany. Every day it collects fresh job ads from public APIs, scores them against your CV, writes a tailored CV and cover letter for the best matches, and shows everything on a dashboard in your browser. It runs on your own computer. Your CV and your data never leave it, except for the AI model you choose.

![Dashboard](docs/dashboard.png)

It never applies for you and never sends email. You stay in control of every application.

## What it does

* **Collects jobs** from the Bundesagentur für Arbeit, Arbeitnow, Adzuna and TheirStack (the last two with your own free keys). It removes duplicates across sources.
* **Scores each job** from 0 to 100 against your profile, with a short reason and honest gaps. Ads that demand fluent German are flagged and skipped (you can switch that off).
* **Learns your taste.** Give jobs a thumbs up or down on the dashboard and the next run leans toward what you liked.
* **Tailors your CV truthfully.** It reorders and selects facts from your profile. It never invents experience. A guard rejects generated text that mentions numbers or tools you did not list, and falls back to safe text.
* **Writes a cover letter** and a short report per job: what the ad asks for, what your CV covers, and which gaps to be honest about.
* **Exports DOCX and PDF** (PDF needs LibreOffice).
* **Optional Gmail sync** (read only) moves statuses forward when confirmations, interview invitations or rejections arrive.
* **Dashboard**: a Today list of what to do next, a pipeline you can filter, notes per job, interview prep, reply rates by source, the skill gaps employers mention most, a weekly summary, and a small animated office that shows what the run is doing.

## Quick start

You need Python 3.11 or newer. Works on Windows, macOS and Linux. On Debian or Ubuntu also install `python3-venv`. On Windows use `python` where the commands below say `python`; on macOS and Linux it may be `python3`.

```bash
git clone https://github.com/srvskr1/job-hunt-pipeline.git
cd job-hunt-pipeline
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS or Linux: source .venv/bin/activate
pip install -e .

mkdir my-hunt && cd my-hunt
jobhunt init      # creates config.toml, profile.toml and .env
jobhunt demo      # optional: fictional sample jobs, to look around first
jobhunt serve     # open http://127.0.0.1:8765
```

Then make it yours:

1. Put your real CV facts into `profile.toml`. Keep bullets short and true; they are copied word for word.
2. Set your keywords, city and radius in `config.toml`.
3. Optional: add API keys to `.env` and switch sources on in `config.toml`.
4. Run `jobhunt doctor` to check the setup, then `jobhunt run` for a real search.

To start fresh after the demo, delete `jobhunt.db`.

## Choosing an AI model

Set `[llm]` in `config.toml`:

| provider | what you need | notes |
|---|---|---|
| `none` | nothing | Keyword scoring and template letters. Works offline, less precise. |
| `anthropic` | `ANTHROPIC_API_KEY` in `.env` | Uses Claude through the Anthropic API. |
| `openai` | `OPENAI_API_KEY`, or a local server | Also works with Ollama or LM Studio: set `base_url = "http://localhost:11434/v1"` and a local model name. Fully offline. |

## Job sources

| source | key | cost and limits | terms you should know |
|---|---|---|---|
| Bundesagentur für Arbeit | none | free | Community documented endpoint (jobsuche.api.bund.dev). No published limits, so requests are kept small. |
| Arbeitnow | none | free | Their terms require a link back to arbeitnow.com. The dashboard shows it. |
| Adzuna | free, from developer.adzuna.com | default 250 calls a day | Allowed for personal research. Adzuna must be credited; every Adzuna job links to Adzuna. Returns short snippets, not full ads. |
| TheirStack | free, from theirstack.com | 200 credits a month, 1 credit per job | Keys may not be shared. Each user needs their own. |

There is no LinkedIn, StepStone or Indeed scraper on purpose. LinkedIn's and StepStone's terms forbid scraping, and Indeed has no public job search API. See [docs/sources.md](docs/sources.md) for the details and links.

## Run it every day

See [docs/scheduling.md](docs/scheduling.md) for Windows Task Scheduler, cron and macOS.

## Gmail status sync (optional)

See [docs/gmail.md](docs/gmail.md). It uses read only access with your own Google Cloud OAuth client.

## Commands

| command | does |
|---|---|
| `jobhunt init` | create config, profile and .env from the examples |
| `jobhunt doctor` | check the setup and keys |
| `jobhunt run` | search, score, tailor, and sync Gmail if enabled |
| `jobhunt run --no-tailor` | search and score only |
| `jobhunt serve` | start the dashboard on 127.0.0.1:8765 |
| `jobhunt gmail` | sync statuses from Gmail once |
| `jobhunt demo` | load fictional sample jobs |

Use `--home PATH` to keep your files in another folder.

## Privacy and safety

* Everything is stored in `jobhunt.db` and the `output` folder next to your config. Both are ignored by git, together with `config.toml`, `profile.toml`, `.env` and Gmail tokens.
* The dashboard listens on 127.0.0.1 only. Write requests need a custom header, so other websites cannot change your data through your browser.
* Your profile and job ads are sent to the AI provider you configure. Choose `none` or a local model if you want nothing to leave your machine.
* Read every tailored document before you send it. The truth guard checks digits and the tools it knows (see `VOCAB` in `jobhunt/score.py`). It cannot judge spelled out numbers or vague claims, so you are the final check.
* Skills in a profile group named "Learning" are never presented as experience; documents may only say you are learning them.

## Project layout

```
jobhunt/
  sources/      one module per job API
  pipeline.py   the daily run: collect, score, tailor, Gmail
  score.py      LLM or keyword scoring, taste from your ratings
  tailor.py     truthful CV plan, DOCX, cover letter, report, PDF
  server.py     local dashboard API
  web/          dashboard page
  examples/     example config and profile
tests/          offline tests: python -m unittest discover -s tests
```

## Contributing

Issues and pull requests are welcome. New sources should use an official or clearly permitted API, follow the shape in `jobhunt/sources/__init__.py`, and come with an offline test.

## Credits and license

MIT, see [LICENSE](LICENSE). Credits for ideas and data are in [NOTICE.md](NOTICE.md).
