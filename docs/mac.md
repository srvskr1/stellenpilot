# Stellenpilot on a Mac

## Install the app

1. Open the [latest release](https://github.com/srvskr1/stellenpilot/releases/latest) and download **Stellenpilot-X.Y.Z-mac.dmg**.
2. Open the downloaded file. A window shows **Stellenpilot** and an **Applications** folder.
3. Drag **Stellenpilot** onto **Applications**.

The app is for Macs with an Apple chip (M1 or newer). On an older Mac with an Intel chip, use Python instead: see [INSTALL.md](../INSTALL.md).

## The first start (once)

The app is free and open source, but it is not signed with a paid Apple developer certificate yet. That is why macOS stops it the first time. Your Mac is fine, and the app is built by GitHub straight from this repository.

**macOS 15 (Sequoia) and newer**

1. Open **Applications** and double click **Stellenpilot**. macOS says it could not check the app. Click **Done** (not "Move to Trash").
2. Open **System Settings**, then **Privacy & Security**.
3. Scroll down to **Security**. You see a line saying Stellenpilot was blocked. Click **Open Anyway**.
4. Enter your Mac password, then click **Open Anyway** once more.

**macOS 14 (Sonoma) and older**

1. Open **Applications**, hold the **Control** key and click **Stellenpilot**, then choose **Open**.
2. Click **Open** in the message that follows.

From then on Stellenpilot opens with a normal double click.

**"Stellenpilot is damaged and can't be opened"?** That is the same check with a scarier message. Open the **Terminal** app, paste this line and press Return, then start the app again:

```
xattr -dr com.apple.quarantine /Applications/Stellenpilot.app
```

## Using it

* Double click **Stellenpilot**. Your browser opens the dashboard, and a small window with **Open dashboard** and **Stop Stellenpilot** appears. Keep that window open while you use it.
* Your files (CV, settings, the documents it writes) are in the folder **Stellenpilot** in your home folder. In Finder: **Go**, **Home**.
* The built-in AI works the same as on Windows: press **Download** under **Settings, AI model**. Its engine comes in a ready made version for Apple chips.
* The daily search runs even when the app is closed, as long as the Mac is awake at that time.

## Remove it

Drag **Stellenpilot** from **Applications** to the Trash. Your files stay in the **Stellenpilot** folder in your home folder, and the built-in AI in the hidden folder `.stellenpilot`; delete those too if you want everything gone. Switch off the daily search in **Settings** first, or remove it as described in [scheduling.md](scheduling.md).
