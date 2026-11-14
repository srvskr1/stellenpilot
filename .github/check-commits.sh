#!/usr/bin/env bash
# Usage: check-commits.sh <git range>. Exits 1 if any commit in the range
# has an author or committer that is not Sourav (or GitHub for web merges),
# or a Co-Authored-By / Claude-Session / "Generated with Claude" line.
set -euo pipefail
ok='^(52565422\+srvskr1@users\.noreply\.github\.com|souravsarkersrv@gmail\.com)$'
ok_committer='^(52565422\+srvskr1@users\.noreply\.github\.com|souravsarkersrv@gmail\.com|noreply@github\.com)$'
bad=0
while IFS='|' read -r sha ae ce; do
  [[ $ae =~ $ok ]] || { echo "::error::$sha author is $ae"; bad=1; }
  [[ $ce =~ $ok_committer ]] || { echo "::error::$sha committer is $ce"; bad=1; }
  if git log -1 --format=%B "$sha" | grep -qiE '^(co-authored-by:|claude-session:)|generated with .*claude'; then
    echo "::error::$sha has an AI attribution line in its message"; bad=1
  fi
done < <(git log --format='%H|%ae|%ce' "$1")
[ $bad = 0 ] && echo "All commits are Sourav's, no attribution lines."
exit $bad
