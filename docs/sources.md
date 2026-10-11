# Job sources and their terms

Checked on 10 October 2026. Terms change, so read the linked pages yourself before relying on this summary.

## Bundesagentur für Arbeit

* Endpoint: `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs` with the header `X-API-Key: jobboerse-jobsuche`. Full ad text comes from `/pc/v4/jobdetails/{base64 reference number}`.
* The BA offers no official API. The endpoint is documented by the community at https://jobsuche.api.bund.dev/ and https://github.com/bundesAPI/jobsuche-api . No rate limits or terms of use are published, so this tool keeps requests small (`arbeitsagentur_results`).
* The older `/pc/v4/jobs` search path returns 403 today; this tool uses v6.

## Arbeitnow

* Endpoint: `https://www.arbeitnow.com/api/job-board-api`, free, no key, about 325 newest jobs per page.
* Terms (https://www.arbeitnow.com/terms, section API): "You also agree to providing a link back to Arbeitnow.com on your platform." The dashboard links every Arbeitnow job and the footer to arbeitnow.com.
* The site's general terms limit use of its materials to personal, non commercial purposes.

## Adzuna

* Get a free key at https://developer.adzuna.com . Terms: https://developer.adzuna.com/docs/terms_of_service
* Allowed uses include "Personal research". Default limits: 25 calls a minute, 250 a day, 1000 a week, 2500 a month. This tool makes at most `adzuna_calls` calls per run (20 by default, 140 a week): page 1 for every search first, then further pages (50 jobs each, up to `adzuna_pages`) while budget is left.
* Credit is required: Adzuna must be acknowledged as the source wherever its data is shown, with a link. The dashboard labels Adzuna jobs with a linked "Adzuna" tag.
* Use by companies, governments or universities is a 14 day trial, after which a licence may be required.
* The API returns a short description snippet, so scores for Adzuna jobs are less precise.

## TheirStack

* Free plan: 200 API credits a month; each job returned costs 1 credit. Rate limit on the free plan: 4 a second, 10 a minute, 50 an hour, 400 a day.
* Terms (https://theirstack.com/en/docs/legal/terms-and-conditions) forbid sharing API keys. Every user needs their own key.
* `theirstack_jobs` caps the number of jobs per run (6 by default, which fits the free plan for a month of daily runs).

## Jobicy

* Free and keyless remote job API: https://jobicy.com/jobs-rss-feed . Listings cover the last 7 days.
* Terms: credit Jobicy with a clickable link to the original listing and never present the listings as your own; start an automated pass at most once an hour. The dashboard labels Jobicy jobs with a linked "Jobicy" tag and links to the Jobicy page.
* Their site blocks bursts of requests, so this tool searches your country and "Europe" only, pauses 3 seconds between calls, makes at most `jobicy_pages` pages each (2 by default), and keeps what it has if it gets blocked.

## Remotive

* Free and keyless remote job API: https://remotive.com/api-documentation
* Terms: link back to the job's Remotive URL and name Remotive as the source; do not resubmit the jobs to other job sites; call it at most about 4 times a day. This tool makes one call per run.
* The free feed is small (a few dozen jobs at a time) and delayed by 24 hours, so expect only a few matches.

## How many jobs to expect

Measured on 11 October 2026 for data roles near Essen: with narrow titles ("Werkstudent Data", "Junior Data Engineer") and ads from the last 3 days, the Bundesagentur returned 15 jobs; the number is limited by the market, not by pages. With broader titles ("Data Engineer", "Data Analyst", "Python") and 14 days it returned 87 instead of 50 before pagination, Arbeitnow 3 instead of 0, and over 7 days Jobicy added 4 remote roles while Remotive added none. Broader titles and a longer `max_age_days` find more; the company watchlist finds roles that never reach job boards.

## Not included, on purpose

* **LinkedIn**: the User Agreement forbids software that scrapes or copies the service (https://www.linkedin.com/legal/user-agreement).
* **StepStone**: the terms of use (section 4.3.4) forbid scraping or similar techniques.
* **Indeed**: there is no public job search API for open source clients today.

## Company watchlist feeds

All checked live on 10 October 2026. None needs a key.

| system | feed | notes |
|---|---|---|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | Docs: "Job Board data is publicly available, so authentication is not required" (https://developers.greenhouse.io/job-board.html). Job text arrives as escaped HTML. |
| Lever | `https://api.lever.co/v0/postings/{site}?mode=json` | EU accounts use `api.eu.lever.co`; the tool tries both. The README says published postings "may be scraped by third parties" (https://github.com/lever/postings-api). |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{name}` | https://developers.ashbyhq.com/docs/public-job-posting-api |
| Personio | `https://{company}.jobs.personio.de/xml` | Personio's FAQ: no credentials needed. Some companies disable the hosted job page, so the job link may not open even though the feed works. |
| SmartRecruiters | `https://api.smartrecruiters.com/v1/companies/{id}/postings` | Public Posting API. An unknown company id returns zero jobs, not an error, so check `stellenpilot watch` output. |

## German level phrases

The tool maps phrases to CEFR levels using conventions from German career sites. They are conventions, not an official standard:

| phrase | level |
|---|---|
| Muttersprache, native | C2 |
| verhandlungssicher, business fluent, sehr gute Deutschkenntnisse, very good German | C1 |
| fließend, fluent, gute Deutschkenntnisse, good German | B2 |
| Grundkenntnisse, basic German | A2 |
| von Vorteil, wünschenswert, is a plus, nice to have | optional, not required |

Sources: karriere.at (lebenslauf-sprachkenntnisse), jobcannon.io (what German level do employers actually ask for), Lingoda (German language levels), karrierebibel.de (Muss und Kann Qualifikationen).
