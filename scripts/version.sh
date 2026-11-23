#!/usr/bin/env bash
# Tag-based versioning helper (adapted from the scribe repository). Tags are the source of truth:
# vMAJOR.MINOR.PATCH[-PRERELEASE]; other tags (v0.1, v0.2.4RC) are ignored. The version in setup.py
# and the newest section of changelog.md follow the latest release (both written by `Bump version`).
# Versions are ordered by SemVer 2.0 precedence, so 0.3.0-rc.1 < 0.3.0 < 0.3.1.
#
#   scripts/version.sh current            version of this checkout, e.g. 0.3.0 or 0.3.0+3.gabc1234.dirty
#   scripts/version.sh latest-tag         highest release tag in the repository (empty if none)
#   scripts/version.sh nearest-tag        nearest release tag reachable from HEAD (empty if none)
#   scripts/version.sh setup              version in setup.py
#   scripts/version.sh changelog-version  newest released version in changelog.md (empty if none)
#   scripts/version.sh highest            highest of the latest tag, setup.py and changelog.md
#   scripts/version.sh versions           all of the above and whether they agree; exit 1 if not
#   scripts/version.sh next <major|minor|patch> [prerelease]
#                                         next version after `highest`, e.g. `next minor rc.1`
#   scripts/version.sh newer <version>    exit 1 unless <version> is newer than `highest` and untagged
#   scripts/version.sh compare <a> <b>    print -1, 0 or 1 by SemVer precedence
#   scripts/version.sh validate <version> exit 1 unless <version> is MAJOR.MINOR.PATCH[-PRERELEASE]
#   scripts/version.sh set <version>      write <version> into setup.py
#   scripts/version.sh changelog <version> [date]
#                                         turn the Unreleased section of changelog.md into <version>
#   scripts/version.sh notes <version>    print the changelog.md section of <version> (release notes)
#   scripts/version.sh check [tag]        setup.py must match [tag], or not be older than the latest tag
#
# Works with the bash 3.2 that ships with macOS.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SETUP_PY="$ROOT/setup.py"
CHANGELOG="$ROOT/changelog.md"
REPO_URL="https://github.com/savex/tempest-parser"
SEMVER_RE='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$'
# the `version="..."` argument of setup(), on its own line
SETUP_VERSION_RE='^[[:space:]]*version[[:space:]]*=[[:space:]]*["'"'"']'

die() { echo "version.sh: $*" >&2; exit 1; }

validate() {
  [[ $1 =~ $SEMVER_RE ]] || die "not a valid version: '$1' (expected MAJOR.MINOR.PATCH[-PRERELEASE])"
}

# Compare MAJOR.MINOR.PATCH only; prints -1, 0 or 1.
compare_core() {
  local a b i
  IFS=. read -r -a a <<< "${1%%-*}"
  IFS=. read -r -a b <<< "${2%%-*}"
  for i in 0 1 2; do
    if (( a[i] > b[i] )); then echo 1; return; fi
    if (( a[i] < b[i] )); then echo -1; return; fi
  done
  echo 0
}

# Full SemVer 2.0 precedence (build metadata ignored); prints -1, 0 or 1.
compare() {
  local a=${1%%+*} b=${2%%+*} c pa="" pb="" i n p q
  c=$(compare_core "$a" "$b")
  if [[ $c != 0 ]]; then echo "$c"; return; fi
  [[ $a == *-* ]] && pa=${a#*-}
  [[ $b == *-* ]] && pb=${b#*-}
  if [[ -z $pa && -z $pb ]]; then echo 0; return; fi
  if [[ -z $pa ]]; then echo 1; return; fi    # a release is newer than its pre-releases
  if [[ -z $pb ]]; then echo -1; return; fi
  local -a x y
  IFS=. read -r -a x <<< "$pa"
  IFS=. read -r -a y <<< "$pb"
  n=${#x[@]}
  (( ${#y[@]} > n )) && n=${#y[@]}
  for (( i = 0; i < n; i++ )); do
    if (( i >= ${#x[@]} )); then echo -1; return; fi
    if (( i >= ${#y[@]} )); then echo 1; return; fi
    p=${x[i]} q=${y[i]}
    if [[ $p =~ ^[0-9]+$ && $q =~ ^[0-9]+$ ]]; then
      if (( 10#$p > 10#$q )); then echo 1; return; fi
      if (( 10#$p < 10#$q )); then echo -1; return; fi
    elif [[ $p =~ ^[0-9]+$ ]]; then echo -1; return   # numeric identifiers sort first
    elif [[ $q =~ ^[0-9]+$ ]]; then echo 1; return
    elif [[ $p > $q ]]; then echo 1; return
    elif [[ $p < $q ]]; then echo -1; return
    fi
  done
  echo 0
}

# The higher of two versions; an empty argument loses.
max_version() {
  if [[ -z $1 ]]; then echo "$2"; return; fi
  if [[ -z $2 ]]; then echo "$1"; return; fi
  if [[ $(compare "$1" "$2") == -1 ]]; then echo "$2"; else echo "$1"; fi
}

latest_tag() {
  local tag best=""
  while IFS= read -r tag; do
    [[ ${tag#v} =~ $SEMVER_RE ]] || continue
    if [[ -z $best || $(compare "${tag#v}" "${best#v}") == 1 ]]; then best=$tag; fi
  done < <(git -C "$ROOT" tag -l 'v[0-9]*')
  echo "$best"
}

# Nearest release tag reachable from HEAD; tags that aren't SemVer are skipped.
nearest_tag() {
  local tag
  while IFS= read -r tag; do
    [[ ${tag#v} =~ $SEMVER_RE ]] && { echo "$tag"; return; }
  done < <(git -C "$ROOT" tag -l 'v[0-9]*' --merged HEAD --sort=-creatordate 2>/dev/null)
  return 0
}

current() {
  local tag base count sha dirty="" meta=""
  tag=$(nearest_tag)
  sha=$(git -C "$ROOT" rev-parse --short=7 HEAD 2>/dev/null) || { setup_version; return; }
  git -C "$ROOT" diff --quiet HEAD -- 2>/dev/null || dirty=1
  if [[ -n $tag ]]; then
    base=${tag#v}
    count=$(git -C "$ROOT" rev-list --count "$tag..HEAD")
    (( count > 0 )) && meta="$count.g$sha"
  else
    base=$(setup_version)
    meta="g$sha"
  fi
  [[ -n $dirty ]] && meta="${meta:+$meta.}dirty"
  echo "$base${meta:++$meta}"
}

setup_version() {
  [[ -f $SETUP_PY ]] || die "no $SETUP_PY"
  grep -E "$SETUP_VERSION_RE" "$SETUP_PY" | head -1 | sed -E "s/$SETUP_VERSION_RE//; s/[\"'].*$//"
}

changelog_version() {
  [[ -f $CHANGELOG ]] || return 0
  awk '/^## \[/ && !/^## \[Unreleased\]/ { sub(/^## \[/, ""); sub(/\].*$/, ""); print; exit }' "$CHANGELOG"
}

highest() {
  local tag
  tag=$(latest_tag)
  max_version "$(max_version "${tag#v}" "$(setup_version)")" "$(changelog_version)"
}

versions() {
  local tag setup log high ok=1 nearest
  tag=$(latest_tag); setup=$(setup_version); log=$(changelog_version); high=$(highest)
  nearest=$(nearest_tag)
  echo "latest tag:      ${tag:-none}"
  echo "nearest tag:     ${nearest:-none}"
  echo "setup.py:        $setup"
  echo "changelog.md:    ${log:-none}"
  echo "highest:         ${high:-none}"
  if [[ -n $tag && ${tag#v} != "$setup" ]]; then
    echo "out of sync: setup.py $setup is not the latest tag $tag"; ok=""
  fi
  if [[ -n $log && $log != "$setup" ]]; then
    echo "out of sync: changelog.md's newest release $log is not setup.py $setup"; ok=""
  fi
  if [[ -z $tag && -n $high ]]; then
    echo "out of sync: no release tag here, but setup.py / changelog.md say $high (tags not fetched or not pushed?)"; ok=""
  fi
  [[ -n $ok ]] && echo "in sync"
  [[ -n $ok ]]
}

next() {
  local bump=${1:-} pre=${2:-} base major minor patch
  base=$(highest)
  base=${base:-0.0.0}
  IFS=. read -r major minor patch <<< "${base%%-*}"
  # After a pre-release, a bump of the same level finalizes it: 2.0.0-rc.1 + major -> 2.0.0.
  local pre_release=""
  [[ $base == *-* ]] && pre_release=1
  case $bump in
    major)
      [[ -n $pre_release && $minor == 0 && $patch == 0 ]] || { major=$((major + 1)); minor=0; patch=0; } ;;
    minor)
      [[ -n $pre_release && $patch == 0 ]] || { minor=$((minor + 1)); patch=0; } ;;
    patch)
      [[ -n $pre_release ]] || patch=$((patch + 1)) ;;
    *) die "next: expected major, minor or patch" ;;
  esac
  local version="$major.$minor.$patch${pre:+-$pre}"
  validate "$version"
  newer "$version" >/dev/null
  echo "$version"
}

# <version> must be newer than every version we know of, and not tagged yet.
newer() {
  local version=$1 high
  validate "$version"
  if git -C "$ROOT" rev-parse -q --verify "refs/tags/v$version" >/dev/null; then
    die "tag v$version already exists"
  fi
  high=$(highest)
  if [[ -n $high && $(compare "$version" "$high") != 1 ]]; then
    die "$version is not newer than $high (the highest of the latest tag, setup.py and changelog.md); pick a higher version, e.g. with a pre-release label on the next patch"
  fi
  echo "ok: $version is newer than ${high:-nothing}"
}

set_version() {
  local version=$1 tmp
  validate "$version"
  tmp=$(mktemp)
  awk -v v="$version" -v re="$SETUP_VERSION_RE" '
    !done && $0 ~ re {
      match($0, /^[[:space:]]*/); indent = substr($0, 1, RLENGTH)
      comma = ($0 ~ /,[[:space:]]*$/) ? "," : ""
      print indent "version=\"" v "\"" comma; done = 1; next
    }
    { print }
  ' "$SETUP_PY" > "$tmp"
  cat "$tmp" > "$SETUP_PY"
  rm -f "$tmp"
  [[ $(setup_version) == "$version" ]] || die "failed to update $SETUP_PY"
  echo "$version"
}

# Unreleased entries become the <version> section; a fresh, empty Unreleased goes on top and the
# links at the bottom follow.
changelog_release() {
  local version=$1 date=${2:-} tmp
  [[ -n $date ]] || date=$(date -u +%Y-%m-%d)
  validate "$version"
  [[ -f $CHANGELOG ]] || die "no $CHANGELOG"
  grep -q '^## \[Unreleased\]' "$CHANGELOG" || die "changelog.md has no '## [Unreleased]' section"
  if grep -q "^## \[$version\]" "$CHANGELOG"; then die "changelog.md already has a $version section"; fi
  tmp=$(mktemp)
  awk -v v="$version" -v d="$date" -v url="$REPO_URL" '
    /^## \[Unreleased\]/ { print; print ""; print "## [" v "] - " d; next }
    /^\[Unreleased\]: /   { print "[Unreleased]: " url "/compare/v" v "...HEAD"; print "[" v "]: " url "/releases/tag/v" v; linked = 1; next }
    { print }
    END { if (!linked) { print ""; print "[Unreleased]: " url "/compare/v" v "...HEAD"; print "[" v "]: " url "/releases/tag/v" v } }
  ' "$CHANGELOG" > "$tmp"
  cat "$tmp" > "$CHANGELOG"
  rm -f "$tmp"
  [[ $(changelog_version) == "$version" ]] || die "failed to update $CHANGELOG"
  echo "$version"
}

# Body of the <version> section, without its heading; exit 1 if there is none.
notes() {
  local version=$1
  validate "$version"
  [[ -f $CHANGELOG ]] || die "no $CHANGELOG"
  grep -q "^## \[$version\]" "$CHANGELOG" || die "changelog.md has no $version section"
  awk -v v="$version" '
    index($0, "## [" v "]") == 1 { on = 1; next }
    on && (/^## \[/ || /^\[[^]]+\]: /) { exit }
    on { print }
  ' "$CHANGELOG" | sed -e '/./,$!d' | awk '{ lines[NR] = $0 } END { n = NR; while (n > 0 && lines[n] == "") n--; for (i = 1; i <= n; i++) print lines[i] }'
}

check() {
  local setup tag=${1:-}
  setup=$(setup_version)
  validate "$setup"
  if [[ -n $tag ]]; then
    [[ ${tag#v} == "$setup" ]] || die "tag $tag does not match setup.py version $setup"
    echo "ok: $tag matches setup.py"
    return
  fi
  tag=$(latest_tag)
  if [[ -z $tag ]]; then
    echo "ok: no release tag yet, setup.py is $setup"
    return
  fi
  [[ $(compare "$setup" "${tag#v}") != -1 ]] \
    || die "setup.py version $setup is older than latest tag $tag"
  echo "ok: setup.py $setup, latest tag $tag"
}

cmd=${1:-current}
shift || true
case $cmd in
  current)           current ;;
  latest-tag)        latest_tag ;;
  nearest-tag)       nearest_tag ;;
  setup)             setup_version ;;
  changelog-version) changelog_version ;;
  highest)           highest ;;
  versions)          versions ;;
  next)              next "$@" ;;
  newer)             newer "${1:?version required}" ;;
  compare)           validate "${1:?a required}"; validate "${2:?b required}"; compare "$1" "$2" ;;
  validate)          validate "${1:?version required}"; echo "ok" ;;
  set)               set_version "${1:?version required}" ;;
  changelog)         changelog_release "${1:?version required}" "${2:-}" ;;
  notes)             notes "${1:?version required}" ;;
  check)             check "$@" ;;
  *)                 die "unknown command '$cmd' (see header of $0)" ;;
esac
