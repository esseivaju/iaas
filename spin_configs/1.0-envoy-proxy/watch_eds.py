#!/usr/bin/env python3
import argparse
import hashlib
import os
import shutil
import sys
import time
from typing import Optional


def file_checksum(path: str) -> str:
    # Content hash for change detection.
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def first_port_value(path: str, default_port: str) -> str:
    # Reuse the first port_value found in the existing EDS.
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("port_value:"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip() or default_port
    return default_port


def append_endpoint(path: str, ip: str, port: str) -> None:
    # Append a new endpoint stanza using the current indentation style.
    with open(path, "a", encoding="utf-8") as f:
        f.write(
            "    - endpoint:\n"
            "        address:\n"
            "          socket_address:\n"
            f"            address: {ip}\n"
            f"            port_value: {port}\n"
        )


def remove_endpoint(src_path: str, dst_path: str, ip: str) -> None:
    # Copy all content except the endpoint block whose address matches ip.
    in_block = False
    block = []
    block_has_ip = False

    def flush_block(out_f) -> None:
        # Emit the buffered block unless it matches the target IP.
        nonlocal block, block_has_ip
        if block and not block_has_ip:
            out_f.writelines(block)
        block = []
        block_has_ip = False

    with open(src_path, "r", encoding="utf-8") as src, open(dst_path, "w", encoding="utf-8") as dst:
        for line in src:
            if line.startswith("    - endpoint:"):
                # New endpoint block begins; flush the previous block first.
                flush_block(dst)
                in_block = True
            if in_block:
                block.append(line)
                if line.startswith("            address: "):
                    addr = line.split(":", 1)[1].strip()
                    if addr == ip:
                        block_has_ip = True
            else:
                dst.write(line)
        if in_block:
            flush_block(dst)


def apply_changes(changes_path: str, eds_path: str) -> None:
    # Apply +IP/-IP changes to a temp copy of the EDS, then atomically replace.
    if not os.path.isfile(eds_path):
        raise FileNotFoundError(f"destination file missing: {eds_path}")

    work_path = f"{eds_path}.tmp"
    shutil.copyfile(eds_path, work_path)

    port = first_port_value(work_path, "8001")

    with open(changes_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            op = line[:1]
            ip = line[1:].strip()
            if not ip:
                print(f"warning: invalid change line (missing ip): {raw_line.rstrip()}", file=sys.stderr)
                continue

            if op == "+":
                # Add if missing.
                with open(work_path, "r", encoding="utf-8") as cur:
                    if f"address: {ip}" not in cur.read():
                        append_endpoint(work_path, ip, port)
            elif op == "-":
                # Remove if present.
                with open(work_path, "r", encoding="utf-8") as cur:
                    if f"address: {ip}" in cur.read():
                        next_path = f"{work_path}.next"
                        remove_endpoint(work_path, next_path, ip)
                        os.replace(next_path, work_path)
            else:
                print(f"warning: invalid change line (use +<ip> or -<ip>): {raw_line.rstrip()}", file=sys.stderr)

    os.replace(work_path, eds_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch a changes file and apply +IP/-IP to Envoy EDS.")
    parser.add_argument("changes_file", help="File with +<ip> or -<ip> per line")
    parser.add_argument("interval", nargs="?", type=float, default=1.0, help="Polling interval seconds")
    parser.add_argument(
        "--dest",
        default="/envoy-config/xds/eds.yaml",
        help="Destination EDS YAML path (default: /envoy-config/xds/eds.yaml)",
    )
    args = parser.parse_args()

    dest_dir = os.path.dirname(args.dest)
    if not os.path.isdir(dest_dir):
        print(f"error: destination directory missing: {dest_dir}", file=sys.stderr)
        return 1

    last_cksum: Optional[str] = None
    print(
        f"watching {args.changes_file} every {args.interval} seconds, "
        f"applying changes to {args.dest} on change"
    )

    while True:
        if os.path.isfile(args.changes_file):
            cksum = file_checksum(args.changes_file)
            if cksum != last_cksum:
                # Apply changes only when the input file content changes.
                apply_changes(args.changes_file, args.dest)
                last_cksum = cksum
                print(f"updated {args.dest}")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
