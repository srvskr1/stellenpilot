# Privacy and safety

* **Local first.** Everything is stored in `jobhunt.db` and the `Stellenpilot` folder next to your config, on your computer. With the built-in AI or another local model, nothing about you leaves it.
* With Claude or OpenAI, your profile and the job ads are sent to that provider.
* The dashboard listens on 127.0.0.1 only, and write requests need a custom header, so other websites cannot change your data through your browser.
* **Updates.** Once a day Stellenpilot asks GitHub whether a newer version exists. That request carries only the version number, never your data, and you can switch it off under Settings, Language. If there is one, Home shows a **Download** button for the installer from the Stellenpilot releases. Run it and it updates your app in place; your workspace is never touched. Stellenpilot itself never downloads or runs anything.
* Read every document before you send it. The truth guard checks digits and the tools it knows (see `VOCAB` in `stellenpilot/score.py`). It cannot judge spelled out numbers or vague claims, so you are the final check.
* Why the server, the guards, the link fetcher and the AI downloads are built the way they are: [docs/architecture.md](https://github.com/srvskr1/stellenpilot/blob/main/docs/architecture.md)


[Back to the README](https://github.com/srvskr1/stellenpilot#readme)
