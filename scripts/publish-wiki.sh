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
if ! git clone --quiet "${WIKI_REMOTE}" "${WORKDIR}/wiki" 2>/dev/null; then
  # A brand-new wiki has no commits yet; init an empty repo to push into.
  echo "  (wiki empty or unclonable — initialising fresh)"
  git init --quiet "${WORKDIR}/wiki"
  git -C "${WORKDIR}/wiki" remote add origin "${WIKI_REMOTE}"
fi

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
