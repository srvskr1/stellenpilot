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
* Allowed uses include "Personal research". Default limits: 25 calls a minute, 250 a day, 1000 a week, 2500 a month. This tool makes `adzuna_calls` calls per run (4 by default).
* Credit is required: Adzuna must be acknowledged as the source wherever its data is shown, with a link. The dashboard labels Adzuna jobs with a linked "Adzuna" tag.
* Use by companies, governments or universities is a 14 day trial, after which a licence may be required.
* The API returns a short description snippet, so scores for Adzuna jobs are less precise.

## TheirStack

* Free plan: 200 API credits a month; each job returned costs 1 credit. Rate limit on the free plan: 4 a second, 10 a minute, 50 an hour, 400 a day.
* Terms (https://theirstack.com/en/docs/legal/terms-and-conditions) forbid sharing API keys. Every user needs their own key.
* `theirstack_jobs` caps the number of jobs per run (6 by default, which fits the free plan for a month of daily runs).

## Not included, on purpose

* **LinkedIn**: the User Agreement forbids software that scrapes or copies the service (https://www.linkedin.com/legal/user-agreement).
* **StepStone**: the terms of use (section 4.3.4) forbid scraping or similar techniques.
* **Indeed**: there is no public job search API for open source clients today.
