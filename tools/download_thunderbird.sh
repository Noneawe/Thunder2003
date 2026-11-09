#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_root="$project_root/runtime"
locale="${1:-pl}"
case "$locale" in
  pl) runtime_name="thunderbird" ;;
  en-US) runtime_name="thunderbird-en-US" ;;
  *) echo "Usage: $0 [pl|en-US]" >&2; exit 2 ;;
esac
if [[ -x "$runtime_root/$runtime_name/thunderbird" ]]; then
  "$runtime_root/$runtime_name/thunderbird" --version
  exit
fi
if [[ -e "$runtime_root/$runtime_name" ]]; then
  echo "Katalog runtime/$runtime_name już istnieje; nie zostanie nadpisany." >&2
  exit 1
fi
mkdir -p "$runtime_root"
download_dir="$(mktemp -d "$runtime_root/.download-159.XXXXXX")"
trap 'rm -rf -- "$download_dir"' EXIT
base_url="https://archive.mozilla.org/pub/thunderbird/releases/159.0"
archive_path="linux-x86_64/$locale/thunderbird-159.0.tar.xz"
curl --fail --location --connect-timeout 20 --max-time 600 \
  --output "$download_dir/thunderbird-159.0.tar.xz" "$base_url/$archive_path"
curl --fail --location --connect-timeout 20 --max-time 60 \
  --output "$download_dir/SHA512SUMS" "$base_url/SHA512SUMS"
awk -v archive="$archive_path" \
  '$2 == archive { print $1 "  thunderbird-159.0.tar.xz"; found=1 } END { if (!found) exit 1 }' \
  "$download_dir/SHA512SUMS" > "$download_dir/checksum.sha512"
(cd -- "$download_dir" && sha512sum --check checksum.sha512)
tar --extract --xz --file "$download_dir/thunderbird-159.0.tar.xz" \
  --directory "$download_dir" --no-same-owner
test -x "$download_dir/thunderbird/thunderbird"
mv -- "$download_dir/thunderbird" "$runtime_root/$runtime_name"
mv -- "$download_dir/SHA512SUMS" "$runtime_root/SHA512SUMS-159.0-$locale"
echo "Thunderbird 159.0 ($locale) jest gotowy: $runtime_root/$runtime_name/thunderbird"
