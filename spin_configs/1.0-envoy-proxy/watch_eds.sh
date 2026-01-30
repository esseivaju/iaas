#!/bin/sh
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: $0 <incoming-eds.yaml> [interval-seconds]" >&2
  exit 2
fi

src_path=$1
interval=${2:-1}
dest_dir=/envoy-config/xds
dest_path=$dest_dir/eds.yaml

last_cksum=""

echo "watching $src_path every $interval seconds, copying to $dest_path on change"

while :; do
  if [ -f "$src_path" ]; then
    cksum_val=$(cksum <"$src_path" | awk '{print $1}')
    if [ "$cksum_val" != "$last_cksum" ]; then
      if [ ! -d "$dest_dir" ]; then
        echo "error: destination directory missing: $dest_dir" >&2
        exit 1
      fi
      tmp_path=$dest_path.tmp
      cp "$src_path" "$tmp_path"
      mv "$tmp_path" "$dest_path"
      last_cksum=$cksum_val
      echo "updated $dest_path"
    fi
  fi
  sleep "$interval"
done
