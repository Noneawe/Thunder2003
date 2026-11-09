#!/usr/bin/env bash
set -euo pipefail
profile_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
variant="${1:-blue}"
case "$variant" in
  blue|silver|graphite|mocha|sage|aurora) ;;
  all)
    for theme in blue silver graphite mocha sage aurora; do
      "$profile_root/open.sh" "$theme" &
    done
    wait
    exit
    ;;
  *) echo "Użycie: $0 [blue|silver|graphite|mocha|sage|aurora|all]" >&2; exit 2 ;;
esac
if [[ ! -f "$profile_root/$variant/prefs.js" ]]; then
  echo "Brak profilu: $variant. Uruchom tools/create_test_profiles.py." >&2
  exit 1
fi
thunderbird_binary="${THUNDERBIRD_BINARY:-$profile_root/../runtime/thunderbird/thunderbird}"
if [[ ! -x "$thunderbird_binary" ]]; then
  echo "Brak lokalnego Thunderbirda. Uruchom: bash tools/download_thunderbird.sh" >&2
  exit 1
fi
exec "$thunderbird_binary" --no-remote --offline --profile "$profile_root/$variant"
