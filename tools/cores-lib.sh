#!/usr/bin/env bash
# Shared by build.sh and build-cores.sh: which version of each emulator core gets built.
#   cores.conf  (repo root)  holds <CORE>_REF=<tag | branch | commit hash>; empty = the latest source (the old behaviour).
#   An environment variable of the same name wins over the file (an explicitly empty one means "latest").
# Needs HERE (the repo root). Source it, then call load_cores_conf.

CORES_CONF="${CORES_CONF:-$HERE/cores.conf}"

# name -> the variable that holds its ref
core_ref_var() {
  case "$1" in
    ngp) echo NGP_REF ;;                      genesis) echo GENESIS_REF ;;            psx|pcsx_rearmed) echo PSX_REF ;;
    dolphin|gc) echo GC_REF ;;                flycast|flycast-sa|flycast-standalone|dc|dcsa) echo DC_REF ;;
    n64|mupen64plus-next) echo N64_REF ;;     saturn|yabasanshiro) echo SATURN_REF ;;
    fake08) echo PICO8_REF ;;                 retro8) echo PICO8_ALT_REF ;;
    stella2014) echo STELLA_REF ;;            atari800) echo ATARI800_REF ;;          prosystem) echo PROSYSTEM_REF ;;
    mame2003_plus|mame2003-plus) echo MAME2003_REF ;;                                 mame) echo MAME_REF ;;
    *) echo "" ;;
  esac
}
CORE_REF_VARS="NGP_REF GENESIS_REF PSX_REF GC_REF DC_REF N64_REF SATURN_REF PICO8_REF PICO8_ALT_REF STELLA_REF ATARI800_REF PROSYSTEM_REF MAME2003_REF MAME_REF"

# Reads KEY=value lines (no code is run). Only the *_REF names above are accepted.
load_cores_conf() {
  local line k v
  [[ -f "$CORES_CONF" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"; line="${line%%#*}"
    [[ "$line" == *=* ]] || continue
    k="${line%%=*}"; v="${line#*=}"
    k="${k//[[:space:]]/}"
    v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"; v="${v#[\"\']}"; v="${v%[\"\']}"
    case " $CORE_REF_VARS " in *" $k "*) ;; *) echo "!! $CORES_CONF: unknown setting '$k' ignored" >&2; continue ;; esac
    [[ "$v" =~ ^[A-Za-z0-9._/@+-]*$ ]] || { echo "!! $CORES_CONF: '$k' has characters that are not allowed in a ref; ignored" >&2; continue; }
    [[ -v "$k" ]] || printf -v "$k" '%s' "$v"
  done < "$CORES_CONF"
  local n; for n in $CORE_REF_VARS; do [[ -v "$n" ]] || printf -v "$n" '%s' ""; done
  export $CORE_REF_VARS
}

# the ref a core is built at ("" = latest); Saturn falls back to its branch
core_ref() {
  local var; var="$(core_ref_var "$1")"; [[ -n "$var" ]] || return 0
  local r="${!var:-}"
  [[ -z "$r" && "$var" == SATURN_REF ]] && r="${SATURN_BRANCH:-}"
  printf '%s' "$r"
}

# git_fetch <core> <repo> <dest> [submodules 1|0]: clone <repo> at the core's ref into <dest>. A tag or branch is cloned shallow
# by name, a commit hash is fetched directly. A pinned ref that cannot be fetched is an error: it never falls back to the latest source.
# Appends "<core>|<repo>|<ref>|<commit>" to $CORES_LOG when that is set.
git_fetch() {
  local core="$1" repo="$2" dest="$3" rec="${4:-1}" ref; ref="$(core_ref "$core")"
  local sub=(); [[ "$rec" == 1 ]] && sub=(--recurse-submodules --shallow-submodules)
  rm -rf "$dest"
  if [[ -z "$ref" ]]; then
    git clone -q --depth 1 "${sub[@]}" "$repo" "$dest" || return 1
  elif ! git clone -q --depth 1 --branch "$ref" "${sub[@]}" "$repo" "$dest" 2>/dev/null; then
    rm -rf "$dest"; mkdir -p "$dest"
    { git -C "$dest" init -q && git -C "$dest" remote add origin "$repo" \
        && git -C "$dest" fetch -q --depth 1 origin "$ref" && git -C "$dest" checkout -q FETCH_HEAD; } \
      || { echo "!! cores.conf: cannot fetch '$ref' of $repo for $core (tag, branch or commit hash; check the spelling)" >&2; return 1; }
    [[ "$rec" == 1 ]] && { git -C "$dest" submodule update -q --init --recursive --depth 1 || return 1; }
  fi
  core_log "$core" "$repo" "${ref:-latest}" "$(git -C "$dest" rev-parse HEAD 2>/dev/null)"
}

# core_log <core> <repo> <ref> <commit>: one line per core in $CORES_LOG (a newer entry replaces the older one)
core_log() {
  [[ -n "${CORES_LOG:-}" ]] || return 0
  mkdir -p "$(dirname "$CORES_LOG")"; touch "$CORES_LOG"
  grep -v "^$1|" "$CORES_LOG" > "$CORES_LOG.tmp" 2>/dev/null || true
  printf '%s|%s|%s|%s\n' "$1" "$2" "$3" "$4" >> "$CORES_LOG.tmp"; mv -f "$CORES_LOG.tmp" "$CORES_LOG"
}
