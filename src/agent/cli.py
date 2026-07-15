"""
CLI 客户端 — HTTP 请求 daemon，打印结果。
支持 run / status / cancel。
"""
import sys, json, urllib.request

DAEMON_URL = "http://127.0.0.1:9020"


def _post(path: str, data: dict | None = None) -> dict:
    body = json.dumps(data or {}).encode() if data else None
    req = urllib.request.Request(
        f"{DAEMON_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{DAEMON_URL}{path}", timeout=5) as resp:
        return json.loads(resp.read())


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m agent.cli <goal>")
        print("       python -m agent.cli --status")
        print("       python -m agent.cli --cancel")
        return

    arg = sys.argv[1]

    if arg == "--status":
        try:
            s = _get("/status")
            print(f"Connected: {s.get('connected')}  Busy: {s.get('busy')}")
            if s.get("current_goal"):
                print(f"Current goal: {s['current_goal'][:80]}")
        except Exception as e:
            print(f"Daemon not reachable: {e}")
        return

    if arg == "--cancel":
        try:
            r = _post("/cancel")
            print("Cancelled" if r.get("cancelled") else "Failed")
        except Exception as e:
            print(f"Error: {e}")
        return

    goal = " ".join(sys.argv[1:])
    try:
        result = _post("/run", {"goal": goal})
        if result.get("aborted"):
            print("ABORTED")
        elif result.get("success"):
            print(f"OK ({result.get('steps', '?')} steps)")
        else:
            print(f"FAIL" + (f" ({result.get('steps', '?')} steps)" if result.get("steps") else ""))
        if result.get("error"):
            print(f"Error: {result['error']}")
        if result.get("stats"):
            print(f"Layers: {result['stats']}")
        for h in result.get("log", []):
            print(f"  Step {h['step']}: [{h.get('layer','?')}] {h['action']} - {h['result'][:80]}")
    except Exception as e:
        print(f"Error: {e}")
        print("Is daemon running? python -m agent.daemon")


if __name__ == "__main__":
    main()
