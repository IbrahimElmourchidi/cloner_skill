#!/usr/bin/env sh
# install.sh — install the clone-site skill for every AI agent on this machine.
#
#   ./install.sh              detect agents, install, link
#   ./install.sh --dry-run    show the plan, change nothing
#   ./install.sh --list       only report what was detected
#   ./install.sh --uninstall  remove every link and the canonical copy
#
# Design
# ------
# The Agent Skills specification does not mandate where skills live. What it
# documents instead is a widely-adopted convention:
#
#     user-level, cross-client    ~/.agents/skills/<name>/SKILL.md
#     user-level, client-native   ~/.<client>/skills/<name>/SKILL.md
#
# So this installs one real copy into ~/.agents/skills/, which every compliant
# client picks up, and symlinks it into each detected client's own directory
# for the clients that only read that one. One copy, many agents; update it
# once and it updates everywhere.
#
# Honesty about coverage: the agent table below is not a guess at forty
# clients. It lists only entries whose directory layout is verified — either
# checked against this machine or documented by the client's own docs. An
# agent not listed is one flag:
#
#     ./install.sh --link myagent=~/.config/myagent/skills
#
# A wrong path in the table would create a directory nothing ever reads while
# the user believed the skill was installed. That failure is worse than an
# agent being absent from the list, so the list stays short on purpose.

set -u

SKILL_NAME=clone-site
REPO=$(cd "$(dirname "$0")" && pwd -P)
HOME_DIR=${HOME:?HOME is not set}

CANONICAL="$HOME_DIR/.agents/skills/$SKILL_NAME"

# Written inside the canonical copy to mark it as ours.
#
# Without it there is no way to tell our own install from a directory a user
# made by hand, because the canonical copy is a real directory by design — it
# is the thing everything else symlinks to. Guessing "any real directory here
# is foreign" makes the second run fail, and the second run is the update
# path, which is the one people actually use.
MARKER=.installed-by-cloner-skill

# Explicit list rather than `cp -R .`, so __pycache__ and local scratch files
# are not copied into a skill directory. `bin` is included so the installed copy
# is self-sufficient — the agent only ever needs scripts/, but a user reading
# the note after installing should have a working command to run.
PAYLOAD="SKILL.md assets scripts templates references bin README.md LICENSE"

DRY=0
DO_UNINSTALL=0
ONLY_LIST=0
FORCE=0
AGENTS_FILTER=""
EXTRA_LINK=""
CANONICAL_OVERRIDE=""

# ---------------------------------------------------------------------------
# Agent table
#
#   kind = link   : has a client-native skills dir; needs a symlink there
#   kind = shared : reads ~/.agents/skills/ already; nothing to do but report
#
# Format: kind|id|label|skills-dir|binary|why
# ---------------------------------------------------------------------------
AGENTS='shared|codex|OpenAI Codex|-|codex|documents $HOME/.agents/skills as its personal skill scope
shared|cursor|Cursor|-|cursor-agent|documents ~/.agents/skills for cross-client skills
link|claude|Claude Code|.claude/skills|claude|verified: ~/.claude/skills is the native dir
link|gemini|Gemini CLI|.gemini/skills|gemini|verified; Gemini CLI also reads ~/.agents/skills
link|antigravity|Gemini Antigravity|.gemini/antigravity-cli/skills|antigravity|verified: does NOT read ~/.agents/skills
link|opencode|OpenCode|.config/opencode/skills|opencode|verified: XDG path, ~/.config/opencode'

usage() {
    cat <<'EOF'
install.sh — install the clone-site skill for every AI agent on this machine

  ./install.sh                 Detect agents, install, link
  ./install.sh --dry-run       Print the plan, change nothing
  ./install.sh --list          Report what was detected, install nothing
  ./install.sh --uninstall     Remove every link and the canonical copy

  -a, --agents a,b      Only these agents (ids from --list)
      --link ID=PATH    Link an agent not in the table
      --canonical PATH  Install somewhere other than ~/.agents/skills
  -f, --force           Replace files that are in the way
  -h, --help            This message
EOF
}

die() { printf 'install.sh: %s\n' "$1" >&2; exit 1; }
say() { printf '%s\n' "$1"; }

# Colour only when stdout is a terminal, so redirected output stays readable.
if [ -t 1 ] && [ "${NO_COLOR:-}" = "" ]; then
    C_OK=$(printf '\033[32m'); C_SKIP=$(printf '\033[90m')
    C_PLAN=$(printf '\033[33m'); C_BAD=$(printf '\033[31m'); C_OFF=$(printf '\033[0m')
else
    C_OK=; C_SKIP=; C_PLAN=; C_BAD=; C_OFF=
fi
ok()   { printf '  %sok%s    %s\n'    "$C_OK"   "$C_OFF" "$1"; }
skip() { printf '  %s--%s    %s\n'    "$C_SKIP" "$C_OFF" "$1"; }
plan() { printf '  %s??%s    %s\n'    "$C_PLAN" "$C_OFF" "$1"; }
bad()  { printf '  %sXX%s    %s\n'    "$C_BAD"  "$C_OFF" "$1"; }
pad()  { printf '%-20s' "$1"; }

while [ $# -gt 0 ]; do
    case $1 in
        --dry-run|-n)   DRY=1 ;;
        --list)         ONLY_LIST=1 ;;
        --uninstall)    DO_UNINSTALL=1 ;;
        --force|-f)     FORCE=1 ;;
        -a|--agents)    AGENTS_FILTER=$2; shift ;;
        --agents=*)     AGENTS_FILTER=${1#*=} ;;
        --link)         EXTRA_LINK="$EXTRA_LINK $2"; shift ;;
        --link=*)       EXTRA_LINK="$EXTRA_LINK ${1#*=}" ;;
        --canonical)    CANONICAL_OVERRIDE=$2; shift ;;
        --canonical=*)  CANONICAL_OVERRIDE=${1#*=} ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "unknown option: $1  (try: ./install.sh --help)" ;;
    esac
    shift
done

[ -n "$CANONICAL_OVERRIDE" ] && CANONICAL=$CANONICAL_OVERRIDE

# Present? A config directory is the strongest signal; a binary on PATH catches
# the fresh-install case where nothing is configured yet. Either alone gives
# false negatives — an agent installed but never run, or a binary no longer on
# PATH but with a config dir left behind.
detected() {
    _dir=$1; _bin=$2
    [ "$_dir" != "-" ] && [ -d "$HOME_DIR/$_dir" ] && return 0
    command -v "$_bin" >/dev/null 2>&1
}

selected() {
    [ -z "$AGENTS_FILTER" ] && return 0
    case ",$AGENTS_FILTER," in *",$1,"*) return 0 ;; esac
    return 1
}

# --- detect ----------------------------------------------------------------
#
# The loop is fed by a heredoc, not a pipe. A pipe would put this in a subshell
# and every variable it set would vanish on exit — which is why an earlier
# draft had to spill its results to temp files inside the repo.

say "AI agents on this machine"
say "-------------------------"

FOUND_LINK=""
FOUND_SHARED=""

while IFS='|' read -r kind id label dir bin why; do
    [ -n "$id" ] || continue
    selected "$id" || continue
    if ! detected "$dir" "$bin"; then
        skip "$(pad "$label") not detected"
        continue
    fi
    if [ "$kind" = shared ]; then
        ok "$(pad "$label") reads ~/.agents/skills — already covered"
        FOUND_SHARED="$FOUND_SHARED$label, "
    else
        ok "$(pad "$label") $HOME_DIR/$dir"
        FOUND_LINK="$FOUND_LINK$id|$label|$dir
"
    fi
done <<AGENTS
$AGENTS
AGENTS

for spec in $EXTRA_LINK; do
    [ -n "$spec" ] || continue
    id=${spec%%=*}
    path=${spec#*=}
    [ -n "$id" ] && [ -n "$path" ] || die "--link needs ID=PATH, got: $spec"
    case $path in
        "~/"*) dir=${path#\~/} ;;
        /*)    dir=$path ;;
        *)     die "--link path must start with ~/ or /, got: $path" ;;
    esac
    ok "$(pad "$id") $HOME_DIR/$dir (--link)"
    FOUND_LINK="$FOUND_LINK$id|$id|$dir
"
done

if [ "$ONLY_LIST" = 1 ]; then
    say ""
    say "Canonical location: $CANONICAL"
    exit 0
fi

# --- uninstall -------------------------------------------------------------

if [ "$DO_UNINSTALL" = 1 ]; then
    say ""
    say "Uninstalling"
    [ -n "$FOUND_LINK" ] && while IFS='|' read -r id label dir; do
        [ -n "$id" ] || continue
        target="$HOME_DIR/$dir/$SKILL_NAME"
        if [ -L "$target" ]; then
            [ "$DRY" = 1 ] && plan "would unlink $target" || { rm -f "$target"; ok "unlinked $(pad "$label") $target"; }
        elif [ -e "$target" ]; then
            bad "$(pad "$label") $target exists and is not a symlink — left alone"
        else
            skip "$(pad "$label") nothing to remove"
        fi
    done <<LIST
$FOUND_LINK
LIST
    # Count links across EVERY detected agent, not just the filtered set. The
    # canonical copy is shared, so removing it while any link survives leaves
    # dangling symlinks in other agents' directories — which reads as a broken
    # install rather than as "you unlinked only some of them".
    remaining=0
    while IFS='|' read -r kind id label dir bin why; do
        [ -n "$id" ] || continue
        [ "$kind" = shared ] && continue
        detected "$dir" "$bin" || continue
        [ -L "$HOME_DIR/$dir/$SKILL_NAME" ] && remaining=$((remaining + 1))
    done <<AGENTS2
$AGENTS
AGENTS2

    if [ "$remaining" -gt 0 ]; then
        bad "canonical left in place: $remaining agent(s) still link to it."
        bad "unlink those too, or run --uninstall without --agents"
    elif [ -e "$CANONICAL" ] || [ -L "$CANONICAL" ]; then
        if [ -f "$CANONICAL/$MARKER" ]; then
            [ "$DRY" = 1 ] && plan "would remove $CANONICAL" || { rm -rf "$CANONICAL"; ok "removed $CANONICAL"; }
        else
            bad "$CANONICAL has no $MARKER marker — not ours, left alone"
        fi
    fi
    exit 0
fi

# --- install ---------------------------------------------------------------

say ""
say "Installing"
say "----------"
say "  canonical: $CANONICAL"

if [ "$DRY" = 1 ]; then
    plan "would create $CANONICAL"
else
    if [ -e "$CANONICAL" ] || [ -L "$CANONICAL" ]; then
        if [ ! -f "$CANONICAL/$MARKER" ] && [ "$FORCE" != 1 ]; then
            die "$CANONICAL exists, has no $MARKER marker, so it was not created by
  this script and is not being overwritten.
  Re-run with --force if it is safe to replace."
        fi
    fi
    rm -rf "$CANONICAL"
    mkdir -p "$CANONICAL"
    : > "$CANONICAL/$MARKER"
    for item in $PAYLOAD; do
        [ -e "$REPO/$item" ] || die "incomplete checkout: $item is missing from $REPO"
        cp -R "$REPO/$item" "$CANONICAL/$item"
    done
    find "$CANONICAL" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
    ok "installed $(printf '%s\n' $PAYLOAD | wc -l | tr -d ' ') items"
fi

[ -n "$FOUND_LINK" ] && while IFS='|' read -r id label dir; do
    [ -n "$id" ] || continue
    target="$HOME_DIR/$dir/$SKILL_NAME"
    parent="$HOME_DIR/$dir"
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$CANONICAL" ]; then
        skip "$(pad "$label") already linked"
        continue
    fi
    if [ -e "$target" ] && [ ! -L "$target" ]; then
        if [ "$FORCE" != 1 ]; then
            bad "$(pad "$label") $target is not a symlink — refusing, use --force"
            continue
        fi
        [ "$DRY" = 1 ] || rm -rf "$target"
    fi
    if [ "$DRY" = 1 ]; then
        plan "would link $(pad "$label") $target -> $CANONICAL"
    else
        mkdir -p "$parent"
        ln -sfn "$CANONICAL" "$target"
        ok "$(pad "$label") linked $target"
    fi
done <<LIST
$FOUND_LINK
LIST

# --- summary ---------------------------------------------------------------

say ""
if [ "$DRY" = 1 ]; then
    say "Dry run. Nothing was changed."
else
    say "Installed. Restart the agents you use — skills are discovered at"
    say "startup, not watched for changes."
    say ""
    say "Then, in any of them:"
    say "    \"set up the step-by-step guide site for this repo\""
    say ""
    say "To scaffold directly:"
    say "    $CANONICAL/bin/clone-site init <project> --name \"My Project\""
fi

[ -n "$FOUND_SHARED" ] && say "" && say "Also covered by ~/.agents/skills: ${FOUND_SHARED%, }"
exit 0