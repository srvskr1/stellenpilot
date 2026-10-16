# Email status sync (optional)

The sync reads recent mail about your applications and moves statuses forward: confirmation of receipt to Applied, an invitation to Interview, a rejection to Rejected, an offer to Offer. It never moves a status backwards, and it never sends, deletes, moves or labels mail. Nothing is marked as read.

## The easy way: email address and app password (about 2 minutes)

Open **Settings** and scroll to **Email**.

1. Turn on **2-Step Verification** for your Google account (https://myaccount.google.com/signinoptions/twosv). Google only offers app passwords with it.
2. Open **App passwords** (https://myaccount.google.com/apppasswords), type the name `Stellenpilot` and press **Create**. Copy the 16 letters.
3. Enter your email address and the app password in Stellenpilot and press **Connect**.

Stellenpilot logs in once to check, then saves the app password in `.env` (readable only by you). It opens your inbox read only (IMAP `EXAMINE`) and reads messages with `BODY.PEEK`, so the mailbox cannot change. To stop, press **Disconnect** (this also deletes the saved password) and delete the app password in your Google account.

**Other providers.** GMX, web.de, Yahoo, t-online, Posteo, mailbox.org and iCloud work the same way: switch on IMAP in your mail settings, and create an app password if your account uses 2-Step Verification. For any other provider enter its IMAP server. Outlook and Hotmail only allow Microsoft's own sign in, which is not supported yet.

**When it does not work.** Work and university Google accounts often have app passwords switched off by their administrator. Use the other way below.

## The other way: your own Google key file (about 10 minutes)

This uses the Gmail API with the read only scope `https://www.googleapis.com/auth/gmail.readonly`. In the dashboard open **Other way: your own Google key file** under **Email**: run the install command it shows in a terminal, create and choose the key file, then connect. The Windows and Mac apps already include Gmail support and skip the first step.

## One time setup by hand (about 10 minutes)

1. Install the extra packages: `stellenpilot gmail --install` (from a source checkout, `pip install -e ".[gmail]"` does the same).
2. Go to https://console.cloud.google.com , create a project (any name).
3. **APIs and Services, Library**: enable the **Gmail API**.
4. **OAuth consent screen**: choose **External**, fill in the app name and your email, add the scope `gmail.readonly`, and add your own Gmail address as a **test user**. Leave the app in **Testing**.
5. **Credentials, Create credentials, OAuth client ID**, type **Desktop app**. Download the JSON and save it as `credentials.json` in your workspace folder (next to `config.toml`).
6. In `config.toml` set `[gmail] enabled = true`.
7. Run `stellenpilot gmail`. A browser window asks you to allow access. Google shows an "unverified app" warning because it is your own private app; continue.

## Good to know

* Google does not require verification for a personal app in Testing mode, but consent expires after about 7 days in Testing. When the sync fails with an auth error, delete `token.json` and run `stellenpilot gmail` again.
* Do not share your `credentials.json` or `token.json`. Both are ignored by git.
* Matching uses the company name, so an email from a recruiting platform about a company that is not on your board is ignored.
