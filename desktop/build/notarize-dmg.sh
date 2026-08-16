#!/usr/bin/env bash
#
# STAGE 2 of the decoupled release pipeline: notarize signed dmgs locally.
#
# CI (stage 1) already produced code-signed, hardened-runtime dmgs and mirrored
# them to R2 as unpublished. Apple's notary service keeps this large PyInstaller
# bundle "In Progress" for hours, so we notarize here — off the CI clock — and
# staple the ticket straight onto the dmg (users download it ready-to-run).
#
# What it does for each dmg passed on the command line:
#   1. submit the dmg to the notary service ONCE (--no-wait) and remember the id,
#   2. poll that SAME id until Accepted/Invalid; network errors are ignored and
#      retried, and it NEVER resubmits (avoids piling up duplicate submissions),
#   3. staple the ticket onto the dmg,
#   4. (optional) re-upload the stapled dmg to R2, overwriting the unpublished
#      copy, so the CDN serves the notarized bytes.
#
# Auth: uses a stored keychain profile (default: cow-notary). Create it once via
#   xcrun notarytool store-credentials cow-notary \
#     --apple-id <id> --team-id <team> --password <app-specific-password>
#
# Usage:
#   # notarize + staple only (no upload):
#   desktop/build/notarize-dmg.sh path/to/CowAgent-1.2.3-arm64.dmg [more.dmg ...]
#
#   # notarize + staple + re-upload to R2 (needs wrangler + Cloudflare creds):
#   VER=1.2.3 UPLOAD=1 desktop/build/notarize-dmg.sh *.dmg
#
# Env:
#   PROFILE            keychain profile name (default: cow-notary)
#   UPLOAD             set to 1 to re-upload stapled dmgs to R2
#   VER                version string for the R2 key desktop/v${VER}/<file> (required if UPLOAD=1)
#   R2_BUCKET          R2 bucket (default: cow-skills)
#   POLL_SECONDS       status poll interval (default: 60)
#   MAX_WAIT_MINUTES   give up polling after this long (default: 720 = 12h)
#
set -euo pipefail

PROFILE="${PROFILE:-cow-notary}"
R2_BUCKET="${R2_BUCKET:-cow-skills}"
POLL_SECONDS="${POLL_SECONDS:-60}"
MAX_WAIT_MINUTES="${MAX_WAIT_MINUTES:-720}"

if [ "$#" -eq 0 ]; then
  echo "usage: $0 <dmg> [dmg ...]" >&2
  echo "  set UPLOAD=1 and VER=<version> to also re-upload stapled dmgs to R2" >&2
  exit 2
fi

if [ "${UPLOAD:-0}" = "1" ] && [ -z "${VER:-}" ]; then
  echo "error: UPLOAD=1 requires VER=<version> (used for the R2 key)" >&2
  exit 2
fi

log() { echo "[notarize-dmg] $*"; }

notarize_one() {
  local dmg="$1"
  if [ ! -f "$dmg" ]; then
    log "SKIP: not a file: $dmg"
    return 1
  fi

  # If it's already stapled (e.g. re-run), skip straight to (optional) upload.
  if xcrun stapler validate "$dmg" >/dev/null 2>&1; then
    log "$dmg already stapled — skipping notarization."
  else
    log "submitting $dmg (no-wait)..."
    local submit_out submission_id
    submit_out="$(xcrun notarytool submit "$dmg" \
      --keychain-profile "$PROFILE" --no-wait --output-format json)"
    submission_id="$(echo "$submit_out" | /usr/bin/plutil -extract id raw - 2>/dev/null || true)"
    if [ -z "$submission_id" ] || [ "$submission_id" = "null" ]; then
      # Fallback parse without plutil (json is single-line).
      submission_id="$(echo "$submit_out" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')"
    fi
    if [ -z "$submission_id" ]; then
      log "ERROR: could not parse submission id from:"
      echo "$submit_out" >&2
      return 1
    fi
    log "submission id: $submission_id (polling same id, never resubmitting)"

    local deadline status ts
    deadline=$(( $(date +%s) + MAX_WAIT_MINUTES * 60 ))
    while :; do
      status=""
      status="$(xcrun notarytool info "$submission_id" \
        --keychain-profile "$PROFILE" --output-format json 2>/dev/null \
        | sed -n 's/.*"status":"\([^"]*\)".*/\1/p' || true)"
      ts="$(date +%H:%M:%S)"
      log "[$ts] status: ${status:-<query failed, retrying>}"

      case "$status" in
        Accepted) break ;;
        Invalid|Rejected)
          log "notarization $status — fetching log:"
          xcrun notarytool log "$submission_id" --keychain-profile "$PROFILE" || true
          return 1
          ;;
      esac

      if [ "$(date +%s)" -ge "$deadline" ]; then
        log "ERROR: not finished after ${MAX_WAIT_MINUTES} min (id: $submission_id)."
        log "NOT resubmitting. Check later: xcrun notarytool info $submission_id --keychain-profile $PROFILE"
        return 1
      fi
      sleep "$POLL_SECONDS"
    done

    log "Accepted; stapling ticket to $dmg"
    local staple_try=1
    until xcrun stapler staple "$dmg"; do
      if [ "$staple_try" -ge 3 ]; then
        log "ERROR: stapling failed after 3 attempts"
        return 1
      fi
      log "staple failed, retrying in 15s..."
      sleep 15
      staple_try=$((staple_try + 1))
    done
    xcrun stapler validate "$dmg"
    log "$dmg notarized + stapled."
  fi

  if [ "${UPLOAD:-0}" = "1" ]; then
    local base key
    base="$(basename "$dmg")"
    key="desktop/v${VER}/${base}"
    log "re-uploading stapled dmg -> r2://${R2_BUCKET}/${key}"
    npx --yes wrangler@latest r2 object put "${R2_BUCKET}/${key}" \
      --file "$dmg" --remote
    log "uploaded $base"
  fi
}

rc=0
for dmg in "$@"; do
  echo "======================================================================"
  notarize_one "$dmg" || rc=1
done

if [ "$rc" -ne 0 ]; then
  log "one or more dmgs failed — see output above."
  exit 1
fi
log "all done."
