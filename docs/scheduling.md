# Run it every day

## The easy way: the dashboard

Open **Settings**, tick **Search for new jobs automatically every day**, pick a time and save. The dashboard creates the task on your computer for you:

* **Windows**: a Task Scheduler task named "JobHunt daily search". If the PC is off at that time, it runs as soon as you log in.
* **macOS and Linux**: one line in your crontab. A missed search (laptop asleep) runs when you open the dashboard.

The dashboard does not need to be open for the daily search. Untick the box and save to remove the task again. Output goes to `run.log` in your workspace. Inside Docker this is not possible; see [docker.md](docker.md).

The steps below do the same thing by hand.

## By hand

The run takes from under a minute to a few minutes, depending on sources and the AI model. Your computer must be on at that time.

### Windows (Task Scheduler)

1. Find the full path of the command: in your activated virtual environment run `where jobhunt`.
2. Open Task Scheduler and choose **Create Basic Task**.
3. Name it "Job hunt", trigger **Daily**, pick a time such as 08:45.
4. Action **Start a program**:
   * Program: the path from step 1, for example `C:\Users\you\job-hunt-pipeline\.venv\Scripts\jobhunt.exe`
   * Arguments: `--home "C:\Users\you\my-hunt" run`
5. Finish, then right click the task, **Properties**, and tick **Run task as soon as possible after a scheduled start is missed**, so a run still happens when the PC was off.

### Linux (cron)

```bash
crontab -e
# every day at 08:45
45 8 * * * /home/you/job-hunt-pipeline/.venv/bin/jobhunt --home /home/you/my-hunt run >> /home/you/my-hunt/run.log 2>&1
```

### macOS

cron works the same way. On a laptop that sleeps, launchd is more reliable; a minimal plist:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.jobhunt</string>
  <key>ProgramArguments</key><array>
    <string>/Users/you/job-hunt-pipeline/.venv/bin/jobhunt</string>
    <string>--home</string><string>/Users/you/my-hunt</string><string>run</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>45</integer></dict>
</dict></plist>
```

Save it as `~/Library/LaunchAgents/local.jobhunt.plist` and run `launchctl load ~/Library/LaunchAgents/local.jobhunt.plist`.

## The dashboard

Start it whenever you want to look: `jobhunt --home PATH serve`, then open http://127.0.0.1:8765 . While a run is in progress, the office scene shows which step it is on.
