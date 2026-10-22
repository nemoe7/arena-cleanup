#!/usr/bin/env bash
# End-to-end tests for arena-cleanup against throwaway repos + a fake gh.
# Usage: bash run-tests.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/engine.py" # the rewrite engine lives right next to the tests
T="$(mktemp -d /tmp/arena-test.XXXXXX)"
export PYTHONIOENCODING=utf-8
export TMPDIR="$T/tmp"
mkdir -p "$TMPDIR"

PASS=0
FAIL=0
SKIP=0
ok() {
  echo "  PASS  $1"
  PASS=$((PASS + 1))
}
bad() {
  echo "  FAIL  $1"
  FAIL=$((FAIL + 1))
}
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (expected [$3], got [$2])"; fi; }

# ---------------------------------------------------------------- fixtures ---
ME_EMAIL="60245796+nemoe7@users.noreply.github.com"
# the one place the version is set; the engine and the UI must both report it
PROJECT_VERSION="$(python3 -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$HERE/pyproject.toml")"
export GIT_CONFIG_GLOBAL="$T/gitconfig"
cat >"$GIT_CONFIG_GLOBAL" <<EOF
[user]
    name = nemoe7
    email = $ME_EMAIL
[init]
    defaultBranch = main
[commit]
    gpgsign = false
[advice]
    detachedHead = false
EOF

# fake gh: PR state driven by files so tests can flip it
mkdir -p "$T/bin"
cat >"$T/bin/gh" <<'EOF'
#!/usr/bin/env bash
state_file="${FAKE_GH_STATE:-/tmp/fake-gh-state}"
if [ "$1 $2" = "pr list" ]; then
  if [ "$(cat "$state_file" 2>/dev/null)" = "none" ]; then
    echo '[]'
  else
    echo '[{"number":42}]'
  fi
  exit 0
fi
if [ "$1 $2" = "pr view" ]; then
  state="$(cat "$state_file" 2>/dev/null)"
  case "$state" in
    failing)
      echo '{"statusCheckRollup":[{"name":"build","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"test","status":"COMPLETED","conclusion":"FAILURE"}]}' ;;
    pending)
      # in progress for the first two polls, then green - exercises the waiting path
      n="$(cat "$state_file.count" 2>/dev/null || echo 0)"; n=$((n+1)); echo "$n" > "$state_file.count"
      if [ "$n" -ge 2 ]; then
        echo '{"statusCheckRollup":[{"name":"build","status":"COMPLETED","conclusion":"SUCCESS"}]}'
      else
        echo '{"statusCheckRollup":[{"name":"build","status":"IN_PROGRESS","conclusion":""}]}'
      fi ;;
    superseded)
      echo '{"statusCheckRollup":[{"name":"build","status":"COMPLETED","conclusion":"CANCELLED"},{"name":"build","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"test","status":"COMPLETED","conclusion":"SUCCESS"}]}' ;;
    superseded-failing)
      echo '{"statusCheckRollup":[{"name":"build","status":"COMPLETED","conclusion":"CANCELLED"},{"name":"build","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"test","status":"COMPLETED","conclusion":"FAILURE"}]}' ;;
    pending-forever)
      echo '{"statusCheckRollup":[{"name":"build","status":"IN_PROGRESS","conclusion":""}]}' ;;
    bad-shape)
      # a wrapper around gh printing a bare list: gh never does, a wrapper can
      echo '[{"name":"build","status":"COMPLETED","conclusion":"SUCCESS"}]' ;;
    none)
      echo '[]' ;;
    *)
      echo '{"statusCheckRollup":[{"name":"build","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"test","status":"COMPLETED","conclusion":"SUCCESS"}]}' ;;
  esac
  exit 0
fi
if [ "$1 $2" = "auth status" ]; then
  if [ "$(cat "$state_file.auth" 2>/dev/null)" = "out" ]; then
    echo "You are not logged into any GitHub hosts." >&2
    exit 1
  fi
  if [ "$3" = "--json" ]; then
    echo '{"hosts":{"github.com":[{"state":"success","active":true,"host":"github.com","login":"nemoe7","tokenSource":"oauth_token","scopes":"repo, read:org"}]}}'
  else
    echo "github.com"
    echo "  ✓ Logged in to github.com account nemoe7 (keyring)"
  fi
  exit 0
fi
if [ "$1 $2" = "auth login" ]; then cat >"$state_file.stdin"; exit 0; fi
if [ "$1 $2" = "auth setup-git" ]; then exit 0; fi
if [ "$1 $2" = "pr status" ]; then exit 0; fi
echo "fake gh: unhandled: $*" >&2; exit 1
EOF
chmod +x "$T/bin/gh"
export FAKE_GH_STATE="$T/gh-state"
export PATH="$T/bin:$PATH"

# the suite calls the engine directly; the shim keeps the test bodies readable
cat >"$T/bin/arena-cleanup" <<EOF
#!/usr/bin/env bash
exec python3 "$SCRIPT" "\$@"
EOF
chmod +x "$T/bin/arena-cleanup"

# a throwaway GPG key so the suite exercises the real signing path
GPG_OK=0
if command -v gpg >/dev/null 2>&1; then
  export GNUPGHOME="$T/gnupg"
  mkdir -p "$GNUPGHOME"
  chmod 700 "$GNUPGHOME"
  gpg --batch --quiet --passphrase '' --quick-generate-key \
    "Test Signer <signer@example.com>" default default 0 2>/dev/null
  KEYID="$(gpg --list-secret-keys --with-colons 2>/dev/null | awk -F: '/^sec/{print $5; exit}')"
  [ -n "$KEYID" ] && GPG_OK=1 || echo "note: no test key, signing paths will be skipped"
fi

# leave exactly one origin/arena/* branch behind, so branch discovery is
# unambiguous (several is a supported-but-asking case, tested separately)
only_arena() {
  local keep="$1" b
  for b in $(git ls-remote --heads origin 2>/dev/null | awk '{print $2}' |
    sed 's|refs/heads/||' | grep '^arena/'); do
    [ "$b" = "$keep" ] || git push -q origin --delete "$b"
  done
  git fetch -q --prune origin
}

# a repo with the interesting commit shapes
mkdir -p "$T/origin.git"
git init --bare -q -b main "$T/origin.git"
git clone -q "$T/origin.git" "$T/work"
cd "$T/work"
[ "$GPG_OK" = 1 ] && git config user.signingkey "$KEYID" && git config gpg.program gpg

commit() { # name email date msgfile
  GIT_AUTHOR_NAME="$1" GIT_AUTHOR_EMAIL="$2" GIT_AUTHOR_DATE="$3" \
    GIT_COMMITTER_NAME="$1" GIT_COMMITTER_EMAIL="$2" GIT_COMMITTER_DATE="$3" \
    git commit -q --allow-empty -F "$4" --no-gpg-sign
}

printf 'chore: init\n' >"$T/m0"
printf 'feat: external contribution\n\nbody the human wrote\n' >"$T/m1"
printf 'feat: agent work\n\nlong body that should be trimmed\n' >"$T/m2"
printf 'fix: mine already fine\n' >"$T/m3"
printf 'chore: bot cleanup\n\nanother body to trim\n' >"$T/m4"

# mainline: one unrelated commit, pushed straight to origin
commit "other-dev" "other@example.com" "2024-01-01T10:00:00+08:00" "$T/m0"
git push -q -u origin main

# the arena branch: an external contribution, then agent/mine/bot commits
git checkout -q -b arena/session-1
commit "other-dev" "other@example.com" "2024-01-02T10:00:00+08:00" "$T/m1"
commit "arena-agent" "agent@arena.ai" "2024-01-03T10:00:00+08:00" "$T/m2"
commit "nemoe7" "$ME_EMAIL" "2024-01-04T10:00:00+08:00" "$T/m3"
commit "arena-ai-coding-agent[bot]" "bot@arena.ai" "2024-01-05T10:00:00+08:00" "$T/m4"
git push -q -u origin arena/session-1

git checkout -q main
# a stale local arena branch that is NOT on origin
git branch arena/stale main
OLD_TIP="$(git rev-parse arena/session-1)"
ORIG_M1="$(git rev-parse arena/session-1~3)"
ORIG_M0="$(git rev-parse main)"
AUTHOR_DATE_AGENT="$(git log -1 --format=%aI arena/session-1~2)"

echo
echo "=== 1. dry run changes nothing ==="
cd "$T/work" && git checkout -q arena/session-1
before="$(git rev-parse HEAD)"
out="$(arena-cleanup run --dry-run 2>&1)"
rc=$?
check "dry run exit code" "$rc" "0"
check "dry run left HEAD alone" "$(git rev-parse HEAD)" "$before"
echo "$out" | grep -q "would force-push" && ok "dry run announced the push" || bad "dry run push notice"
echo "$out" | grep -qi "would delete stale local branch arena/stale" && ok "dry run announced branch deletion" || bad "dry run branch deletion notice"
git show-ref --verify --quiet refs/heads/arena/stale && ok "dry run kept arena/stale" || bad "dry run deleted arena/stale"

# dry run while sitting on the default branch: it must resolve the arena branch
# first and describe THAT branch, without touching the working tree (regression:
# it used to report on main itself and wrongly conclude "nothing to publish")
git checkout -q main
out="$(arena-cleanup --dry-run 2>&1)"
echo "$out" | grep -q "would switch to arena/session-1" && ok "dry run found the arena branch" || bad "dry run branch discovery"
echo "$out" | grep -q "would force-push arena/session-1" && ok "dry run reports on the arena branch, not main" || {
  bad "dry run target branch"
  echo "$out" | tail -4
}
check "dry run left the working tree on main" "$(git branch --show-current)" "main"
check "dry run moved no refs" "$(git rev-parse main)" "$(git rev-parse origin/main)"
git checkout -q arena/session-1

echo
echo "=== 2. logging format ==="
echo "$out" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{2}:[0-9]{2} (INFO|OK|WARN|ERROR) ' &&
  ok "ISO-8601 local timestamps" || {
  bad "ISO-8601 timestamps"
  echo "$out" | head -3
}
# every line that is not a dimmed verbatim dump must start with a timestamp
strays="$(echo "$out" | grep -vE '^([0-9]{4}-[0-9]{2}-[0-9]{2}T|  \| | +$)' | wc -l)"
check "no untimestamped noise at all" "$strays" "0"
echo "$out" | grep -qE '^s+s*' && bad "progress mark spam is back" || ok "no per-commit mark spam"
echo "$out" | grep -q "scanning... " && ok "captured output still reports progress" || bad "no progress when redirected"

echo
echo "=== 3. strip: identity, dates, message trimming ==="
out="$(arena-cleanup strip 2>&1)"
rc=$?
check "strip exit code" "$rc" "0"
echo "$out" | grep -qE "3 rewritten, [0-9]+ signed, 2 untouched" && ok "reported 3 rewritten / 2 untouched" || {
  bad "rewrite counts"
  echo "$out" | tail -3
}
NEW_TIP="$(git rev-parse HEAD)"
[ "$NEW_TIP" != "$OLD_TIP" ] && ok "tip moved" || bad "tip did not move"
check "commits diverged from main" "$(git rev-list --count main..HEAD)" "4"
check "root commit (already on main) kept its hash" "$(git rev-parse HEAD~4)" "$ORIG_M0"
check "external commit kept its hash (no rewrite)" "$(git rev-parse HEAD~3)" "$ORIG_M1"
[ "$(git rev-parse HEAD~2)" != "$(git rev-parse origin/arena/session-1~2)" ] && ok "claimed commit was rewritten" || bad "claimed commit not rewritten"
check "no author is arena-agent any more" \
  "$(git log --format='%an|%ae' HEAD | grep -c 'arena-agent\|arena-ai-coding-agent')" "0"
check "external commit kept its author" \
  "$(git log -1 --format='%an <%ae>' HEAD~3)" "other-dev <other@example.com>"
check "external commit kept its message body" \
  "$(git log -1 --format=%B HEAD~3 | tail -2 | head -1)" "body the human wrote"
check "claimed commit message trimmed" "$(git log -1 --format=%B HEAD~2)" "feat: agent work"
check "bot commit message trimmed" "$(git log -1 --format=%B HEAD)" "chore: bot cleanup"
check "agent author date preserved" "$(git log -1 --format=%aI HEAD~2)" "$AUTHOR_DATE_AGENT"
check "committer identity applied" "$(git log -1 --format='%cn <%ce>' HEAD)" "nemoe7 <$ME_EMAIL>"
check "external commit reparented but intact" \
  "$(git log -1 --format='%s' HEAD~3)" "feat: external contribution"
check "external commit untouched by identity rewrite" \
  "$(git log -1 --format='%an' HEAD~3)" "other-dev"
check "history is still linear/complete" "$(git rev-list --count HEAD)" "5"

echo
echo "=== 4. strip is idempotent + --check ==="
arena-cleanup strip >/dev/null 2>&1
arena-cleanup strip --check >/dev/null 2>&1
check "second strip --check reports clean (exit 0)" "$?" "0"
tip_before="$(git rev-parse HEAD)"
arena-cleanup strip >/dev/null 2>&1
check "second strip is a no-op" "$(git rev-parse HEAD)" "$tip_before"
check "backup bundle was written" "$(ls "${TMPDIR:-/tmp}"/git-pre-rewrite-*.bundle 2>/dev/null | wc -l | tr -d ' ')" "1"

echo
echo "=== 5. full run from the default branch (switch + push + return) ==="
cd "$T/work" && git checkout -q main
git reset -q --hard origin/main 2>/dev/null || true
# make origin/arena/session-1 differ from main so there is work to publish
git checkout -q arena/session-1
git commit -q --allow-empty -m "chore: more bot work" \
  --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q --force origin arena/session-1
git checkout -q main
git fetch -q --prune origin
echo "open" >"$FAKE_GH_STATE"
out="$(arena-cleanup -K 2>&1)"
rc=$?
check "run (default branch) exit code" "$rc" "0"
if [ "$rc" != 0 ]; then echo "$out" | sed 's/^/      | /'; fi
echo "$out" | grep -q "switching to arena/session-1" && ok "switched to arena branch" || bad "switch notice"
echo "$out" | grep -q "force-pushing" && ok "force-pushed" || bad "push notice"
check "returned to main" "$(git branch --show-current)" "main"
check "main reset to origin/main" "$(git rev-parse main)" "$(git rev-parse origin/main)"
check "arena/stale pruned" "$(git show-ref --verify --quiet refs/heads/arena/stale && echo present || echo gone)" "gone"
check "origin/main == rewritten arena branch" "$(git rev-parse origin/main)" "$(git rev-parse arena/session-1)"
check "pushed main carries the newer bot commit" \
  "$(git log --format=%s origin/main | grep -c 'more bot work')" "1"
check "no arena-agent authors left on origin/main" \
  "$(git log --format='%an' origin/main | grep -c 'arena-agent' || true)" "0"

echo
echo "=== 6. second run is a clean no-op ==="
out="$(arena-cleanup -K 2>&1)"
rc=$?
check "idempotent run exit code" "$rc" "0"
if [ "$rc" != 0 ]; then echo "$out" | sed 's/^/      | /'; fi
echo "$out" | grep -q "already contains" && ok "detected in-sync state" || bad "in-sync detection"
echo "$out" | grep -q "hint:" && bad "git's raw advice leaked into the log" || ok "no raw git advice in the log"
echo "$out" | grep -q "WARN.*fast-forward" && bad "rewrite divergence reported as a warning" || ok "rewritten divergence is not a warning"
echo "$out" | grep -q "rewritten version of origin/arena/session-1" && ok "explained the hash-only divergence" || {
  bad "no explanation for the divergence"
  echo "$out" | grep -i "upstream\|diverg" | sed 's/^/      | /'
}
strays6="$(echo "$out" | grep -vcE '^([0-9]{4}-[0-9]{2}-[0-9]{2}T|  \| | +$)')"
check "no untimestamped lines in a quiet run" "$strays6" "0"

echo
echo "=== 7. PR gate ==="
cd "$T/work" && git checkout -q arena/session-1
git commit -q --allow-empty -m "chore: bot work 2" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
echo "none" >"$FAKE_GH_STATE"
out="$(arena-cleanup run -K 2>&1)"
rc=$?
check "missing PR blocks the run" "$rc" "1"
if ! echo "$out" | grep -q "no open PR"; then echo "$out" | sed 's/^/      | /'; fi
echo "$out" | grep -q "no open PR" && ok "explained the PR gate" || bad "PR gate message"
out="$(arena-cleanup run --skip-pr-check --dry-run 2>&1)"
rc=$?
check "--skip-pr-check bypasses the gate" "$rc" "0"
echo "failing" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"
started="$(date +%s)"
out="$(arena-cleanup run 2>&1)"
rc=$?
elapsed=$(($(date +%s) - started))
check "failing check blocks the run" "$rc" "1"
[ "$elapsed" -le 5 ] && ok "failing checks abort without waiting (${elapsed}s)" || bad "waited on a failing check"
echo "$out" | grep -q 'check "test": FAILURE' && ok "reported the failing check" || {
  bad "failing check report"
  echo "$out" | sed 's/^/      | /'
}
echo "$out" | grep -q "has failing check(s)" && ok "explained the abort" || bad "failing check abort message"
echo "bad-shape" >"$FAKE_GH_STATE"
out="$(arena-cleanup run 2>&1)"
rc=$?
check "a malformed rollup fails the run" "$rc" "1"
echo "$out" | grep -q "printed a list, not a JSON object" && ok "named the shape gh gave" || {
  bad "malformed rollup message"
  echo "$out" | tail -3
}
echo "$out" | grep -qi "traceback" && bad "malformed rollup leaked a traceback" ||
  ok "no traceback from a malformed rollup"

echo "pending" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"
out="$(arena-cleanup run --dry-run 2>&1)"
rc=$?
check "dry run does not block on running checks" "$rc" "0"
echo "$out" | grep -q "would wait for 1 still-running check" && ok "dry run says it would wait" || {
  bad "dry run wait notice"
  echo "$out" | tail -3
}

echo "pending" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"
out="$(arena-cleanup run -K --check-interval 1 --check-timeout 30 2>&1)"
rc=$?
check "running checks are waited for, then the run proceeds" "$rc" "0"
echo "$out" | grep -q "still running; waiting up to" && ok "announced the wait" || {
  bad "wait announcement"
  echo "$out" | tail -5
}
echo "$out" | grep -q 'check "build": SUCCESS' && ok "reported the check turning green" || bad "check-green reporting"
echo "$out" | grep -q "all 1 check(s) finished" && ok "reported completion" || bad "completion line"

# the run above published this branch, so add work to get back past the early exit
git commit -q --allow-empty -m "chore: work for the timeout test" \
  --author="arena-agent <agent@arena.ai>" --no-gpg-sign
echo "pending-forever" >"$FAKE_GH_STATE"
out="$(arena-cleanup run -K --check-interval 1 --check-timeout 3 2>&1)"
rc=$?
check "a check that never finishes times out" "$rc" "1"
echo "$out" | grep -q "timed out after 3s" && ok "explained the timeout" || {
  bad "timeout message"
  echo "$out" | tail -4
}
echo "$out" | grep -q "still running: build" && ok "named the stuck check" || bad "stuck check not named"

echo "pending-forever" >"$FAKE_GH_STATE"
out="$(arena-cleanup run -K --check-timeout 0 2>&1)"
rc=$?
check "--check-timeout 0 refuses instead of waiting" "$rc" "1"
echo "$out" | grep -q "waiting is disabled" && ok "explained --check-timeout=0" || bad "no-wait message"

echo "pending-forever" >"$FAKE_GH_STATE"
started="$(date +%s)"
out="$(arena-cleanup run --dry-run 2>&1)"
rc=$?
elapsed=$(($(date +%s) - started))
check "dry run returns immediately despite running checks" "$rc" "0"
[ "$elapsed" -le 5 ] && ok "dry run did not actually wait (${elapsed}s)" || bad "dry run waited ${elapsed}s"

echo
echo "=== 8. failure handling ==="
git checkout -q main
out="$(cd "$T/origin.git" && arena-cleanup 2>&1)"
rc=$?
check "outside a work tree fails cleanly" "$rc" "1"
cd "$T/work" && git checkout -q --detach HEAD
out="$(arena-cleanup 2>&1)"
rc=$?
check "detached HEAD fails cleanly" "$rc" "1"
echo "$out" | grep -q "detached" && ok "explained detached HEAD" || bad "detached HEAD message"
git checkout -q arena/session-1

echo
echo "=== 9. verbose output ==="
out="$(arena-cleanup doctor -v 2>&1)"
echo "$out" | grep -q '^\$ git' && ok "verbose prints the commands it runs" || bad "verbose mode"
echo "$out" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T.*INFO' && ok "verbose output keeps the log format" || bad "verbose format"
# -v must not cost us the captured output: lots of code parses it
out="$(arena-cleanup strip -n -v 2>&1)"
rc=$?
check "-v still parses what git prints" "$rc" "0"
echo "$out" | grep -q "not inside a git repository" && bad "-v lost the parsed output" || ok "-v kept the parsed output"
echo "$out" | grep -q '^  | ' && ok "-v echoes the output of each command" || bad "-v echoed nothing"

echo
echo "=== 10. GPG signing (real key) ==="
if [ "$GPG_OK" = 1 ]; then
  cd "$T/work"
  git checkout -q main
  git branch -q -D arena/sign 2>/dev/null || true
  git checkout -q -b arena/sign
  git commit -q --allow-empty -m "chore: agent signed work

body" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
  git commit -q --allow-empty -m "chore: human work" \
    --author="other@example.com <other@example.com>" --no-gpg-sign
  out="$(arena-cleanup strip 2>&1)"
  rc=$?
  check "signed strip exit code" "$rc" "0"
  echo "$out" | grep -q "1 signed" && ok "reported 1 signed commit" || {
    bad "signing count"
    echo "$out" | tail -2
  }
  check "claimed commit has a good signature" "$(git log -1 --format='%G?' HEAD~1)" "G"
  check "unclaimed commit left unsigned" "$(git log -1 --format='%G?' HEAD)" "N"
  check "rewritten subject preserved" "$(git log -1 --format='%s' HEAD~1)" "chore: agent signed work"
  arena-cleanup strip --check >/dev/null 2>&1
  check "re-signed history is idempotent (--check exit 0)" "$?" "0"
  git commit -q --allow-empty -m "chore: unsigned agent work" \
    --author="arena-agent <agent@arena.ai>" --no-gpg-sign
  before="$(git rev-parse HEAD)"
  out="$(GNUPGHOME="$T/gnupg-empty" arena-cleanup strip 2>&1)"
  rc=$?
  check "signing with no secret key fails" "$rc" "1"
  echo "$out" | grep -q "could not sign commit" && ok "explained the signing failure" || bad "signing failure message"
  echo "$out" | grep -q "fix your GPG setup" && ok "pointed at the GPG setup" || bad "no GPG hint"
  check "failed signing left HEAD untouched" "$(git rev-parse HEAD)" "$before"
  [ -f "$(git rev-parse --git-dir)/REBASE_HEAD" ] && bad "left rebase state behind" || ok "no rebase state left behind"
  git checkout -q arena/session-1
else
  echo "  SKIP  no gpg key available"
fi

echo
echo "=== 11. doctor ==="
out="$(arena-cleanup doctor 2>&1)"
rc=$?
check "doctor exit code" "$rc" "0"
echo "$out" | grep -q "git:" && ok "doctor reported git" || bad "doctor git check"
echo "$out" | grep -q "gh authenticated" && ok "doctor reported gh auth" || bad "doctor gh check"

echo
echo "=== 12. force-push lease protects the default branch ==="
REAL_GIT="$(command -v git)"
cat >"$T/bin/git" <<EOF
#!/usr/bin/env bash
# sabotage: move origin/main after the tool's fetch, just before its push
if [ "\$1" = "push" ] && [ ! -f "$T/sabotaged" ]; then
  touch "$T/sabotaged"
  SAB="\$("$REAL_GIT" -C "$T/origin.git" rev-parse refs/heads/arena/session-1)"
  "$REAL_GIT" -C "$T/origin.git" update-ref refs/heads/main "\$SAB"
  echo "\$SAB" > "$T/sabotaged-sha"
fi
exec "$REAL_GIT" "\$@"
EOF
chmod +x "$T/bin/git"
cd "$T/work"
git checkout -q main
git update-ref refs/heads/main "$(git rev-parse origin/main)"
git checkout -q arena/session-1
git commit -q --allow-empty -m "chore: agent work for lease test" \
  --author="arena-agent <agent@arena.ai>" --no-gpg-sign
echo "open" >"$FAKE_GH_STATE"
out="$(arena-cleanup -K 2>&1)"
rc=$?
check "run refuses when the target ref moved" "$rc" "1"
check "origin/main still holds the sabotaged commit" \
  "$(git -C "$T/origin.git" rev-parse refs/heads/main)" "$(cat "$T/sabotaged-sha")"
[ "$(git -C "$T/origin.git" rev-parse refs/heads/main)" != "$(git rev-parse HEAD)" ] &&
  ok "our tip did NOT overwrite origin/main" || bad "origin/main was clobbered"
echo "$out" | grep -q "stale info" && ok "git reported stale lease info" || {
  bad "lease rejection message"
  echo "$out" | tail -5
}
check "local history still rewritten" "$(git log -1 --format=%ae)" "60245796+nemoe7@users.noreply.github.com"
rm -f "$T/bin/git" # restore the real git for any later sections

echo
echo "=== 13. upstream diverged with different content ==="
"$REAL_GIT" clone -q "$T/origin.git" "$T/sibling"
cd "$T/sibling" && "$REAL_GIT" checkout -q arena/session-1
echo "upstream only" >upstream-only.txt
"$REAL_GIT" add upstream-only.txt
"$REAL_GIT" commit -q -m "feat: work pushed straight to the arena branch" --no-gpg-sign
"$REAL_GIT" push -q origin arena/session-1
cd "$T/work" && git checkout -q main && git fetch -q origin
MAIN_BEFORE="$(git rev-parse origin/main)"
echo "open" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"
LOCAL_ARENA_BEFORE="$(git rev-parse arena/session-1)"

# no terminal -> cannot ask -> cancels rather than guessing, and puts the repo back
out="$(arena-cleanup run -K 2>&1)"
rc=$?
check "no terminal: cancels instead of guessing" "$rc" "1"
echo "$out" | grep -q "have diverged" && ok "detected the divergence" || {
  bad "no divergence warning"
  echo "$out" | grep -i "diverg" | sed 's/^/      | /'
}
echo "$out" | grep -q "only on origin/arena/session-1" && ok "said what differs, and where" || bad "differs not explained"
echo "$out" | grep -q "cancelled:" && ok "said it was cancelled" || bad "no cancel notice"
check "returned to the branch the run started on" "$(git branch --show-current)" "main"
check "origin/main untouched" "$(git rev-parse origin/main)" "$MAIN_BEFORE"
check "local arena branch did not move" "$(git rev-parse arena/session-1)" "$LOCAL_ARENA_BEFORE"
echo "$out" | grep -q "hint:" && bad "git's raw advice leaked into the log" || ok "no raw git advice in the log"

# -x local: keep local history, no question
out="$(arena-cleanup run -K -x local 2>&1)"
rc=$?
check "-x local completes" "$rc" "0"
echo "$out" | grep -q -- "--on-divergence=local: keeping local history" && ok "-x local kept local history" || {
  bad "-x local did not keep local"
  echo "$out" | grep -i "diverg" | sed 's/^/      | /'
}
[ "$(git rev-parse origin/main)" != "$MAIN_BEFORE" ] && ok "-x local published local history" || bad "-x local published nothing"

# -x remote: overwrite the (diverged) local copy with the remote, then publish
cd "$T/work" && git checkout -q arena/session-1
echo "local-only edit" >local-only.txt && git add local-only.txt
git commit -q -m "feat: local-only work that -x remote discards" --no-gpg-sign
git checkout -q main
out="$(arena-cleanup run -K -x remote -f 2>&1)"
rc=$?
check "-x remote completes" "$rc" "0"
if [ "$rc" != 0 ]; then echo "$out" | sed 's/^/      | /'; fi
echo "$out" | grep -q "replacing local arena/session-1 with origin/arena/session-1" && ok "-x remote replaced local with remote" || {
  bad "-x remote did not replace"
  echo "$out" | grep -iE "diverg|replac" | sed 's/^/      | /'
}
check "the remote copy is what got published" \
  "$(git diff --quiet origin/arena/session-1 origin/main -- && echo same || echo differs)" "same"
check "the remote-only file reached main" "$(git cat-file -e origin/main:upstream-only.txt 2>/dev/null && echo yes || echo no)" "yes"
check "the discarded local-only file did not" "$(git cat-file -e origin/main:local-only.txt 2>/dev/null && echo yes || echo no)" "no"

echo
echo "=== 14. --branch main (clean the default branch in place) ==="
git init -q --bare -b main "$T/mode.git"
git clone -q "$T/mode.git" "$T/mode-work" 2>/dev/null
cd "$T/mode-work"
[ "$GPG_OK" = 1 ] && git config user.signingkey "$KEYID" && git config gpg.program gpg
git commit -q --allow-empty -m "chore: init" --author="other@example.com <other@example.com>" --no-gpg-sign
git commit -q --allow-empty -m "feat: agent wrote straight to main

a body the agent wrote" --author="arena-ai-coding-agent[bot] <bot@arena.ai>" --no-gpg-sign
git push -q -u origin main
DIRTY_TIP="$(git rev-parse HEAD)"
echo "none" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"

out="$(arena-cleanup --branch main --dry-run 2>&1)"
rc=$?
check "--branch main dry run exit code" "$rc" "0"
echo "$out" | grep -q "cleaning main directly" && ok "said it is cleaning main directly" || bad "no --branch notice"
echo "$out" | grep -q "locating origin/arena" && bad "still did arena discovery" || ok "skipped arena discovery"
check "--branch main dry run moved nothing" "$(git rev-parse HEAD)" "$DIRTY_TIP"
check "--branch main dry run stayed on main" "$(git branch --show-current)" "main"

out="$(arena-cleanup --branch main 2>&1)"
rc=$?
check "--branch main rewrites in place" "$rc" "0"
check "agent commit on main was claimed" "$(git log -1 --format=%ae)" "$ME_EMAIL"
check "message trimmed" "$(git log -1 --format=%B)" "feat: agent wrote straight to main"
check "local main == origin/main after push" "$(git rev-parse main)" "$(git rev-parse origin/main)"
check "still on main afterwards" "$(git branch --show-current)" "main"
[ "$(git rev-parse HEAD)" != "$DIRTY_TIP" ] && ok "main history actually changed" || bad "main history unchanged"

out="$(arena-cleanup --branch main 2>&1)"
rc=$?
check "second --branch main run is a no-op" "$rc" "0"
echo "$out" | grep -q "nothing to push" && ok "reported nothing to push" || {
  bad "no-op reporting"
  echo "$out" | tail -3
}
echo "$out" | grep -q "force-pushing" && bad "pushed again for no reason" || ok "no pointless force-push"

out="$(arena-cleanup --branch no-such-branch 2>&1)"
rc=$?
check "unknown --branch fails cleanly" "$rc" "1"
echo "$out" | grep -q "branch not found: no-such-branch" && ok "named the missing branch" || bad "missing branch message"

echo
echo "=== 15. --delete-branch (drop the arena branch once published) ==="
git checkout -q -b arena/mode-test
git commit -q --allow-empty -m "chore: agent work for deletion

body" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/mode-test
git checkout -q main
echo "open" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"

out="$(arena-cleanup --delete-branch --dry-run 2>&1)"
rc=$?
check "--delete-branch dry run exit code" "$rc" "0"
echo "$out" | grep -q "would delete origin/arena/mode-test" && ok "announced the remote deletion" || {
  bad "no remote deletion notice"
  echo "$out" | tail -4
}
echo "$out" | grep -q "would delete local branch arena/mode-test" && ok "announced the local deletion" || bad "no local deletion notice"
git show-ref --verify --quiet refs/heads/arena/mode-test && ok "dry run kept the local branch" || bad "dry run deleted the local branch"

out="$(arena-cleanup --delete-branch 2>&1)"
rc=$?
check "--delete-branch run exit code" "$rc" "0"
echo "$out" | grep -q "deleted origin/arena/mode-test" && ok "deleted the remote branch" || {
  bad "remote branch not deleted"
  echo "$out" | tail -4
}
echo "$out" | grep -q "deleted local branch arena/mode-test" && ok "deleted the local branch" || bad "local branch not deleted"
git show-ref --verify --quiet refs/heads/arena/mode-test && bad "local branch survived" || ok "local branch is gone"
[ "$(git ls-remote --heads origin 2>/dev/null | grep -c 'arena/mode-test' || true)" = "0" ] && ok "origin has no arena/mode-test" || bad "remote branch survived"

# already-published branch + --delete-branch must still tidy up
git checkout -q -b arena/already-there main
git push -q -u origin arena/already-there
git checkout -q main
out="$(arena-cleanup --delete-branch 2>&1)"
rc=$?
check "already-published branch still gets deleted" "$rc" "0"
[ "$(git ls-remote --heads origin 2>/dev/null | grep -c 'arena/already-there' || true)" = "0" ] && ok "cleaned up the already-published branch" || bad "already-published branch left behind"

# safety: the default branch is never a deletion candidate
out="$(arena-cleanup --branch main --delete-branch 2>&1)"
rc=$?
check "--branch main --delete-branch exits 0" "$rc" "0"
echo "$out" | grep -qE "deleted (origin/|local branch )main" && bad "tried to delete main" || ok "never attempted to delete main"
echo "$out" | grep -q "nothing to delete" && bad "noisy refusal for a flag that cannot apply" || ok "quietly ignores deletion for main"
git show-ref --verify --quiet refs/heads/main && ok "local main intact" || bad "local main deleted"
[ "$(git ls-remote --heads origin 2>/dev/null | grep -c 'refs/heads/main' || true)" = "1" ] && ok "origin main intact" || bad "origin main deleted"

# running from inside the arena branch: switch off it so the delete can finish
git checkout -q -b arena/still-on-it main
git push -q -u origin arena/still-on-it
out="$(arena-cleanup --delete-branch 2>&1)"
rc=$?
check "run from inside the arena branch exits 0" "$rc" "0"
echo "$out" | grep -q "switching to main first, so arena/still-on-it can be deleted" && ok "stepped off the branch before deleting it" || {
  bad "did not step off the branch"
  echo "$out" | tail -4
}
echo "$out" | grep -q "deleted origin/arena/still-on-it" && ok "deleted its remote branch" || bad "remote branch not deleted"
git show-ref --verify --quiet refs/heads/arena/still-on-it && bad "local branch survived" || ok "deleted the branch we started on"
check "ended on the default branch" "$(git branch --show-current)" "main"
cd "$T/work"
git checkout -q arena/session-1 2>/dev/null || true

echo
echo "=== 16. help screen + shorthands ==="
out="$(arena-cleanup --help 2>&1)"
for flag in --branch --delete-branch --skip-pr-check --check-timeout \
  --check-interval --dry-run --verbose --check --version \
  --path --keep-empty --no-tags; do
  echo "$out" | grep -q -- "$flag" && ok "help lists $flag" || bad "help hides $flag"
done
for short in " -b " " -d " " -k " " -t " " -i " " -n " " -v " " -c " " -V " \
  " -p " " -E " " -T "; do
  echo "$out" | grep -q -- "$(echo "$short" | sed 's/^ //;s/ $//')," && ok "help shows${short%,}" || bad "help hides${short%,}"
done
echo "$out" | grep -q "arena-cleanup -b main" && ok "help shows worked examples" || bad "no examples in help"
echo "$out" | grep -q "the local arena branch is deleted once a run finishes" && ok "help documents the default branch cleanup" || bad "branch cleanup undocumented"
check "help exits 0" "$?" "0"

# shorthands must behave exactly like their long forms
cd "$T/work" && git checkout -q main
out="$(arena-cleanup -n 2>&1)"
rc=$?
check "-n (dry run) exit code" "$rc" "0"
echo "$out" | grep -q "dry run:" && ok "-n is dry-run" || bad "-n not honored"

out="$(arena-cleanup -b main -n 2>&1)"
rc=$?
check "-b/-n together exit code" "$rc" "0"
echo "$out" | grep -q "cleaning main directly" && ok "-b selects the branch" || bad "-b not honored"

out="$(arena-cleanup -V 2>&1)"
rc=$?
check "-V exits 0" "$rc" "0"
echo "$out" | grep -qE "arena-cleanup [0-9]+\.[0-9]+\.[0-9]+" && ok "-V prints the version" || bad "-V output"
check "-V prints the pyproject version" "${out##* }" "$PROJECT_VERSION"

out="$(arena-cleanup doctor -v 2>&1)" # -v on a non-run command
echo "$out" | grep -q '^\$ ' && ok "-v works with doctor" || bad "-v with doctor"

out="$(arena-cleanup strip -c 2>&1)"
rc=$?
[ "$rc" = "0" ] || [ "$rc" = "7" ] && ok "strip -c returns 0/7 (got $rc)" || bad "strip -c exit code ($rc)"

# flags that belong to one command are rejected on another, with a clear message
out="$(arena-cleanup strip -b main 2>&1)"
rc=$?
check "strip -b is a usage error" "$rc" "2"
echo "$out" | grep -q "only applies to .run." && ok "explained the misplaced run flag" || {
  bad "unclear misuse message"
  echo "$out" | tail -2
}
out="$(arena-cleanup doctor -c 2>&1)"
rc=$?
check "doctor -c is a usage error" "$rc" "2"
echo "$out" | grep -q "only applies to .strip." && ok "explained the misplaced strip flag" || bad "unclear strip flag message"
out="$(arena-cleanup -d 2>&1)" # -d is run-only, and run is the default
echo "$out" | grep -q "only applies" && bad "-d rejected on the default command" || ok "-d accepted on the default (run) command"

echo
echo "=== 17. blacklist claims a commit authored by 'arena' ==="
cd "$T/work" && git checkout -q main
git checkout -q -b arena/bl-check main
git commit -q --allow-empty -m "feat: bare arena author

body to trim" --author="arena <arena@example.com>" --no-gpg-sign
git commit -q --allow-empty -m "chore: human commit" --author="someone <someone@example.com>" --no-gpg-sign
out="$(arena-cleanup strip 2>&1)"
rc=$?
check "strip exit code" "$rc" "0"
check "bare 'arena' author was claimed" "$(git log -1 --format='%ae' HEAD~1)" "$ME_EMAIL"
check "its message was trimmed" "$(git log -1 --format=%B HEAD~1)" "feat: bare arena author"
check "unrelated author untouched" "$(git log -1 --format='%ae' HEAD)" "someone@example.com"
git checkout -q main
git branch -q -D arena/bl-check

echo
echo "=== 18. superseded check runs (re-run workflows) ==="
cd "$T/work" && git checkout -q -b arena/superseded main
git commit -q --allow-empty -m "chore: agent work for check dedupe" \
  --author="arena-agent <agent@arena.ai>" --no-gpg-sign
echo "superseded" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count" "$FAKE_GH_STATE.count"
out="$(arena-cleanup run -K --dry-run 2>&1)"
rc=$?
check "green-but-cancelled rollup proceeds" "$rc" "0"
echo "$out" | grep -q 'check "build": SUCCESS' && ok "took the current run's SUCCESS" || {
  bad "did not resolve the duplicate"
  echo "$out" | grep check | sed 's/^/      | /'
}
echo "$out" | grep -q "ignored superseded CANCELLED" && ok "named the stale run it ignored" || bad "did not explain the ignored run"
echo "$out" | grep -q "check.*CANCELLED$" && bad "still aborting on the stale cancelled run" || ok "no longer reports cancelled"

echo "superseded-failing" >"$FAKE_GH_STATE"
out="$(arena-cleanup run -K --dry-run 2>&1)"
rc=$?
check "a real failure still blocks, with a stale cancelled sibling" "$rc" "1"
echo "$out" | grep -q 'check "test": FAILURE' && ok "reported the genuine failure" || bad "missed the failing check"

echo
echo "=== 19. local arena branch is deleted once the run is done ==="
cd "$T/work" && git checkout -q main
git checkout -q -b arena/cleanup-default main
git commit -q --allow-empty -m "chore: agent work to publish

body" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/cleanup-default
git checkout -q main
only_arena arena/cleanup-default
echo "open" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"
out="$(arena-cleanup 2>&1)"
rc=$?
check "run exit code" "$rc" "0"
if [ "$rc" != 0 ]; then echo "$out" | sed 's/^/      | /'; fi
echo "$out" | grep -q "deleted local branch arena/cleanup-default" && ok "deleted the local copy" || {
  bad "local branch not deleted"
  echo "$out" | tail -4
}
git show-ref --verify --quiet refs/heads/arena/cleanup-default && bad "local branch survived" || ok "local branch is gone"
[ "$(git ls-remote --heads origin 2>/dev/null | grep -c 'arena/cleanup-default' || true)" = "1" ] && ok "origin still has the branch (survives in upstream)" || bad "remote branch was removed without -d"
check "ended on the default branch" "$(git branch --show-current)" "main"
git push -q origin --delete arena/cleanup-default
git fetch -q --prune origin

# -K keeps it
git checkout -q -b arena/keepme main
git commit -q --allow-empty -m "chore: another agent commit

body" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/keepme
git checkout -q main
only_arena arena/keepme
out="$(arena-cleanup -K 2>&1)"
rc=$?
check "-K run exit code" "$rc" "0"
git show-ref --verify --quiet refs/heads/arena/keepme && ok "-K kept the local branch" || bad "-K did not keep the branch"
[ "$(git ls-remote --heads origin 2>/dev/null | grep -c 'arena/keepme' || true)" = "1" ] && ok "-K left origin alone" || bad "-K touched origin"
git branch -q -D arena/keepme
git push -q origin --delete arena/keepme
git fetch -q --prune origin

# -d removes both, local copy included
git checkout -q -b arena/dropboth main
git commit -q --allow-empty -m "chore: agent work to drop

body" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/dropboth
git checkout -q main
only_arena arena/dropboth
out="$(arena-cleanup -d 2>&1)"
rc=$?
check "-d run exit code" "$rc" "0"
git show-ref --verify --quiet refs/heads/arena/dropboth && bad "local copy survived -d" || ok "-d deleted the local branch"
[ "$(git ls-remote --heads origin 2>/dev/null | grep -c 'arena/dropboth' || true)" = "0" ] && ok "-d deleted the remote branch" || bad "-d left the remote branch"

echo
echo "=== 20. uncommitted changes ==="
cd "$T/work" && git checkout -q main
git fetch -q --prune origin && git reset -q --hard origin/main
# a file that differs between main and the arena branch, edited but uncommitted
echo "main version" >conflict.txt && git add conflict.txt && git commit -q -m "chore: add conflict.txt" --no-gpg-sign
git push -q origin main
git checkout -q -b arena/conflict main
echo "branch version" >conflict.txt && git commit -q -am "feat: branch edits conflict.txt" --no-gpg-sign
git push -q -u origin arena/conflict
git checkout -q main
only_arena arena/conflict
echo "uncommitted local edit" >conflict.txt # would be lost by the final reset

out="$(arena-cleanup -K 2>&1)"
rc=$?
check "dirty tree + branch switch is refused" "$rc" "1"
echo "$out" | grep -q "uncommitted change(s) and this run switches branches" && ok "explained why it refused" || {
  bad "no refusal"
  echo "$out" | tail -5
}
echo "$out" | grep -q "M conflict.txt" && ok "listed the offending file" || bad "did not name the file"
echo "$out" | grep -q "git stash" && ok "suggested stashing" || bad "no way out suggested"
echo "$out" | grep -q -- "-f to continue" && ok "mentioned the override" || bad "no override mentioned"
check "refused before switching" "$(git branch --show-current)" "main"
git show-ref --verify --quiet refs/heads/arena/conflict && ok "no cleanup ran either" || bad "run did partial work before aborting"

# -f forces past the guard, and then git's own error is what the log shows
out="$(arena-cleanup -K -f 2>&1)"
rc=$?
check "-f proceeds past the guard" "$rc" "1"
echo "$out" | tail -12 | sed 's/^/      | /'
if true; then
  echo "$out" | grep -q -- "--force set; continuing" && ok "said it is forcing" || bad "no force notice"
  echo "$out" | grep -q "failed to switch to arena/conflict" && ok "named the failing step" || bad "step not named"
  echo "$out" | grep -q "  | " && ok "dumped the command's real output" || {
    bad "raw output not shown"
    echo "$out" | tail -8
  }
  echo "$out" | grep -qiE "would be overwritten|local changes" && ok "included git's own error text" || bad "git's error text missing"
  echo "$out" | grep -q "git switch arena/conflict" && ok "showed the exact command that failed" || bad "command not shown"
fi

# cleaning the default branch in place moves nothing, so it is allowed
git checkout -q -- conflict.txt
git clean -qfd
echo "in-place edit" >>conflict.txt
out="$(arena-cleanup -b main 2>&1)"
rc=$?
check "-b main with a dirty tree still runs" "$rc" "0"
if [ "$rc" != 0 ]; then echo "$out" | tail -8 | sed 's/^/      | /'; fi
echo "$out" | grep -q "nothing here moves the working tree" && ok "said the changes are left alone" || {
  bad "missing note"
  echo "$out" | tail -4
}
check "the uncommitted edit survived" "$(tail -1 conflict.txt)" "in-place edit"
git checkout -q -- conflict.txt
git push -q origin --delete arena/conflict 2>/dev/null
git fetch -q --prune origin

echo "=== 21. main was cleaned up, local arena branch is the pre-cleanup copy ==="
cd "$T/work" && git checkout -q main
# make sure exactly one origin/arena/* branch exists, so branch discovery is unambiguous
for b in $(git ls-remote --heads origin 2>/dev/null | awk '{print $2}' | sed 's|refs/heads/||' | grep '^arena/'); do
  git push -q origin --delete "$b"
done
git fetch -q --prune origin
git checkout -q -b arena/stale-copy main
git commit -q --allow-empty -m "feat: work that gets published

body" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/stale-copy
# publish a cleaned version of it to main ...
git checkout -q main
git merge -q --ff-only arena/stale-copy
arena-cleanup strip >/dev/null 2>&1 # clean it locally
git push -q --force origin main     # ...and publish that to main
# ...then put the local arena branch back to its pre-cleanup (upstream) state
git checkout -q arena/stale-copy
git reset -q --hard origin/arena/stale-copy
git checkout -q main
MAIN_TIP="$(git rev-parse origin/main)"
out="$(arena-cleanup -K 2>&1)"
rc=$?
check "run exits 0" "$rc" "0"
echo "$out" | grep -q "identical content but different history" && ok "detected the pre-cleanup copy" || {
  bad "not detected"
  echo "$out" | grep -iE "content|history|push" | sed 's/^/      | /'
}
echo "$out" | grep -q "already carries a cleaned-up version" && ok "said why nothing would happen" || bad "no explanation"
check "origin/main was NOT rewritten again" "$(git rev-parse origin/main)" "$MAIN_TIP"
echo "$out" | grep -q "force-push" && bad "force-pushed anyway" || ok "did not force-push"
git branch -q -D arena/stale-copy 2>/dev/null

echo
echo "=== 22. multiple origin/arena/* branches ==="
cd "$T/work" && git checkout -q main && git reset -q --hard origin/main && git fetch -q --prune origin
only_arena "" # start from a clean slate of remote arena branches
# two leftover arena branches
git checkout -q -b arena/multi-a main
git commit -q --allow-empty -m "chore: work on multi-a" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/multi-a
git checkout -q main
git checkout -q -b arena/multi-b main
git commit -q --allow-empty -m "chore: work on multi-b" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/multi-b
git checkout -q main
echo "open" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"

out="$(arena-cleanup 2>&1)"
rc=$?
check "no terminal: refuses rather than picking" "$rc" "1"
echo "$out" | grep -q "2 origin/arena/\* branches found" && ok "counted them" || bad "did not count the branches"
echo "$out" | grep -q -- "-b <branch>" && ok "suggested -b for non-interactive use" || bad "no -b hint"
check "nothing was touched" "$(git branch --show-current)" "main"
[ "$(git ls-remote --heads origin | grep -c 'arena/multi' || true)" = "2" ] && ok "both branches left alone" || bad "a branch went missing"

# with a terminal: it lists them and waits for an answer
out="$(printf '2\n' | script -qec "arena-cleanup" /dev/null 2>&1)"
rc=$?
check "interactive pick succeeds" "$rc" "0"
echo "$out" | grep -q "Which one should this run clean?" && ok "asked which branch" || {
  bad "no question asked"
  echo "$out" | tail -8 | sed 's/^/      | /'
}
echo "$out" | grep -q "1) origin/arena/multi-a" && ok "listed the candidates" || bad "candidates not listed"
echo "$out" | grep -q "switching to arena/multi-b" && ok "worked on the chosen branch" || bad "wrong branch chosen"
check "the chosen branch reached main" "$(git log -1 --format=%s origin/main)" "chore: work on multi-b"
[ "$(git ls-remote --heads origin | grep -c 'arena/multi-a' || true)" = "1" ] && ok "the un-chosen branch was left alone" || bad "un-chosen branch was deleted"
git push -q origin --delete arena/multi-a 2>/dev/null
git fetch -q --prune origin

# cancelling at the menu is not destructive
git checkout -q -b arena/multi-c main
git commit -q --allow-empty -m "chore: work on multi-c" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/multi-c
git checkout -q -b arena/multi-d main
git commit -q --allow-empty -m "chore: work on multi-d" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/multi-d
git checkout -q main
TIPS_BEFORE="$(git ls-remote --heads origin | md5sum)"
out="$(printf 'c\n' | script -qec "arena-cleanup" /dev/null 2>&1)"
rc=$?
check "cancelling the menu exits non-zero" "$rc" "1"
echo "$out" | grep -q "cancelled:" && ok "said it was cancelled" || bad "no cancel notice"
check "cancelling changed nothing" "$(git ls-remote --heads origin | md5sum)" "$TIPS_BEFORE"
check "still on the starting branch" "$(git branch --show-current)" "main"
for b in arena/multi-c arena/multi-d; do git push -q origin --delete "$b" 2>/dev/null; done
git fetch -q --prune origin

echo
echo "=== 23. divergence prompt, answered by hand ==="
cd "$T/work" && git checkout -q main
git branch -q -D arena/multi-b 2>/dev/null
only_arena ""
git reset -q --hard origin/main && git fetch -q --prune origin
# local branch: commit A, pushed ...
git checkout -q -b arena/div-prompt main
echo "local version" >shared.txt && git add shared.txt
git commit -q -m "feat: local writes shared.txt" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/div-prompt
# ... remote copy: someone else adds commit B on top ...
cd "$T/sibling" && git fetch -q origin && git checkout -q -B arena/div-prompt origin/arena/div-prompt
echo "remote version" >shared.txt && git add shared.txt
git commit -q -m "feat: remote writes shared.txt" --no-gpg-sign
git push -q origin arena/div-prompt
# ... and local adds its own commit C, so neither side can fast-forward
cd "$T/work" && git fetch -q origin
git checkout -q arena/div-prompt
echo "local only" >local-only.txt && git add local-only.txt
git commit -q -m "feat: local adds local-only.txt" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git checkout -q main
only_arena arena/div-prompt
echo "open" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"
check "diverged as intended (both sides have unique commits)" \
  "$(git rev-list --count origin/arena/div-prompt..arena/div-prompt),$(git rev-list --count arena/div-prompt..origin/arena/div-prompt)" "1,1"

# answer "keep local": local history wins, the remote-only commit is not published
out="$(printf '2\n' | script -qec "arena-cleanup -K -f" /dev/null 2>&1)"
rc=$?
check "answering 'keep local' completes" "$rc" "0"
echo "$out" | grep -q "have diverged" && ok "paused on the divergence" || {
  bad "no divergence detected"
  echo "$out" | tail -6 | sed 's/^/      | /'
}
echo "$out" | grep -q "Replace local history with" && ok "asked before overwriting anything" || bad "no question asked"
echo "$out" | grep -q "keeping local history" && ok "kept local history as asked" || bad "'keep local' ignored"
check "local content was published" "$(git show origin/main:shared.txt)" "local version"
check "the local-only file was published" "$(git cat-file -e origin/main:local-only.txt 2>/dev/null && echo yes || echo no)" "yes"
check "the remote-only change was not published" \
  "$(git cat-file -e origin/main:local-only.txt 2>/dev/null && echo yes || echo no)" "yes"

# answer "overwrite local": local is replaced by the remote copy, and that is published
cd "$T/work" && git checkout -q arena/div-prompt
echo "second local change" >shared.txt && git add shared.txt
git commit -q -m "feat: second local change" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git checkout -q main
out="$(printf '1\n' | script -qec "arena-cleanup -K -f" /dev/null 2>&1)"
rc=$?
check "answering 'overwrite local' completes" "$rc" "0"
echo "$out" | grep -q "replacing local arena/div-prompt with origin/arena/div-prompt" && ok "overwrote local with the remote copy" || {
  bad "did not overwrite"
  echo "$out" | grep -iE "replac|diverg" | sed 's/^/      | /'
}
check "remote content is what got published" "$(git show origin/main:shared.txt)" "remote version"
check "the discarded local-only file is gone from main" \
  "$(git cat-file -e origin/main:local-only.txt 2>/dev/null && echo present || echo gone)" "gone"

# cancel: back to the branch the run started on, nothing published
cd "$T/work" && git checkout -q arena/div-prompt
echo "third local change" >shared.txt && git add shared.txt
git commit -q -m "feat: third local change" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git checkout -q main
MAIN_NOW="$(git rev-parse origin/main)"
out="$(printf 'c\n' | script -qec "arena-cleanup -K" /dev/null 2>&1)"
rc=$?
check "cancelling the prompt exits non-zero" "$rc" "1"
echo "$out" | grep -q "cancelled:" && ok "said it was cancelled" || {
  bad "no cancel notice"
  echo "$out" | tail -5 | sed 's/^/      | /'
}
check "returned to the branch the run started on" "$(git branch --show-current)" "main"
check "nothing was published" "$(git rev-parse origin/main)" "$MAIN_NOW"
check "the local branch was left as it was" \
  "$(git rev-parse arena/div-prompt)" "$(git rev-parse arena/div-prompt)"

git checkout -q main
for b in arena/div-prompt; do git push -q origin --delete "$b" 2>/dev/null; done
git fetch -q --prune origin
git branch -q -D arena/div-prompt 2>/dev/null

echo "=== 24. default branch already absorbed the branch (plus a maintenance commit) ==="
cd "$T/work" && git checkout -q main && only_arena "" && git reset -q --hard origin/main && git fetch -q --prune origin
# a branch with an agent commit, and its work published to main (rewritten)
git checkout -q -b arena/absorbed main
printf 'feat: agent work that gets absorbed\n\nbody\n' >"$T/absorb-msg"
git commit -q --allow-empty -F "$T/absorb-msg" --author="arena-ai-coding-agent[bot] <bot@arena.ai>" --no-gpg-sign
git push -q -u origin arena/absorbed
git checkout -q main
echo "open" >"$FAKE_GH_STATE"
rm -f "$FAKE_GH_STATE.count"
arena-cleanup -K >/dev/null 2>&1 # publish + clean main
ABSORBED_MAIN="$(git rev-parse origin/main)"
echo "  (main now holds the rewritten commit: $(git log -1 --format='%s' origin/main))"
# a maintenance commit made straight on main afterwards
git reset -q --hard origin/main
git commit -q --allow-empty -m "chore: maintenance commit made on main" --no-gpg-sign
git push -q origin main
MAINT_SHA="$(git rev-parse --short HEAD)"
# the local arena branch is still the pre-cleanup copy
git branch -q -f arena/absorbed origin/arena/absorbed
git checkout -q main
git fetch -q --prune origin
MAIN_NOW="$(git rev-parse origin/main)"

out="$(arena-cleanup -K 2>&1)"
rc=$?
check "run exits 0 (nothing to publish)" "$rc" "0"
echo "$out" | grep -q "different content, but every commit this branch adds is already on main" && ok "detected that the work was already absorbed" || {
  bad "absorption not detected"
  echo "$out" | grep -iE "absorb|content|already" | sed 's/^/      | /'
}
echo "$out" | grep -q "origin/main also has 1 commit(s) this branch does not have" && ok "counted the maintenance commit" || bad "maintenance commit not counted"
echo "$out" | grep -q "$MAINT_SHA" && ok "named the commit at risk" || bad "at-risk commit not named"
echo "$out" | grep -q "would replace origin/main and drop those commit(s)" && ok "said what publishing would do" || bad "consequence not stated"
echo "$out" | grep -q -- "arena-cleanup -b main" && ok "suggested cleaning main itself" || bad "no next step suggested"
check "origin/main was left alone" "$(git rev-parse origin/main)" "$MAIN_NOW"
check "main still has the maintenance commit" "$(git merge-base --is-ancestor "$MAINT_SHA" origin/main && echo yes || echo no)" "yes"
echo "$out" | grep -q "force-push" && bad "pushed despite the risk" || ok "did not push"

# -f insists, and that is a documented way to lose the maintenance commit
out="$(arena-cleanup -K -f 2>&1)"
rc=$?
check "-f publishes anyway" "$rc" "0"
echo "$out" | grep -q "origin/main also has 1 commit(s)" && ok "still warned before doing it" || bad "no warning with -f"
check "origin/main was replaced by the branch" "$(git rev-parse origin/main)" "$(git rev-parse arena/absorbed)"
check "the maintenance commit is gone (that is what -f means)" \
  "$(git merge-base --is-ancestor "$MAINT_SHA" origin/main && echo present || echo gone)" "gone"

echo
echo "=== 25. brand-new work + a maintenance commit on main (push guard) ==="
cd "$T/work" && git checkout -q main
git checkout -q -b arena/new-work main
git commit -q --allow-empty -m "chore: new agent work" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
git push -q -u origin arena/new-work
git checkout -q main
only_arena arena/new-work
echo "  (main is behind the branch, plus a commit made after the fork)"
git reset -q --hard origin/main
git commit -q --allow-empty -m "chore: hotfix landed on main meanwhile" --no-gpg-sign
git push -q origin main
git fetch -q --prune origin
MAIN_BEFORE="$(git rev-parse origin/main)"

out="$(arena-cleanup -K 2>&1)"
rc=$?
check "no terminal: refuses to publish over it" "$rc" "1"
echo "$out" | grep -q "this push replaces origin/main" && ok "warned before pushing" || {
  bad "no push warning"
  echo "$out" | grep -iE "push|replace" | sed 's/^/      | /'
}
echo "$out" | grep -q "hotfix landed on main meanwhile" && ok "named the commit that would be dropped" || bad "dropped commit not named"
echo "$out" | grep -q "cancelled before pushing" && ok "cancelled instead of pushing" || bad "not cancelled"
check "origin/main untouched" "$(git rev-parse origin/main)" "$MAIN_BEFORE"

# answered at the terminal: publish anyway
out="$(printf 'y\n' | script -qec "arena-cleanup -K" /dev/null 2>&1)"
rc=$?
check "confirming publishes" "$rc" "0"
echo "$out" | grep -q "confirmed; publishing anyway" && ok "took the confirmation" || {
  bad "confirmation ignored"
  echo "$out" | tail -6 | sed 's/^/      | /'
}
check "origin/main now has the branch work" "$(git rev-parse origin/main)" "$(git rev-parse arena/new-work)"

git checkout -q main && git reset -q --hard origin/main
for b in arena/new-work arena/absorbed; do
  git push -q origin --delete "$b" 2>/dev/null
  git branch -q -D "$b" 2>/dev/null
done
git fetch -q --prune origin

echo
echo "=== 26. -p/--path: remove a directory from history, tags follow ==="
if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "  SKIP  path/tag checks (git-filter-repo is not installed)"
  SKIP=$((SKIP + 1))
else
  cd "$T/work" && git checkout -q main && only_arena "" && git reset -q --hard origin/main && git fetch -q --prune origin
  git checkout -q -b arena/paths main
  mkdir -p site/uploads
  printf 'page\n' >site/index.html
  printf 'secret\n' >site/uploads/secret.bin
  git add -A && git commit -q -m "feat: site and uploads" --author="other-dev <other@example.com>" --no-gpg-sign
  printf 'more secret\n' >>site/uploads/secret.bin
  git add -A && git commit -q -m "chore: touch only uploads" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
  printf 'page two\n' >>site/index.html
  git add -A && git commit -q -m "feat: more site" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
  git tag -a v-site -m "site release" # on the last commit
  git tag tl HEAD~2                   # on the untouched first commit
  BEFORE_SHA="$(git rev-parse HEAD)"
  COMMITS_BEFORE="$(git rev-list --count HEAD)"

  out="$(arena-cleanup strip -n -p site/uploads 2>&1)"
  check "dry run exits 0" "$?" "0"
  echo "$out" | grep -q "would remove site/uploads: 1 file(s) across 2 commit(s)" && ok "dry run counted files and commits" || {
    bad "dry run count"
    echo "$out" | grep -i "would remove" | sed 's/^/      | /'
  }
  check "dry run left HEAD alone" "$(git rev-parse HEAD)" "$BEFORE_SHA"
  check "dry run left the file in place" "$(test -f site/uploads/secret.bin && echo present)" "present"

  out="$(arena-cleanup strip -n -p ./site/uploads/ 2>&1)"
  echo "$out" | grep -q "would remove site/uploads:" && ok "./ and a trailing / are normalized" || {
    bad "path normalization"
    echo "$out" | grep -i "would remove" | sed 's/^/      | /'
  }

  out="$(arena-cleanup doctor 2>&1)"
  echo "$out" | grep -q "git-filter-repo:" && ok "doctor reports git-filter-repo" || bad "doctor silent about git-filter-repo"

  out="$(arena-cleanup strip -p no/such/path 2>&1)"
  check "a path that matches nothing is an error" "$?" "1"
  echo "$out" | grep -q "nothing in this repo's history matches 'no/such/path'" && ok "the error names the path" || bad "unmatched-path error"
  check "typo check changed nothing" "$(git rev-parse HEAD)" "$BEFORE_SHA"

  arena-cleanup strip -c -p site/uploads >/dev/null 2>&1
  check "strip -c -p reports a needed rewrite (exit 7)" "$?" "7"

  out="$(arena-cleanup strip -p site/uploads 2>&1)"
  check "strip -p exits 0" "$?" "0"
  check "removed the file from the tree" "$(git ls-tree -r --name-only HEAD | grep -c '^site/uploads/')" "0"
  check "kept the rest of the tree" "$(git ls-tree -r --name-only HEAD | grep -c '^site/index.html$')" "1"
  check "the uploads-only commit is gone" "$(git log --format=%s | grep -c 'touch only uploads')" "0"
  check "two commits remain (one was pruned)" "$((COMMITS_BEFORE - $(git rev-list --count HEAD)))" "1"
  check "origin remote came back" "$(git remote | tr '\n' ' ')" "origin "
  check "annotated tag is still annotated" "$(git cat-file -t v-site)" "tag"
  check "tag message survived" "$(git tag -l --format='%(contents)' v-site | head -1)" "site release"
  check "tag names a commit the branch still has" "$(git merge-base --is-ancestor v-site HEAD && echo yes)" "yes"
  check "lightweight tag still names its commit" "$(git rev-parse tl)" "$(git rev-parse HEAD~1)"
  echo "$out" | grep -qE "[0-9]+ tag\(s\) now point at the rewritten commits" && ok "re-pointed tags after re-signing" || {
    bad "tag not re-pointed by the sign pass"
    echo "$out" | grep -i "tag" | sed 's/^/      | /'
  }

  # -E keeps a commit that only touched the removed path
  git checkout -q main && git reset -q --hard origin/main
  git checkout -q -b arena/keep-empty main
  mkdir -p tmpdir && printf 'x\n' >tmpdir/x.bin
  git add -A && git commit -q -m "chore: only tmpdir" --author="other-dev <other@example.com>" --no-gpg-sign
  printf 'y\n' >tmpdir/y.bin
  git add -A && git commit -q -m "chore: only tmpdir again" --author="other-dev <other@example.com>" --no-gpg-sign
  KEEP_BEFORE="$(git rev-list --count HEAD)"
  out="$(arena-cleanup strip -p tmpdir -E 2>&1)"
  check "-E exits 0" "$?" "0"
  check "-E kept both now-empty commits" "$(git rev-list --count HEAD)" "$KEEP_BEFORE"
  check "-E still removed the files" "$(git ls-tree -r --name-only HEAD | grep -c '^tmpdir/')" "0"
  git checkout -q main && git branch -q -D arena/keep-empty

  echo
  echo "=== 27. -p with run: publish the cleaned tree, move tags on origin ==="
  cd "$T/work" && git checkout -q main && only_arena "" && git reset -q --hard origin/main && git fetch -q --prune origin
  git checkout -q -b arena/pub main
  mkdir -p dist && printf 'blob\n' >dist/bundle.bin
  git add -A && git commit -q -m "feat: add dist bundle" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
  git tag -a v1 -m "release v1"
  git push -q -u origin arena/pub
  git push -q origin refs/tags/v1
  git checkout -q main
  TAG_BEFORE="$(git -C "$T/origin.git" rev-parse refs/tags/v1)"
  MAIN_BEFORE="$(git rev-parse origin/main)"

  out="$(arena-cleanup -K -k -p dist 2>&1)"
  rc=$?
  check "run -p exits 0 (no push-guard false positive)" "$rc" "0"
  echo "$out" | grep -q "cancelled before pushing" && bad "push guard fired on a pruned commit" || ok "push guard ignored the deliberately pruned commit"
  check "origin/main lost dist/" "$(git -C "$T/origin.git" ls-tree -r --name-only main | grep -c '^dist/')" "0"
  check "origin/main really moved" "$([ "$MAIN_BEFORE" != "$(git rev-parse origin/main)" ] && echo moved)" "moved"
  check "origin still has the tag" "$(git -C "$T/origin.git" rev-parse --verify -q refs/tags/v1 >/dev/null && echo yes)" "yes"
  check "tag is still an annotated tag" "$(git -C "$T/origin.git" cat-file -t refs/tags/v1)" "tag"
  check "tag moved to the rewritten commit" "$([ "$TAG_BEFORE" != "$(git -C "$T/origin.git" rev-parse refs/tags/v1)" ] && echo moved)" "moved"
  check "tag points inside origin/main" "$(git -C "$T/origin.git" merge-base --is-ancestor refs/tags/v1 main && echo yes)" "yes"
  echo "$out" | grep -q "updated 1 tag(s) on origin" && ok "said it updated the tag on origin" || {
    bad "tag update not reported"
    echo "$out" | grep -i "tag" | sed 's/^/      | /'
  }
  git push -q origin --delete arena/pub 2>/dev/null
  git branch -q -D arena/pub 2>/dev/null
  git reset -q --hard origin/main
  git fetch -q --prune origin

  # Isolated repo: the only commit touching the path is already on main, and
  # nothing else needs rewriting - so after the prune HEAD is an ancestor of
  # origin/main again, and the push still has to drop that commit there.
  # Without that, the files stay on origin and the run claims success.
  git init -q --bare -b main "$T/clean-origin.git"
  git clone -q "$T/clean-origin.git" "$T/clean-work"
  (
    cd "$T/clean-work" || exit 1
    printf 'base\n' >base.txt
    git add -A
    git -c user.name=other-dev -c user.email=other@example.com commit -q -m "base"
    git push -q -u origin main
    mkdir -p onlydir && printf 'x\n' >onlydir/x.bin
    git add -A
    git -c user.name=other-dev -c user.email=other@example.com commit -q -m "only a blob"
    git push -q origin main
    git fetch -q
  )
  check "the blob is on origin before the run" "$(git -C "$T/clean-origin.git" ls-tree -r --name-only main | grep -c '^onlydir/')" "1"
  out="$(cd "$T/clean-work" && arena-cleanup -b main -k -p onlydir 2>&1)"
  check "-p publishes when its only commit was pruned" "$?" "0"
  check "origin no longer has the file" "$(git -C "$T/clean-origin.git" ls-tree -r --name-only main | grep -c '^onlydir/')" "0"
  check "origin no longer has the pruned commit" "$(git -C "$T/clean-origin.git" log --format=%s main | grep -c 'only a blob')" "0"

  # --no-tags: publish the branch but leave origin's tag where it is
  git reset -q --hard origin/main
  git checkout -q -b arena/pub2 main
  mkdir -p dist2 && printf 'blob\n' >dist2/b.bin
  git add -A && git commit -q -m "feat: another blob" --author="arena-agent <agent@arena.ai>" --no-gpg-sign
  git tag -a v2 -m "release v2"
  git push -q -u origin arena/pub2
  git push -q origin refs/tags/v2
  git checkout -q main
  TAG2_BEFORE="$(git -C "$T/origin.git" rev-parse refs/tags/v2)"
  out="$(arena-cleanup -K -k -p dist2 -T 2>&1)"
  check "-T run exits 0" "$?" "0"
  echo "$out" | grep -qE -- "--no-tags set: [0-9]+ tag\(s\) still name the old history on origin: .*v2" && ok "named the tag it left behind" || {
    bad "--no-tags warning"
    echo "$out" | grep -i -E "tag" | sed 's/^/      | /'
  }
  echo "$out" | grep -q "the removed content stays reachable through those tags" && ok "spelled out what that means" || bad "--no-tags consequence"
  check "origin tag was left alone" "$(git -C "$T/origin.git" rev-parse refs/tags/v2)" "$TAG2_BEFORE"
  check "the tag now names a dropped commit" "$(git -C "$T/origin.git" merge-base --is-ancestor refs/tags/v2 main && echo present || echo dropped)" "dropped"
  check "the branch was still published" "$(git -C "$T/origin.git" ls-tree -r --name-only main | grep -c '^dist2/')" "0"
  git push -q origin --delete arena/pub2 2>/dev/null
  git branch -q -D arena/pub2 2>/dev/null
  git checkout -q main && git reset -q --hard origin/main && git fetch -q --prune origin

  echo
  echo "=== 28. tags only move when their history was published ==="
  # two branches on origin, uploads on both: the run publishes main only, so a
  # tag into develop must stay put - a tag pointing at a commit develop does not
  # have would be worse than a tag on old history.
  git init -q --bare -b main "$T/multi-origin.git"
  git clone -q "$T/multi-origin.git" "$T/multi-work"
  (
    cd "$T/multi-work" || exit 1
    mkdir -p uploads && printf 's\n' >uploads/s.bin && printf 'a\n' >a.txt
    git add -A
    git -c user.name=dev -c user.email=d@e.com commit -q -m "A: main + uploads"
    git tag -a tMain -m "on main"
    git checkout -q -b develop
    printf 'd\n' >d.txt && git add -A
    git -c user.name=dev -c user.email=d@e.com commit -q -m "B: develop work"
    git tag -a tDev -m "on develop"
    printf 's2\n' >uploads/s2.bin && git add -A
    git -c user.name=dev -c user.email=d@e.com commit -q -m "C: develop + uploads"
    git push -q origin main develop
    git push -q origin refs/tags/tMain refs/tags/tDev
    git checkout -q main
  )
  DEV_BEFORE="$(git -C "$T/multi-origin.git" rev-parse develop)"
  TDEV_BEFORE="$(git -C "$T/multi-origin.git" rev-parse refs/tags/tDev)"
  TMAIN_BEFORE="$(git -C "$T/multi-origin.git" rev-parse refs/tags/tMain)"

  out="$(cd "$T/multi-work" && arena-cleanup -b main -k -p uploads 2>&1)"
  check "run over two branches exits 0" "$?" "0"
  check "origin/main was cleaned" "$(git -C "$T/multi-origin.git" ls-tree -r --name-only main | grep -c '^uploads/')" "0"
  check "origin/develop was left alone" "$(git -C "$T/multi-origin.git" rev-parse develop)" "$DEV_BEFORE"
  check "the develop tag did not move" "$(git -C "$T/multi-origin.git" rev-parse refs/tags/tDev)" "$TDEV_BEFORE"
  check "the develop tag still names a commit develop has" \
    "$(git -C "$T/multi-origin.git" merge-base --is-ancestor refs/tags/tDev develop && echo yes)" "yes"
  check "the main tag moved" "$([ "$TMAIN_BEFORE" != "$(git -C "$T/multi-origin.git" rev-parse refs/tags/tMain)" ] && echo moved)" "moved"
  check "the main tag names a commit main has" \
    "$(git -C "$T/multi-origin.git" merge-base --is-ancestor refs/tags/tMain main && echo yes)" "yes"
  echo "$out" | grep -q "1 tag(s) not moved on origin" && ok "warned about the tag it left behind" || {
    bad "no warning about the unpublishable tag"
    echo "$out" | grep -i "tag" | sed 's/^/      | /'
  }
  echo "$out" | grep -q "does not publish: tDev" && ok "named that tag" || bad "unnamed left-behind tag"
  echo "$out" | grep -q "1 other branch(es) on origin still contain uploads" && ok "warned that develop still has the files" || {
    bad "stale branch not reported"
    echo "$out" | grep -iE "branch|contain" | sed 's/^/      | /'
  }
  echo "$out" | grep -q "origin/develop" && ok "named the stale branch" || bad "unnamed stale branch"
  echo "$out" | grep -q -- "-b <branch> -p <path>" && ok "said how to clean it" || bad "no next step for the stale branch"
fi

echo
echo "=== 29. web UI: repo store, one-click jobs, signing ==="
cd "$T/work" && git checkout -q main && only_arena "" && git reset -q --hard origin/main && git fetch -q --prune origin
UI_PORT="$(python3 -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()')"
UIDATA="$T/uidata"
UI_LOG="$T/ui.log"

start_ui() {
  python3 "$HERE/ui/server.py" --data "$UIDATA" --host 127.0.0.1 --port "$UI_PORT" >>"$UI_LOG" 2>&1 &
  UI_PID=$!
  for _ in $(seq 1 60); do
    curl -fsS "http://127.0.0.1:$UI_PORT/api/env" >/dev/null 2>&1 && return 0
    sleep 0.25
  done
  return 1
}
stop_ui() {
  kill "$UI_PID" 2>/dev/null
  wait "$UI_PID" 2>/dev/null
}

# jq replacement: read a JSON document and print one expression against it
q() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1]))' "$1"; }
API="http://127.0.0.1:$UI_PORT"

start_ui || bad "the UI did not start"
ok "the UI starts and answers /api/env"

env_json="$(curl -fsS "$API/api/env")"
check "it reports the UI version" "$(echo "$env_json" | q 'd["version"]')" "$PROJECT_VERSION"
check "it reports the engine version" "$(echo "$env_json" | q 'd["tool"]')" "$PROJECT_VERSION"
echo "$env_json" | q 'd["tools"]["git"]' | grep -q True && ok "it detects git" || bad "git not detected"
echo "$env_json" | q 'd["tools"]["gh"]' | grep -q True && ok "it sees gh signed in" || bad "gh looks signed out to the UI"
echo "$env_json" | q 'd["data"]' | grep -qx "$UIDATA" && ok "it honours --data" || bad "--data ignored"
check "a fresh instance starts with no repos" "$(curl -fsS "$API/api/repos")" "[]"

PAGE="$T/page.html"
curl -fsS "$API/" -o "$PAGE"
page="$(cat "$PAGE")"
# grep the file rather than an echo of it: the page is bigger than a pipe
# buffer, so `echo "$page" | grep -q` dies of SIGPIPE under pipefail as soon as
# grep stops reading, and reports a green match as a failure
grep -q '<title>arena-cleanup</title>' "$PAGE" && ok "it serves the page" || bad "page missing"
grep -qE '(src|href)="https?://' "$PAGE" && bad "page loads remote assets" || ok "page is self-contained (no CDN)"
grep -q 'color-scheme" content="dark"' "$PAGE" && ok "dark mode is the only theme" || bad "theme not pinned dark"
grep -q '<link[^>]*stylesheet' "$PAGE" && bad "page needs an external stylesheet" || ok "styles are inline"
grep -q 'fonts/inter.woff2' "$PAGE" && ok "the page uses the bundled Inter font" || bad "no bundled font"
font_headers="$(curl -sS -D- -o "$T/font.bin" "$API/fonts/inter.woff2")"
echo "$font_headers" | grep -qi 'content-type: font/woff2' && ok "the font is served as font/woff2" || bad "font content-type"
[ "$(wc -c <"$T/font.bin")" -gt 20000 ] && ok "the font file is real (not a stub)" || bad "font file too small"
grep -q 'id="view-signing"' "$PAGE" && ok "the signing view ships with the page" || bad "no signing view"
grep -q 'id="view-dashboard"' "$PAGE" && ok "the dashboard view ships with the page" || bad "no dashboard view"

# -- add by path --------------------------------------------------------------
add="$(curl -fsS -X POST "$API/api/repos" -H 'Content-Type: application/json' \
  -d "{\"source\":\"$T/work\"}")"
REPO_ID="$(echo "$add" | q 'd["id"]')"
[ -n "$REPO_ID" ] && ok "a local work tree can be added by path" || bad "path add failed"
check "adding the same path twice keeps one entry" "$(echo "$add" | q 'd["id"]')" "$REPO_ID"
curl -fsS -X POST "$API/api/repos" -H 'Content-Type: application/json' \
  -d "{\"source\":\"$T/work\"}" >/dev/null
check "the repo list has one repo" "$(curl -fsS "$API/api/repos" | q 'len(d)')" "1"
echo "$add" | q 'd["status"]["ok"]' | grep -q True && ok "it reads the work tree on add" || {
  bad "status missing on add"
  echo "$add" | head -c 400 | sed 's/^/      | /'
}
echo "$add" | q 'd["status"]["default"]' | grep -qx main && ok "it resolves the default branch" || bad "default branch unknown"
echo "$add" | q 'd["managed"]' | grep -q False && ok "a local path is not managed" || bad "local path marked managed"
check "the registry writes a JSON file" \
  "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$UIDATA/repos.json")" "1"

# -- add by clone URL ---------------------------------------------------------
git clone -q --bare "$T/work" "$T/work.git"
# give the bare repo one arena branch so the clone has something to report
git --git-dir="$T/work.git" update-ref refs/heads/arena/ui-test refs/heads/main
clone="$(curl -fsS -X POST "$API/api/repos" -H 'Content-Type: application/json' \
  -d "{\"source\":\"file://$T/work.git\"}")"
CLONE_ID="$(echo "$clone" | q 'd["id"]')"
CLONE_PATH="$(echo "$clone" | q 'd["path"]')"
echo "$clone" | q 'd["managed"]' | grep -q True && ok "a clone URL is cloned and managed" || bad "URL not managed"
[ -d "$CLONE_PATH/.git" ] && ok "the clone exists under the data dir" || bad "clone missing on disk"
echo "$clone" | q 'd["status"]["default"]' | grep -qx main && ok "the clone resolves its default branch" || bad "clone status"
echo "$clone" | q 'd["status"]["arena"]' | grep -q 'arena/' && ok "the clone reports its arena branches" || bad "no arena branches"
check "the repo list has two repos" "$(curl -fsS "$API/api/repos" | q 'len(d)')" "2"
check "a bad path is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/repos" -H 'Content-Type: application/json' -d '{"source":"/nope/nope"}')" "400"
check "an empty source is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/repos" -H 'Content-Type: application/json' -d '{"source":"  "}')" "400"
check "an unknown repo is a 404" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$API/api/repos/deadbeef1234")" "404"

# -- one click ----------------------------------------------------------------
BEFORE_HEAD="$(git rev-parse HEAD)"
job="$(curl -fsS -X POST "$API/api/repos/$REPO_ID/jobs" -H 'Content-Type: application/json' \
  -d '{"action":"clean","dry_run":true,"branch":"main"}')"
JOB_ID="$(echo "$job" | q 'd["id"]')"
echo "$job" | q '" ".join(d["argv"])' | grep -q -- '--dry-run' && ok "one click builds a dry-run argv" || {
  bad "argv"
  echo "$job" | sed 's/^/      | /'
}
echo "$job" | q '" ".join(d["argv"])' | grep -q -- '--on-divergence' &&
  bad "one click picked a divergence policy on its own" ||
  ok "one click leaves divergence to a human"
for _ in $(seq 1 80); do
  snap="$(curl -fsS "$API/api/jobs/$JOB_ID")"
  echo "$snap" | grep -q '"status": "done"' && break
  sleep 0.25
done
check "the job finishes with exit 0" "$(echo "$snap" | q 'd["exit"]')" "0"
[ "$(echo "$snap" | q 'len(d["lines"])')" -gt 5 ] && ok "the output came back to the page" || bad "no output captured"
echo "$snap" | q 'd["lines"][0]["text"]' | grep -q 'arena-cleanup' && ok "the log is the tool's own output" || bad "log garbled"
check "the dry run left the repo alone" "$(git rev-parse HEAD)" "$BEFORE_HEAD"

timeout 3 curl -sS -N "$API/api/jobs/$JOB_ID/events" >"$T/sse.txt" 2>/dev/null || true
grep -q '^data: ' "$T/sse.txt" && ok "SSE replays the job" || {
  bad "no SSE events"
  head -c 200 "$T/sse.txt" | sed 's/^/      | /'
}

# -- the argv whitelist -------------------------------------------------------
check "an unknown action is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/repos/$REPO_ID/jobs" -H 'Content-Type: application/json' -d '{"action":"rm -rf /"}')" "400"
check "an unknown option is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/repos/$REPO_ID/jobs" -H 'Content-Type: application/json' -d '{"action":"run","nope":1}')" "400"
check "a branch that looks like a flag is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/repos/$REPO_ID/jobs" -H 'Content-Type: application/json' -d '{"action":"run","branch":"--upload-pack=x"}')" "400"
check "a path that looks like a flag is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/repos/$REPO_ID/jobs" -H 'Content-Type: application/json' -d '{"action":"strip","paths":["-x"]}')" "400"
check "a negative timeout is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/repos/$REPO_ID/jobs" -H 'Content-Type: application/json' -d '{"action":"run","timeout":-5}')" "400"
check "a job for an unknown repo is a 404" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/repos/deadbeef1234/jobs" -H 'Content-Type: application/json' -d '{"action":"run"}')" "404"
check "cancelling an unknown job is a 404" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/jobs/deadbeef1234/cancel")" "404"

# -- signing ------------------------------------------------------------------
sign="$(curl -fsS "$API/api/signing")"
echo "$sign" | q 'd["gpg"]' | grep -q True && ok "the signing panel sees gpg" || bad "gpg not detected"
echo "$sign" | q 'type(d["keys"]).__name__' | grep -qx list && ok "it lists secret keys" || bad "keys not a list"
echo "$sign" | q 'type(d["github"]).__name__' | grep -qx dict && ok "it reports what GitHub knows" || bad "no github block"
echo "$sign" | q '"error" in d["github"] and "checked" in d["github"]' | grep -q True &&
  ok "an unreachable GitHub is an error, not a crash" || bad "github block incomplete"
echo "$sign" | q 'd["format"] or "openpgp"' | grep -qx openpgp && ok "it reports the signing format" || bad "format missing"
if [ "$(echo "$sign" | q 'len(d["keys"])')" -gt 0 ]; then
  FPR="$(echo "$sign" | q 'd["keys"][0]["fingerprint"]')"
  pub="$(curl -fsS -X POST "$API/api/signing" -H 'Content-Type: application/json' \
    -d "{\"action\":\"public_key\",\"fingerprint\":\"$FPR\"}")"
  echo "$pub" | q 'd["public_key"]' | grep -q 'BEGIN PGP PUBLIC KEY BLOCK' &&
    ok "the public key can be copied out of the UI" || bad "public key export failed"
  used="$(curl -fsS -X POST "$API/api/signing" -H 'Content-Type: application/json' \
    -d "{\"action\":\"use\",\"fingerprint\":\"$FPR\"}")"
  echo "$used" | q 'd["active"]' | grep -qx "$FPR" && ok "a key can be made active" || bad "key not activated"
else
  echo "  SKIP  no secret key in this environment - key export not exercised"
fi
check "an unknown signing action is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/signing" -H 'Content-Type: application/json' -d '{"action":"nope"}')" "400"
check "a use without a fingerprint is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/signing" -H 'Content-Type: application/json' -d '{"action":"use"}')" "400"

# -- safety and persistence ---------------------------------------------------
check "path traversal is refused" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$API/../../etc/passwd")" "404"
check "an unknown API path is a 404" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$API/api/nope")" "404"

# -- authentication -----------------------------------------------------------
# The fake gh decides "signed in" from a flag file, so both states are testable.
#
# The stub in this suite answers "auth status" with exit 0 and no JSON, which is
# the signed-in shape, so the first assertion is the interesting one in CI and
# the signed-out half is driven by removing the flag.
auth="$(curl -fsS "$API/api/auth")"
echo "$auth" | q 'type(d["gh"]).__name__' | grep -qx dict && ok "the auth endpoint answers" || bad "no auth payload"
echo "$auth" | q '"authenticated" in d["gh"] and "installed" in d["gh"]' | grep -q True &&
  ok "it reports gh installation and sign-in separately" || bad "auth shape incomplete"
echo "$auth" | q '"credential_helpers" in d["git"] and "ssh_keys" in d["git"]' | grep -q True &&
  ok "it reports how git authenticates" || bad "git auth block incomplete"
echo "$auth" | q '"GH_TOKEN" in d["env"]' | grep -q True && ok "it reports token env vars" || bad "env block incomplete"
check "a token that is not a token is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/auth" -H 'Content-Type: application/json' \
    -d '{"action":"token","token":"not a token"}')" "400"
check "an empty token is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/auth" -H 'Content-Type: application/json' \
    -d '{"action":"token","token":""}')" "400"
check "an unknown auth action is a 400" \
  "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/api/auth" -H 'Content-Type: application/json' \
    -d '{"action":"sudo"}')" "400"
gh_ids="$(curl -fsS "$API/api/repos" | q 'sorted(d[0]["status"].keys())')"
echo "$gh_ids" | grep -q "pr_checked" && ok "status says whether checks could be read" || bad "no pr_checked flag"

# the same fake gh can be signed out from the test, which is the state that used
# to be indistinguishable from "these branches have no pull request"
echo out >"$(dirname "$FAKE_GH_STATE")/gh-state.auth" 2>/dev/null || echo out >"$FAKE_GH_STATE.auth"
signed_out="$(curl -fsS -X POST "$API/api/auth" -H 'Content-Type: application/json' -d '{"action":"check"}')"
echo "$signed_out" | q 'd["gh"]["authenticated"]' | grep -q False &&
  ok "it notices a signed-out gh" || bad "sign-out not noticed"
echo "$signed_out" | q 'd["gh"]["error"]' | grep -qi "not logged" &&
  ok "it quotes gh's own complaint" || bad "no reason given"
out_status="$(curl -fsS "$API/api/repos" | q 'd[0]["status"]["pr_checked"]')"
[ "$out_status" = "False" ] && ok "an unchecked repo says so instead of faking no-PR" ||
  bad "pr_checked left true while signed out"
curl -fsS "$API/api/repos" | q 'd[0]["status"]["pr_reason"]' | grep -qi "not signed in" &&
  ok "it says why checks are unavailable" || bad "no pr_reason"
: >"$FAKE_GH_STATE.auth"
signed_in="$(curl -fsS -X POST "$API/api/auth" -H 'Content-Type: application/json' -d '{"action":"check"}')"
echo "$signed_in" | q 'd["gh"]["login"]' | grep -qx "nemoe7" &&
  ok "it reads the account name" || bad "login missing"
echo "$signed_in" | q 'd["gh"]["scopes"]' | grep -q "repo" && ok "it reads token scopes" || bad "scopes missing"

# -- health -------------------------------------------------------------------
# docker's HEALTHCHECK calls this on a 30s interval, so it has to be cheap and
# it has to fail loudly when the registry cannot be read
curl -s -D "$T/healthz.head" -o "$T/healthz.json" "$API/healthz"
grep -q '200' "$T/healthz.head" && ok "/healthz answers 200" || bad "/healthz did not answer 200"
check "/healthz reports ok" "$(q 'd["ok"]' <"$T/healthz.json")" "True"
echo "$(q 'd["version"]' <"$T/healthz.json")" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' &&
  ok "/healthz carries the version" || bad "/healthz has no version"
check "/healthz reports the pyproject version" "$(q 'd["version"]' <"$T/healthz.json")" "$PROJECT_VERSION"
echo "$(q 'type(d["uptime"]).__name__' <"$T/healthz.json")" | grep -qx float &&
  ok "/healthz carries uptime" || bad "/healthz has no uptime"
check "/healthz counts the registered repos" "$(curl -fsS "$API/api/repos" | q 'len(d)')" \
  "$(q 'd["repos"]' <"$T/healthz.json")"
check "/api/health is the same answer" "$(curl -fsS "$API/api/health" | q 'd["ok"]')" "True"
grep -q 'id="start"' "$PAGE" && ok "the desktop view has its own Start button" ||
  bad "no Start button outside the phone tab bar"

# -- what survives a rebuild ---------------------------------------------------
storage="$(curl -fsS "$API/api/storage")"
echo "$storage" | q 'len(d["items"])' | grep -qE '^[6-9]$' && ok "storage lists what to protect" ||
  bad "storage items missing"
echo "$storage" | q 'all("survives" in i and "mount_point" in i for i in d["items"])' | grep -q True &&
  ok "each item says whether it is on a mount" || bad "items lack mount info"
echo "$storage" | q 'any(i["label"]=="GitHub token" for i in d["items"])' | grep -q True &&
  ok "the gh token is accounted for" || bad "gh token missing from storage"
echo "$storage" | q 'any(i["label"]=="git config" for i in d["items"])' | grep -q True &&
  ok "git credentials are accounted for" || bad "git config missing from storage"
echo "$storage" | q 'd["tools"]["git-filter-repo"]' | grep -q True &&
  ok "git-filter-repo is reported as an image tool" || bad "git-filter-repo not reported"
echo "$storage" | q '"home_mounted" in d' | grep -q True && ok "it says whether HOME is a volume" ||
  bad "no home_mounted flag"
# existence alone must never be reported as survival: a file in the writable
# layer disappears with the container even though it is here right now
echo "$storage" | q 'all((not i["survives"]) or bool(i["mount_point"]) for i in d["items"])' | grep -q True &&
  ok "a row only claims survival when it is under a mount" || bad "survives is wrong"

# -- job cancellation ----------------------------------------------------------
# Cancel must be distinguishable from a crash: the UI shows "cancelled", not
# "exit -15". Drive the Job object directly so the test cannot race a real run.
cat >"$T/cancel.py" <<'CANCEL_PY'
import sys
import time

sys.path.insert(0, sys.argv[1])
from ui.server import Job

job = Job(["sleep", "30"], "/tmp", {"id": "t", "name": "t"})
job.start()
time.sleep(0.3)
assert job.cancel() is True, "cancel returned False for a running job"
snap = job.snapshot()
for _ in range(50):
  snap = job.snapshot()
  if snap["status"] == "done":
    break
  time.sleep(0.1)
assert snap["status"] == "done", snap["status"]
assert snap["cancelled"] is True, "the cancelled flag was not set"
assert snap["exit"] != 0, "a cancelled job cannot exit 0"
CANCEL_PY
python3 "$T/cancel.py" "$HERE" && ok "a cancelled job is marked cancelled, not just failed" ||
  bad "cancellation is not distinguishable from a crash"

# -- PWA ----------------------------------------------------------------------
manifest="$(curl -fsS "$API/manifest.webmanifest")"
echo "$manifest" | q 'd["display"]' | grep -qx standalone && ok "the manifest asks for a standalone window" || bad "display mode"
echo "$manifest" | q 'd["start_url"]' | grep -qx "/" && ok "the manifest has a start url" || bad "start_url"
echo "$manifest" | q 'len(d["icons"])' | grep -qE '^[3-9]' && ok "the manifest ships multiple icons" || bad "icons missing"
echo "$manifest" | q 'any(i.get("purpose")=="maskable" for i in d["icons"])' | grep -q True &&
  ok "one icon is maskable (Android adaptive)" || bad "no maskable icon"
check "the manifest is served as JSON" \
  "$(curl -s -o /dev/null -w '%{content_type}' "$API/manifest.webmanifest")" \
  "application/manifest+json; charset=utf-8"
check "the page links the manifest" \
  "$(printf '%s' "$page" | grep -c 'rel="manifest"')" "1"
for icon in icon-192.png icon-512.png apple-touch-icon.png; do
  body="$(curl -fsS "$API/icons/$icon" | head -c 4 | od -An -tx1 | tr -d ' \n')"
  [ "$body" = "89504e47" ] && ok "icons/$icon is a real PNG" || bad "icons/$icon not a PNG"
done
check "the worker is served as JavaScript" \
  "$(curl -s -o /dev/null -w '%{content_type}' "$API/sw.js")" "application/javascript; charset=utf-8"
curl -s -D "$T/sw.head" -o /dev/null "$API/sw.js"
grep -qi 'cache-control: no-store' "$T/sw.head" && ok "the worker is never cached (updates land)" || bad "sw cached"
grep -qi 'service-worker-allowed: /' "$T/sw.head" && ok "the worker may control the whole origin" || bad "scope header"
sw="$(curl -fsS "$API/sw.js")"
echo "$sw" | grep -q 'arena-shell' && ok "the worker caches a named shell" || bad "no shell cache"
echo "$sw" | grep -q 'url.pathname.startsWith("/api/")' && ok "the worker never caches API responses" || bad "worker caches API"
grep -q 'apple-mobile-web-app-capable' "$PAGE" && ok "iOS gets the standalone metas" || bad "no iOS metas"
grep -q 'serviceWorker.register' "$PAGE" && ok "the page registers the worker" || bad "worker not registered"
grep -q 'beforeinstallprompt' "$PAGE" && ok "the page uses the install prompt when offered" || bad "no install prompt"
grep -q 'Add to Home Screen' "$PAGE" && ok "iOS gets written install steps" || bad "no iOS instructions"
echo "$env_json" | q '"secure" in d' | grep -q True && ok "it says whether the origin is a secure context" || bad "no secure flag"

stop_ui
start_ui || bad "the UI did not restart"
check "repos survive a restart" "$(curl -fsS "$API/api/repos" | q 'len(d)')" "2"
echo "$(curl -fsS "$API/api/repos" | q 'd[0]["status"]["ok"]')" | grep -q True &&
  ok "remembered repos are re-read on boot" || bad "status lost after restart"

removed="$(curl -fsS -X POST "$API/api/repos/$CLONE_ID/remove" -H 'Content-Type: application/json' -d '{"delete":true}')"
echo "$removed" | q 'd["removed"]' | grep -qx "$CLONE_ID" && ok "a repo can be forgotten" || bad "remove failed"
check "the list shrinks after a removal" "$(curl -fsS "$API/api/repos" | q 'len(d)')" "1"
[ -d "$CLONE_PATH" ] && bad "the managed clone was left behind" || ok "the managed clone is deleted with --delete"

echo "=== 30. the commit list and the page shell ==="
# The dashboard says how many commits the branch has and which ones; the page
# hides the log behind a click, so the HTML must carry the new card and none of
# the old command strip. Grep the saved page file: a 74 KB page through a pipe
# trips SIGPIPE under pipefail, and the test then fails with the match in hand.
commits="$(curl -fsS "$API/api/repos/$REPO_ID/commits?limit=2")"
echo "$commits" | q 'len(d["commits"])' | grep -qx 2 && ok "the commit list honours limit" || bad "limit ignored"
echo "$commits" | q 'd["total"] >= 2' | grep -q True && ok "it reports the branch total" || bad "no total"
echo "$commits" | q 'all({"sha", "short", "subject", "author", "date", "signed"} <= set(c) for c in d["commits"])' |
  grep -q True && ok "each row carries sha, subject, author, date and signing" || bad "commit shape"
echo "$commits" | q 'len(d["commits"][0]["short"]) >= 7' | grep -q True && ok "the short sha is long enough to paste" || bad "short sha"
echo "$commits" | q 'd["branch"] != ""' | grep -q True && ok "it names the branch it read" || bad "no branch"
check "a zero limit still returns one commit" \
  "$(curl -fsS "$API/api/repos/$REPO_ID/commits?limit=0" | q 'len(d["commits"])')" "1"
check "a huge limit is clamped, not an error" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$API/api/repos/$REPO_ID/commits?limit=100000")" "200"
check "a nonsense limit falls back to the default" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$API/api/repos/$REPO_ID/commits?limit=abc")" "200"
check "the commit list for an unknown repo is a 404" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$API/api/repos/deadbeef1234/commits")" "404"

curl -fsS "$API/" -o "$PAGE"
grep -q 'id="commits"' "$PAGE" && ok "the page has a commit list card" || bad "no commits card"
grep -q 'id="logwrap" hidden' "$PAGE" && ok "the log starts collapsed" || bad "log is not collapsed"
grep -q 'id="phases"' "$PAGE" && ok "the run card is a list of phases" || bad "no phase list"
grep -q 'class="brand" href="#/"' "$PAGE" && ok "the brand links home" || bad "brand is not a link"
grep -q 'id="task-note"' "$PAGE" && ok "the page says what the selected task does" || bad "no task note"
grep -q 'id="start-mobile"' "$PAGE" && ok "the phone tab bar carries the run controls" || bad "no phone start"
if grep -qE 'cmdpreview|id="cmdline"|id="emptystate"|oneclick-mobile' "$PAGE"; then
  bad "the removed command strip is still in the page"
else
  ok "the command strip and its helpers are gone"
fi

# The health endpoint is what compose and the sidecar probe.
check "healthz answers ok" "$(curl -fsS "$API/healthz" | q 'd["ok"]')" "True"

# Every storage row says whether it survives a rebuild and where it is mounted.
storage="$(curl -fsS "$API/api/storage")"
echo "$storage" | q 'all({"survives", "mount_point"} <= set(i) for i in d["items"])' |
  grep -q True && ok "every storage item reports mount status" || bad "storage shape"
echo "$storage" | q 'any(i["mount_point"] for i in d["items"])' |
  grep -q True && ok "a mount point is known for at least one item" || bad "no mount point"

stop_ui
git checkout -q main && git reset -q --hard origin/main

echo "=== 31. compose settings come from .env ==="
# every ${VAR} the compose file substitutes has to be documented, or `up`
# silently runs with an empty name and the engine refuses the first rewrite
missing=""
for name in $(grep -o '\${[A-Z_][A-Z_0-9]*' "$HERE/docker-compose.yml" | sed 's/[{}$]//g' | sort -u); do
  grep -q "^#*[[:space:]]*$name=" "$HERE/.env.example" || missing="$missing $name"
done
check "every compose variable is offered in .env.example" "$missing" ""
for name in GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL TS_AUTHKEY; do
  grep -q "^$name=" "$HERE/.env.example" && ok ".env.example sets $name" || bad ".env.example has no $name"
done
grep -qx '\.env' "$HERE/.gitignore" && ok ".env is git-ignored" || bad ".env is not git-ignored"
grep -q '^\.env\.\*' "$HERE/.gitignore" && ok ".env.* is ignored too (backups stay local)" || bad ".env.* not ignored"
grep -q '^!\.env' "$HERE/.dockerignore" && bad "the build context allows .env in" || ok ".env stays out of the image"
grep -q 'TS_AUTHKEY: \${TS_AUTHKEY' "$HERE/docker-compose.yml" && ok "compose takes the tailscale key from the file" || bad "compose hard-codes TS_AUTHKEY"

echo "=== 32. the sidecar can reach the app ==="
# the sidecar is hostnamed arena-cleanup for the MagicDNS name, so inside it
# `arena-cleanup` is itself: the proxy has to dial a name only the app answers
proxy="$(sed -n 's/.*"Proxy": "http:\/\/\([^:"]*\):.*/\1/p' "$HERE/docker/tailscale-serve.json")"
check "the proxy dials a dedicated name" "$proxy" "arena-app"
grep -qE '^[[:space:]]+- arena-app$' "$HERE/docker-compose.yml" && ok "compose gives the app that alias" || bad "no arena-app alias in compose"
grep -q 'hostname: arena-cleanup' "$HERE/docker-compose.yml" && ok "the node keeps its arena-cleanup name" || bad "the node name was lost"
[ "$proxy" = "arena-cleanup" ] && bad "the proxy dials the sidecar's own hostname" || ok "the proxy does not dial the sidecar's own hostname"

echo
echo "---------------------------------------------"
echo "PASS: $PASS   FAIL: $FAIL"
[ "$SKIP" -eq 0 ] || echo "SKIPPED: $SKIP section(s) - install git-filter-repo to run them"
echo "scratch dir: $T"
[ "$FAIL" -eq 0 ] || exit 1
