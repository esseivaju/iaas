#!/bin/sh
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: $0 <changes-file> [interval-seconds]" >&2
  exit 2
fi

src_path=$1
interval=${2:-1}
dest_dir=/envoy-config/xds
dest_path=$dest_dir/eds.yaml

last_cksum=""

echo "watching $src_path every $interval seconds, applying changes to $dest_path on change"

append_endpoint() {
  file=$1
  ip=$2
  port=$3
  printf '\n    - endpoint:\n        address:\n          socket_address:\n            address: %s\n            port_value: %s\n' "$ip" "$port" >> "$file"
}

remove_endpoint() {
  ip=$1
  src=$2
  dst=$3
  awk -v ip="$ip" '
    function flush_block() {
      if (in_block) {
        if (!block_has_ip) {
          for (i = 1; i <= block_len; i++) print block[i];
        }
      }
      in_block = 0;
      block_len = 0;
      block_has_ip = 0;
    }
    {
      if ($0 ~ /^    - endpoint:/) {
        flush_block();
        in_block = 1;
      }
      if (in_block) {
        block[++block_len] = $0;
        if ($0 ~ /^            address: /) {
          addr = $0;
          sub(/^            address: /, "", addr);
          if (addr == ip) block_has_ip = 1;
        }
      } else {
        print $0;
      }
    }
    END { flush_block(); }
  ' "$src" > "$dst"
}

while :; do
  if [ -f "$src_path" ]; then
    cksum_val=$(cksum <"$src_path" | awk '{print $1}')
    if [ "$cksum_val" != "$last_cksum" ]; then
      if [ ! -d "$dest_dir" ]; then
        echo "error: destination directory missing: $dest_dir" >&2
        exit 1
      fi
      if [ ! -f "$dest_path" ]; then
        echo "error: destination file missing: $dest_path" >&2
        exit 1
      fi

      work_path=$dest_path.tmp
      cp "$dest_path" "$work_path"

      port=$(awk '/port_value:/ {print $2; exit}' "$work_path")
      if [ -z "$port" ]; then
        port=8001
      fi

      while IFS= read -r line || [ -n "$line" ]; do
        line=$(printf "%s" "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [ -z "$line" ]; then
          continue
        fi
        case "$line" in
          \#*) continue ;;
        esac

        op=$(printf "%s" "$line" | cut -c1)
        ip=$(printf "%s" "$line" | cut -c2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [ -z "$ip" ]; then
          echo "warning: invalid change line (missing ip): $line" >&2
          continue
        fi

        case "$op" in
          +)
            if ! grep -q "address: $ip" "$work_path"; then
              append_endpoint "$work_path" "$ip" "$port"
            fi
            ;;
          -)
            if grep -q "address: $ip" "$work_path"; then
              tmp_path=$work_path.next
              remove_endpoint "$ip" "$work_path" "$tmp_path"
              mv "$tmp_path" "$work_path"
            fi
            ;;
          *)
            echo "warning: invalid change line (use +<ip> or -<ip>): $line" >&2
            ;;
        esac
      done < "$src_path"

      mv "$work_path" "$dest_path"
      last_cksum=$cksum_val
      echo "updated $dest_path"
    fi
  fi
  sleep "$interval"
done
