# Rules for AI assistants in this repo

Before any git command that writes a commit (commit, cherry-pick, rebase, merge, amend, commit-tree), run:

```
git config user.name "Sourav Sarker"
git config user.email "52565422+srvskr1@users.noreply.github.com"
```

Never add Co-Authored-By, Claude-Session or "Generated with Claude Code" lines to commits or PR descriptions. The `commit identity` check on every PR fails if you do.
