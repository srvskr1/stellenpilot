# Live traffic for stellenpilot.dev

A small Cloudflare Worker that shows who is on the website right now and how often the download buttons get used. It runs on the Cloudflare free plan. No cookies, no IP addresses kept and nothing stored on the visitor's device. The privacy page (`docs/datenschutz.html`, section Besucherzählung) describes exactly this, so update it if you change what gets sent.

## What it shows

1. Visitors right now, page views per minute for the last hour, top pages, where visitors came from and their countries
2. Download clicks by platform, live
3. Real downloads: GitHub release files (all time, by platform) and pip installs from PyPI (day, week, month), refreshed every 10 minutes

A click on a download button opens GitHub, so clicks show interest. The GitHub and PyPI numbers are the finished downloads.

## Files

1. `worker.js` counts visits and serves the viewer
2. `viewer.html` the dashboard, shows demo data until you enter your view key
3. `../docs/live.js` the counter every page of the site loads; it does nothing until its Worker URL is set
4. `check.mjs` self test, run `npm run check`

## First deploy

1. `cd live` then `npm install`
2. `npx wrangler login` and approve in the browser
3. `npm run deploy` and copy the URL it prints, like `https://stellenpilot-live.NAME.workers.dev`
4. `npx wrangler secret put VIEW_KEY` and paste a long random password
5. Put the URL plus `/hit` into `U` at the top of `docs/live.js` and push
6. Open the Worker URL, click View key, enter the password

## Limits

1. Counts live in memory, so a Worker restart starts them from zero. It is a live view, not an archive.
2. Each open tab counts as one visitor.
3. GitHub allows 60 API calls an hour without a token; the Worker uses 6.
