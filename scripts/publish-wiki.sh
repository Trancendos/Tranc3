#!/usr/bin/env bash
#
# publish-wiki.sh — publish the repo's staged wiki content to the GitHub Wiki.
#
# The canonical wiki source lives in-repo at `wiki-content/` (version-controlled,
# reviewable). The GitHub Wiki is a *separate* git repo (…/<repo>.wiki.git). This
# script mirrors `wiki-content/` into that wiki repo and pushes, so publishing is
# a single command. Requires push access to the wiki repo (the code repo's
# collaborators normally have it; CI needs a token with `repo` scope).
#
# Usage:
#   scripts/publish-wiki.sh                      # uses default remote below
#   WIKI_REMOTE=git@github.com:ORG/REPO.wiki.git scripts/publish-wiki.sh
#   DRY_RUN=1 scripts/publish-wiki.sh            # build the commit, skip push
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_ROOT}/wiki-content"
WIKI_REMOTE="${WIKI_REMOTE:-https://github.com/Trancendos/Tranc3.wiki.git}"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

if [[ ! -d "${SRC}" ]]; then
  echo "error: ${SRC} not found — nothing to publish." >&2
  exit 1
fi

echo "→ Cloning wiki: ${WIKI_REMOTE}"
# Capture git's stderr rather than discarding it: a clone failure can be a
# never-created wiki (legitimate first publish) OR a real error (auth, DNS,
# permissions, bad remote). Silently treating every failure as "empty wiki"
# hides the real cause and only surfaces later as a confusing push failure.
CLONE_LOG="$(mktemp)"
if git clone --quiet "${WIKI_REMOTE}" "${WORKDIR}/wiki" 2>"${CLONE_LOG}"; then
  # Success — an existing-but-empty wiki clones with a warning and no commits;
  # that is fine, the first commit is created below. Echo any git notices.
  [[ -s "${CLONE_LOG}" ]] && cat "${CLONE_LOG}" >&2
elif grep -qiE 'not found|does not exist|not exported|empty repository' "${CLONE_LOG}"; then
  # The wiki repo has not been created yet (first publish). Initialise fresh,
  # but still surface exactly what git reported so an auth/permission problem
  # masquerading as "not found" is not lost.
  echo "  (wiki not yet initialised — creating a fresh repo to push into)"
  echo "  git reported:" >&2; cat "${CLONE_LOG}" >&2
  git init --quiet "${WORKDIR}/wiki"
  git -C "${WORKDIR}/wiki" remote add origin "${WIKI_REMOTE}"
else
  # Unrecognised failure (auth, DNS, permissions, bad remote) — fail loudly.
  echo "error: failed to clone wiki repo (${WIKI_REMOTE}):" >&2
  cat "${CLONE_LOG}" >&2
  rm -f "${CLONE_LOG}"
  exit 1
fi
rm -f "${CLONE_LOG}"

echo "→ Mirroring wiki-content/ into the wiki (preserving structure)"
# Remove previously-published pages so deletions propagate, but keep .git.
find "${WORKDIR}/wiki" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp -r "${SRC}/." "${WORKDIR}/wiki/"

cd "${WORKDIR}/wiki"
git add -A
if git diff --cached --quiet; then
  echo "→ No changes; wiki already up to date."
  exit 0
fi

PAGES="$(find . -name '*.md' -not -path './.git/*' | wc -l | tr -d ' ')"
git -c user.name="Trancendos" -c user.email="victicnor@gmail.com" \
    commit --quiet -m "Publish wiki from repo wiki-content/ (${PAGES} pages)"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "→ DRY_RUN=1 — commit built (${PAGES} pages) but not pushed."
  exit 0
fi

echo "→ Pushing ${PAGES} pages to the wiki…"
BRANCH="$(git symbolic-ref --short HEAD 2>/dev/null || echo master)"
git push origin "HEAD:${BRANCH}"
echo "✓ Wiki published (${PAGES} pages)."
