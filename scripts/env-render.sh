#!/bin/bash
# =============================================================================
# env-render.sh -- narrow env projections for the infrastructure containers
# =============================================================================
#
# A LIBRARY, not a command: sourced by scripts/install_aivis.sh and by
# scripts/aivis-manage.sh. Running it directly does nothing.
#
# WHY IT EXISTS. backend/.env is the application's env: payment keys,
# session secret, telegram token, MinIO credentials, and now the comms
# service token. Handing that whole file to the datastore containers
# means a compromised postgres, redis or MinIO reads secrets that have
# nothing to do with it. Each of those containers needs between two and
# four keys, so it gets a PROJECTION carrying exactly those.
#
# After this library is in use, `app` is the only service in
# docker-compose.yml that still reads backend/.env -- which is correct:
# it is the application.
#
# TWO PROJECTIONS, ONE RENDERER. The donor product has a single
# projection and therefore a single hardcoded key list. aivis has two
# (its stack carries object storage, the donor's does not), and two
# copies of a forty-line renderer differing only in a key array and a
# header sentence would drift the first time one of them was fixed. So
# the renderer takes the key list; the projections are two arrays and
# two call sites.
#
# REGENERATED, NEVER EDITED: install writes both files, and every
# `aivis update` writes them again from backend/.env. Editing a
# projection by hand survives exactly until the next update.
# =============================================================================

# Keys the postgres and redis containers need, and nothing else.
# shellcheck disable=SC2034  # read through a nameref in render_env_projection
_DB_ENV_KEYS=(
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    REDIS_PASSWORD
)

# Keys the minio and minio-init containers need, and nothing else.
#
# ROOT_USER / ROOT_PASSWORD are what the server itself boots on.
# ACCESS_KEY / SECRET_KEY are the backend's service account -- strictly
# speaking only minio-init uses them, to CREATE that account
# (`mc admin user svcacct add` against the root user). They are in the
# one shared list rather than a third projection because the account
# lives inside MinIO: a compromised MinIO server can already read and
# rotate it, so withholding the pair from the server buys nothing, while
# a second file would be one more document to keep in step.
# shellcheck disable=SC2034  # read through a nameref in render_env_projection
_MINIO_ENV_KEYS=(
    MINIO_ROOT_USER
    MINIO_ROOT_PASSWORD
    MINIO_ACCESS_KEY
    MINIO_SECRET_KEY
)

# Print the assignment line for KEY out of FILE, or nothing if there is
# none.
#
# `tail -n 1` -- LAST occurrence, not first: a repeated key in a file
# read as shell assignments resolves to the last one, and compose reads
# an env_file the same way. Matching is on an exact `KEY=` prefix, so
# POSTGRES_PASSWORD_FILE and a commented-out `#POSTGRES_DB=` are not
# mistaken for the real key.
_env_line() {
    local file="$1" key="$2"
    grep -E "^${key}=" "$file" 2>/dev/null | tail -n 1
}

# render_env_projection <src .env> <name of keys array> <what it is for>
#
# Print the projection to stdout. Reads nothing but the file it is given,
# writes nothing, calls nothing external -- so it can be asserted on
# directly, without a filesystem.
#
# Returns non-zero WITHOUT printing a partial document when any key is
# missing or empty: a caller redirecting our stdout must never be handed
# half an env file.
#
# Lines are copied VERBATIM. A password may legitimately contain '#',
# '=', spaces or quotes, and compose's env_file reader takes the raw
# KEY=value line -- re-quoting the value would change what the container
# actually receives.
render_env_projection() {
    # `${N:-}`, not `$N`: callers run under `set -u`, where a bare $1
    # aborts the whole script before the argument check below can report
    # anything.
    local src="${1:-}" keys_name="${2:-}" purpose="${3:-}"

    if [ -z "$src" ] || [ -z "$keys_name" ]; then
        echo "env-render: usage: render_env_projection <src .env> <keys array name> [purpose]" >&2
        return 2
    fi
    if [ ! -r "$src" ]; then
        echo "env-render: cannot read $src" >&2
        return 1
    fi

    # A nameref, so the key list travels as data rather than as a second
    # copy of this function.
    local -n keys="$keys_name"

    local key line missing=""

    # Validate FIRST, render second. The check is on the VALUE, not on
    # the line: `POSTGRES_PASSWORD=` is a present line with an absent
    # password, and letting it through starts redis with no password at
    # all, leaves postgres unable to initialise a fresh volume, and
    # brings MinIO up on empty root credentials.
    for key in "${keys[@]}"; do
        line=$(_env_line "$src" "$key")
        if [ -z "${line#"${key}="}" ]; then
            missing="${missing:+$missing, }$key"
        fi
    done
    if [ -n "$missing" ]; then
        echo "env-render: missing (or empty) in $src: $missing" >&2
        echo "env-render: refusing to project a partial env -- the containers" >&2
        echo "env-render: reading it would start without their credentials." >&2
        return 1
    fi

    echo "# ==========================================================================="
    echo "# GENERATED by scripts/env-render.sh -- DO NOT EDIT."
    echo "# ==========================================================================="
    echo "# PROJECTION of backend/.env, regenerated on every install and every"
    echo "# update. backend/.env is the single source of these values -- edit"
    echo "# there and re-run \`aivis update\` (or the installer), never here."
    echo "#"
    echo "# Handed to ${purpose:-these containers} INSTEAD of the full backend/.env,"
    echo "# so a compromise there no longer exposes the application's payment,"
    echo "# telegram, session and service-token secrets."
    echo "# ==========================================================================="
    echo ""
    for key in "${keys[@]}"; do
        _env_line "$src" "$key"
    done
}

# write_env_projection <src .env> <dst> <keys array name> <what it is for>
#
# Returns 0 on success. Non-zero, with no partial file left behind, on
# any failure -- every caller treats that as fatal, and rightly.
write_env_projection() {
    local src="${1:-}" dst="${2:-}" keys_name="${3:-}" purpose="${4:-}"
    local old_umask tmp

    if [ -z "$src" ] || [ -z "$dst" ] || [ -z "$keys_name" ]; then
        echo "env-render: usage: write_env_projection <src .env> <dst> <keys array name> [purpose]" >&2
        return 2
    fi

    tmp="${dst}.tmp.$$"

    # umask BEFORE the first write, not chmod after it: the file holds
    # credentials and content lands the moment it exists, so a
    # create-then-chmod leaves a window in which it is world-readable.
    old_umask=$(umask)
    umask 077

    if ! render_env_projection "$src" "$keys_name" "$purpose" > "$tmp"; then
        umask "$old_umask"
        rm -f "$tmp"
        return 1
    fi

    # Belt AND braces: where `mv` below degrades from a rename into a
    # copy, the destination is created under the CALLER's umask and the
    # 077 set here is lost. An explicit mode on both files is the only
    # form that does not depend on which mv you got.
    chmod 600 "$tmp" 2>/dev/null || true
    umask "$old_umask"

    # Atomic swap: a concurrent reader (a compose command) sees either
    # the old file or the new one, never a half-written one.
    if ! mv -f "$tmp" "$dst"; then
        rm -f "$tmp"
        echo "env-render: cannot move $tmp -> $dst" >&2
        return 1
    fi

    # See the chmod above: this is the one that holds when mv copied
    # rather than renamed.
    chmod 600 "$dst" 2>/dev/null || true
    return 0
}

# The two projections this product actually has. Named wrappers rather
# than bare call sites so a failure message names the file the operator
# is about to lose, not a generic "projection".
write_db_env() {
    write_env_projection "${1:-}" "${2:-}" _DB_ENV_KEYS "the postgres and redis containers"
}

write_minio_env() {
    write_env_projection "${1:-}" "${2:-}" _MINIO_ENV_KEYS "the minio and minio-init containers"
}
