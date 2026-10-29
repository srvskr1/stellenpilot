# Features

## Automation

* **Daily autopilot.** Switch on **Automatic search** in Settings and pick a time. Stellenpilot sets up Task Scheduler on Windows or cron on macOS and Linux for you. The dashboard does not need to be open. A search missed because the computer was off runs when you log in or open Stellenpilot. Doing it by hand: [docs/scheduling.md](https://github.com/srvskr1/stellenpilot/blob/main/docs/scheduling.md)
* **Company watchlist.** Switch on the ready made list of about 200 companies with offices in Germany, or add your dream companies that use Greenhouse, Lever, Ashby, Personio or SmartRecruiters. Their new roles often appear here before they reach the job boards.
* **Email sync.** Read only. Connect Gmail (or GMX, web.de and others) in **Settings, Email** with your address and an app password, in about 2 minutes, and statuses move forward as replies arrive. It never sends, deletes, moves or labels mail. If your Google account has no app passwords, use your own Google key file instead: run `stellenpilot gmail --install` in a terminal, then follow the steps the dashboard shows. Details: [docs/gmail.md](https://github.com/srvskr1/stellenpilot/blob/main/docs/gmail.md)
* **Daily digest** to Telegram or email: top new matches, documents ready to send, interviews. See [docs/digest.md](https://github.com/srvskr1/stellenpilot/blob/main/docs/digest.md)
* **Jobs you found yourself.** Paste a link or the ad text from LinkedIn, a friend or anywhere, and the AI scores and tailors it like the rest.

## The dashboard

Five calm pages, in your browser, on your computer:

* **Home**: what is ready to apply, interviews coming up, the newest matches, and a small 3D office where a robot works through each step of the search.
* **Jobs**: every job with its score, why it fits, honest gaps, your documents, notes and interview prep. Filter by word, source, type, place, day, match or status, and see which tools of the ad you have, which ones you are missing, and what the job would score with each of them.
* **Applications**: a board you drag cards across (Applied, Interview, Offer, Rejected). Below it, Insights shows reply rates by source and CV layout, where your applications stop (CV, first check or interviews), a follow up email for interviews that went quiet, how many English ads still want good German, the skills that would open the most jobs for you, and a weekly summary.
* **My CV**: your profile, with tips to improve your matches.
* **Settings**: language (English or Deutsch), job sources, the AI, the daily search and Gmail, with step by step help for every key.

Something broken? **Report a bug** in the sidebar or in Settings opens the bug report form on GitHub.


[Back to the README](https://github.com/srvskr1/stellenpilot#readme)
