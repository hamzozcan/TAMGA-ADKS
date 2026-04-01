#!/usr/bin/env python3
"""
TAMGA AFAD Bridge
-----------------
Yerel TAMGA düğümünden merkezi AFAD panel backend'ine snapshot push eder.
"""

import argparse
import sys
import time
from datetime import datetime

import requests


def log(msg: str):
    print(f"[AFAD-BRIDGE] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def fetch_snapshot(local_url: str, node_id: str, node_label: str) -> dict:
    resp = requests.get(
        f"{normalize_url(local_url)}/api/afad/local-snapshot",
        params={"node_id": node_id, "node_label": node_label},
        timeout=12,
    )
    resp.raise_for_status()
    return resp.json()


def push_snapshot(remote_url: str, shared_key: str, payload: dict) -> dict:
    resp = requests.post(
        f"{normalize_url(remote_url)}/api/afad/ingest",
        json=payload,
        headers={"x-tamga-key": shared_key},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def run_once(local_url: str, remote_url: str, shared_key: str, node_id: str, node_label: str) -> int:
    snapshot = fetch_snapshot(local_url, node_id, node_label)
    result = push_snapshot(remote_url, shared_key, snapshot)
    log(
        f"Snapshot gönderildi -> node={result.get('node_id', node_id)} "
        f"updated_at={result.get('updated_at', '-')}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TAMGA AFAD Bridge")
    parser.add_argument("--local-url", default="http://127.0.0.1:8000", help="Yerel TAMGA backend URL")
    parser.add_argument("--remote-url", required=True, help="Merkezi AFAD backend URL")
    parser.add_argument("--shared-key", default="", help="AFAD ingest shared key")
    parser.add_argument("--node-id", default="TAMGA-EDGE-001", help="Saha düğüm kimliği")
    parser.add_argument("--node-label", default="TAMGA Saha Düğümü", help="Saha düğüm etiketi")
    parser.add_argument("--interval", type=int, default=20, help="Gönderim aralığı (sn)")
    parser.add_argument("--once", action="store_true", help="Tek sefer gönder ve çık")
    args = parser.parse_args()

    shared_key = (args.shared_key or "").strip()
    if not shared_key:
        log("--shared-key zorunlu")
        return 2

    if args.once:
        try:
            return run_once(args.local_url, args.remote_url, shared_key, args.node_id, args.node_label)
        except Exception as exc:
            log(f"Hata: {exc}")
            return 1

    log(
        f"Bridge başladı | local={normalize_url(args.local_url)} "
        f"-> remote={normalize_url(args.remote_url)} | interval={args.interval}s"
    )
    while True:
        try:
            run_once(args.local_url, args.remote_url, shared_key, args.node_id, args.node_label)
        except KeyboardInterrupt:
            log("Kapatıldı")
            return 0
        except Exception as exc:
            log(f"Gönderim hatası: {exc}")
        time.sleep(max(5, int(args.interval)))


if __name__ == "__main__":
    sys.exit(main())
