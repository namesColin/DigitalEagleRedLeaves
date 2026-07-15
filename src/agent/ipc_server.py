"""
IPC 层 — HTTP API + 扩展命令队列。
"""
import asyncio, json
from aiohttp import web


class IpcServer:

    def __init__(self, task_runner, port: int = 9020):
        self._runner = task_runner
        self._port = port
        self._cmd_queue = asyncio.Queue()
        self._result_pending = {}
        self._app = web.Application()
        self._app.router.add_post("/run", self._handle_run)
        self._app.router.add_post("/cancel", self._handle_cancel)
        self._app.router.add_get("/status", self._handle_status)
        self._app.router.add_get("/pop", self._handle_pop)
        self._app.router.add_post("/push", self._handle_push)

    async def start(self):
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", self._port)
        await site.start()
        print(f"  [IPC] http://127.0.0.1:{self._port}")

    async def _handle_run(self, req):
        try:
            body = await req.json()
            g = body.get("goal", "").strip()
            if not g: return web.json_response({"error": "empty goal"}, status=400)
            return web.json_response(await self._runner.submit(g))
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_cancel(self, req):
        self._runner.cancel(); return web.json_response({"cancelled": True})

    async def _handle_status(self, req):
        s = self._runner.status(); s["queue"] = self._cmd_queue.qsize(); return web.json_response(s)

    async def _handle_pop(self, req):
        cmds = []
        while True:
            try:
                cmds.append(self._cmd_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return web.json_response(cmds)

    async def _handle_push(self, req):
        try:
            body = await req.json()
            fut = self._result_pending.pop(body.get("id", 0), None)
            if fut and not fut.done(): fut.set_result(body.get("result", {}))
            return web.json_response({"ok": True})
        except: return web.json_response({"error": "parse"}, status=500)

    async def send_command(self, cmd: dict, timeout: float = 15) -> dict:
        fut = asyncio.get_event_loop().create_future()
        self._result_pending[cmd["id"]] = fut
        await self._cmd_queue.put(cmd)
        try: return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._result_pending.pop(cmd["id"], None); return {"error": "timeout"}
