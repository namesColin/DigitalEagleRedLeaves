"""
Native Messaging Host — Chrome 启动，stdin/stdout 桥接扩展。
Agent 通过 localhost:9021 与此进程通信。
"""
import sys, json, struct, socket, threading


def read_message():
    raw = sys.stdin.buffer.read(4)
    if not raw or len(raw) < 4:
        return None
    return json.loads(sys.stdin.buffer.read(struct.unpack("=I", raw)[0]))


def write_message(msg):
    data = json.dumps(msg).encode()
    sys.stdout.buffer.write(struct.pack("=I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def main():
    pending = {}
    lock = threading.Lock()

    def pipe_server():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 9021))
        srv.listen(5)
        while True:
            conn, _ = srv.accept()
            data = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk: break
                data += chunk
                if b"\n" in data: break
            try:
                cmd = json.loads(data.decode().strip())
                with lock: pending[cmd.get("id", 0)] = conn
                write_message(cmd)
            except: pass

    threading.Thread(target=pipe_server, daemon=True).start()

    while True:
        msg = read_message()
        if msg is None: break
        if msg.get("type") == "result":
            cid = msg.get("id", 0)
            with lock: conn = pending.pop(cid, None)
            if conn:
                try:
                    conn.send(json.dumps(msg.get("result", {})).encode() + b"\n")
                    conn.close()
                except: pass


if __name__ == "__main__":
    main()
