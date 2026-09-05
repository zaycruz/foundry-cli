#!/usr/bin/env python3
"""Long-running CDP network capture for reverse-engineering Palantir Foundry APIs.

Attaches to a Chromium browser (Arc/Chrome) started with
``--remote-debugging-port`` and records every request to
``*.palantirfoundry.com`` — URL, POST body, response body — to daily-rotated
JSONL files. Authorization and Cookie headers are redacted at capture time.

Designed to run for weeks under launchd: reconnects forever when the browser
restarts, rotates output files daily, and tolerates malformed frames.

Usage:
    python3 palantir_cdp_capture.py [--port 9223] [--outdir ~/.palantir-capture]

The capture is the evidence source for the reverse-engineering tickets in
``tickets/`` — mined endpoints must still pass the contract-verification gate
before shipping as CLI commands.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import sys
import urllib.request

SKIP_EXTENSIONS = (
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".map", ".webp", ".avif",
)
ALLOWED_HOST_SUFFIXES = (".palantirfoundry.com",)
REDACTED_HEADERS = {"authorization", "cookie", "proxy-authorization", "x-api-key"}

_id_counter = 0
pending: dict[int, dict] = {}
requests_by_id: dict[tuple, dict] = {}
out_lock = asyncio.Lock()
out_dir = ""
out_file = None
out_date = ""


def next_id() -> int:
    global _id_counter
    _id_counter += 1
    return _id_counter


def interesting(url: str) -> bool:
    if not url.startswith("http"):
        return False
    host = url.split("/")[2].split(":")[0].lower()
    if not any(host.endswith(s) for s in ALLOWED_HOST_SUFFIXES):
        return False
    path = url.split("?")[0].lower()
    return not path.endswith(SKIP_EXTENSIONS)


def current_outfile():
    """Return the daily-rotated output file handle, rolling at midnight."""
    global out_file, out_date
    today = datetime.date.today().isoformat()
    if out_file is None or out_date != today:
        if out_file is not None:
            out_file.close()
        out_date = today
        path = os.path.join(out_dir, f"capture-{today}.jsonl")
        out_file = open(path, "a")
        print(f"[rotate] writing {path}", flush=True)
    return out_file


async def send(ws, method, params=None, session_id=None):
    mid = next_id()
    msg = {"id": mid, "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    fut = asyncio.get_event_loop().create_future()
    pending[mid] = {"future": fut}
    await ws.send(json.dumps(msg))
    return await fut


async def write_record(rec):
    async with out_lock:
        rec["capturedAt"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        current_outfile().write(json.dumps(rec) + "\n")
        current_outfile().flush()


async def handle_event(ws, msg):
    method = msg.get("method")
    params = msg.get("params", {})
    session_id = msg.get("sessionId")
    try:
        await _handle_event_inner(ws, method, params, session_id)
    except Exception as e:
        print(f"[warn] {method}: {e}", flush=True)


async def _handle_event_inner(ws, method, params, session_id):
    if method == "Target.attachedToTarget":
        sid = params["sessionId"]
        await send(ws, "Network.enable", {"maxPostDataSize": 10_000_000}, sid)
        print(f"[attach] {params['targetInfo'].get('url', '')[:100]}", flush=True)
        return

    if not session_id:
        return

    if method == "Network.requestWillBeSent":
        req = params["request"]
        url = req["url"]
        if not interesting(url):
            return
        key = (session_id, params["requestId"])
        requests_by_id[key] = {
            "url": url,
            "method": req["method"],
            "postData": req.get("postData"),
            "headers": {
                k: v for k, v in req.get("headers", {}).items()
                if k.lower() not in REDACTED_HEADERS
            },
            "type": params.get("type"),
        }
        print(f"[req] {req['method']} {url[:140]}", flush=True)

    elif method == "Network.responseReceived":
        key = (session_id, params["requestId"])
        rec = requests_by_id.get(key)
        if rec is not None:
            rec["status"] = params["response"]["status"]
            rec["mimeType"] = params["response"].get("mimeType")

    elif method == "Network.loadingFinished":
        key = (session_id, params["requestId"])
        rec = requests_by_id.pop(key, None)
        if rec is None:
            return
        try:
            body_resp = await send(
                ws, "Network.getResponseBody", {"requestId": key[1]}, session_id,
            )
            result = body_resp.get("result", {})
            body = result.get("body", "")
            if result.get("base64Encoded"):
                body = "<base64:" + str(len(body)) + " chars>"
            rec["responseBody"] = body
        except Exception as e:
            rec["responseBodyError"] = str(e)
        await write_record(rec)
        print(f"[done] {rec.get('status')} {rec['url'][:140]}", flush=True)


async def capture_loop(port: int):
    import websockets

    version_url = f"http://127.0.0.1:{port}/json/version"
    while True:
        try:
            with urllib.request.urlopen(version_url, timeout=5) as r:
                info = json.load(r)
        except Exception:
            await asyncio.sleep(5)
            continue

        ws_url = info["webSocketDebuggerUrl"]
        print(f"[connect] {ws_url}", flush=True)
        try:
            async with websockets.connect(ws_url, max_size=100_000_000) as ws:
                async def receiver():
                    async for raw in ws:
                        msg = json.loads(raw)
                        if "id" in msg and msg["id"] in pending:
                            pending.pop(msg["id"])["future"].set_result(msg)
                        else:
                            asyncio.create_task(handle_event(ws, msg))

                recv_task = asyncio.create_task(receiver())
                await send(ws, "Target.setAutoAttach", {
                    "autoAttach": True,
                    "waitForDebuggerOnStart": False,
                    "flatten": True,
                })
                await send(ws, "Target.setDiscoverTargets", {"discover": True})
                print("[ready] capturing — browser restarts will be re-attached", flush=True)
                await recv_task
        except Exception as e:
            print(f"[disconnect] {e}; retrying in 5s", flush=True)
            pending.clear()
            requests_by_id.clear()
            await asyncio.sleep(5)


def main():
    global out_dir
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9223)
    parser.add_argument(
        "--outdir", default=os.path.expanduser("~/.palantir-capture")
    )
    args = parser.parse_args()
    out_dir = args.outdir
    os.makedirs(out_dir, exist_ok=True)
    try:
        asyncio.run(capture_loop(args.port))
    except KeyboardInterrupt:
        print("\n[stopped]")


if __name__ == "__main__":
    main()
