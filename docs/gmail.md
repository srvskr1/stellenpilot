# Gmail status sync (optional)

The sync reads recent mail about your applications and moves statuses forward: confirmation of receipt to Applied, an invitation to Interview, a rejection to Rejected, an offer to Offer. It never moves a status backwards, never sends, deletes or labels mail, and only asks for the read only scope `https://www.googleapis.com/auth/gmail.readonly`.

## One time setup (about 10 minutes)

1. Install the extra packages: `pip install -e ".[gmail]"`
2. Go to https://console.cloud.google.com , create a project (any name).
3. **APIs and Services, Library**: enable the **Gmail API**.
4. **OAuth consent screen**: choose **External**, fill in the app name and your email, add the scope `gmail.readonly`, and add your own Gmail address as a **test user**. Leave the app in **Testing**.
5. **Credentials, Create credentials, OAuth client ID**, type **Desktop app**. Download the JSON and save it as `credentials.json` in your workspace folder (next to `config.toml`).
6. In `config.toml` set `[gmail] enabled = true`.
7. Run `jobradar gmail`. A browser window asks you to allow access. Google shows an "unverified app" warning because it is your own private app; continue.

## Good to know

* Google does not require verification for a personal app in Testing mode, but consent expires after about 7 days in Testing. When the sync fails with an auth error, delete `token.json` and run `jobradar gmail` again.
* Do not share your `credentials.json` or `token.json`. Both are ignored by git.
* Matching uses the company name, so an email from a recruiting platform about a company that is not on your board is ignored.
