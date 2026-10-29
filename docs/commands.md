# Commands

| command | does |
|---|---|
| `stellenpilot init` | create config, profile and .env from the examples |
| `stellenpilot doctor` | check the setup and keys |
| `stellenpilot run` | search, score, tailor, and sync Gmail if enabled |
| `stellenpilot run --no-tailor` | search and score only |
| `stellenpilot serve` | start the dashboard on 127.0.0.1:8765 and open it in the browser (`--no-browser` to skip) |
| `stellenpilot shortcut` | put a Stellenpilot icon on the desktop that starts this workspace |
| `stellenpilot gmail` | sync statuses from Gmail once |
| `stellenpilot gmail --install` | install the Google packages for the own key file way of Gmail sync |
| `stellenpilot demo` | load fictional sample jobs |
| `stellenpilot import cv.pdf` | turn your CV into `profile.imported.toml` to review |
| `stellenpilot add LINK` | add a job from a careers page link |
| `stellenpilot add --text ad.txt --title "..." --company "..." --tailor` | add a pasted ad and tailor it now |
| `stellenpilot watch LINK` | find the watchlist entry for a company |
| `stellenpilot eval` | measure how well scoring ranks the jobs you labeled ([docs/evaluation.md](https://github.com/srvskr1/stellenpilot/blob/main/docs/evaluation.md)) |
| `stellenpilot eval --make-sheet` | write 100 jobs to label by hand in `eval/labels.csv` |
| `stellenpilot notify-test` | send a test digest |
| `stellenpilot telegram-id` | show your Telegram chat id |

Use `--home PATH` to keep your files in another folder.

## Project layout

```
stellenpilot/
  sources/      one module per job API
  pipeline.py   the daily run: collect, score, tailor, Gmail
  score.py      LLM or keyword scoring, taste from your ratings
  evaluate.py   scoring evaluation: labels, metrics, model comparison
  tailor.py     truthful CV plan, DOCX, cover letter, report, PDF
  server.py     local dashboard API
  web/          dashboard page
  examples/     example config and profile
tests/          offline tests: python -m unittest discover -s tests
```


[Back to the README](https://github.com/srvskr1/stellenpilot#readme)
