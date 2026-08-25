#!/usr/bin/env python3
"""leader_send.py — deliver one kickoff prompt to the team leader over the gateway WS.

Frame shape required by the WebChannel (_handle_raw_message):
    {"type":"req", "id":"<str>", "method":"chat.send", "params":{...}}
On success the gateway replies {"type":"res","id":<id>,"ok":true,"payload":{"accepted":true,...}}
and emits a team.runtime_ready event. This script sends the kickoff and CONFIRMS that
accepted:true came back for its request id, so a silent drop is caught.

Usage:
  leader_send.py --file kickoff.txt
  leader_send.py "<kickoff text>"
Exit: 0 accepted, 1 connect/send failure, 3 sent-but-not-accepted, 2 bad args.
"""
import argparse, asyncio, json, os, sys, time, secrets

WS_URL = os.environ.get("JW_WS_URL", "ws://localhost:19100/ws")
MODEL  = os.environ.get("JW_MODEL", "deepseek-v4-pro")
CONNECT_TIMEOUT = float(os.environ.get("JW_CONNECT_TIMEOUT", "20"))
ACCEPT_TIMEOUT  = float(os.environ.get("JW_ACCEPT_TIMEOUT", "15"))

def _id():  return f"req_{secrets.token_hex(6)}"
def _sid(): return f"sess_{secrets.token_hex(6)}"

def frame(method, params):
    return {"type": "req", "id": _id(), "method": method, "params": params}

async def send(prompt):
    try:
        import websockets
    except ImportError:
        print("ERROR: pip install websockets", file=sys.stderr); return 1
    sid = _sid()
    chat = frame("chat.send", {
        "session_id": sid, "content": prompt, "mode": "team",
        "model_name": MODEL, "query": prompt,
    })
    try:
        async with websockets.connect(WS_URL, open_timeout=CONNECT_TIMEOUT, max_size=None) as ws:
            # drain the connection.ack the gateway pushes on connect
            try: await asyncio.wait_for(ws.recv(), timeout=3)
            except Exception: pass
            await ws.send(json.dumps(chat))
            # confirm acceptance: look for res ok:true accepted:true for OUR id,
            # or a team.runtime_ready event for our session
            accepted = False
            t0 = time.time()
            while time.time() - t0 < ACCEPT_TIMEOUT:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=ACCEPT_TIMEOUT)
                except Exception:
                    break
                try: msg = json.loads(raw)
                except Exception: continue
                if msg.get("type") == "res" and msg.get("id") == chat["id"]:
                    if msg.get("ok") and (msg.get("payload") or {}).get("accepted"):
                        accepted = True; break
                    else:
                        print(f"[leader_send] REJECTED: {str(raw)[:200]}", file=sys.stderr)
                        return 3
                if msg.get("event") == "team.runtime_ready":
                    accepted = True; break
            if accepted:
                print(f"[leader_send] accepted (session {sid})", file=sys.stderr)
            print(f"SESSION={sid}")  # stdout, machine-readable for run_one.sh
            return 0
            print("[leader_send] sent but no accepted:true / runtime_ready seen", file=sys.stderr)
            return 3
    except Exception as e:
        print(f"ERROR: send failed: {e}", file=sys.stderr); return 1

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("prompt", nargs="?")
    g.add_argument("--file")
    a = ap.parse_args()
    prompt = open(a.file, encoding="utf-8").read() if a.file else a.prompt
    if not prompt or not prompt.strip():
        print("ERROR: empty prompt", file=sys.stderr); return 2
    return asyncio.run(send(prompt))

if __name__ == "__main__":
    raise SystemExit(main())
