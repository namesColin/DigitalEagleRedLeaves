"""
任务调度层 — 维护队列 + 串行执行 LayeredAgent。
支持取消、超时、状态查询。
"""
import asyncio, time


class TaskRunner:

    def __init__(self, brain_loop, task_timeout_steps: int = 20):
        self._agent = brain_loop
        self._queue = asyncio.Queue()
        self._busy = False
        self._cancel_flag = False
        self._current_goal = ""
        self._task_timeout_steps = task_timeout_steps
        self._last_result = None

    async def start(self):
        while True:
            goal, future = await self._queue.get()
            self._busy = True
            self._cancel_flag = False
            self._current_goal = goal
            started_at = time.time()
            try:
                result = await self._agent.run(
                    goal,
                    max_steps=self._task_timeout_steps,
                    should_abort=lambda: self._cancel_flag,
                )
                aborted = self._cancel_flag
                self._last_result = {
                    "success": result.get("success", False) and not aborted,
                    "steps": result.get("steps", 0),
                    "stats": result.get("stats", {}),
                    "aborted": aborted,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                    "log": [
                        {"step": h["step"], "action": h["action"],
                         "result": h["result"], "layer": h.get("layer", "?")}
                        for h in result.get("log", [])
                    ],
                }
            except Exception as e:
                self._last_result = {
                    "success": False,
                    "error": str(e),
                    "aborted": self._cancel_flag,
                    "elapsed_ms": int((time.time() - started_at) * 1000),
                }
            future.set_result(self._last_result)
            self._busy = False
            self._current_goal = ""

    async def submit(self, goal: str) -> dict:
        future = asyncio.get_event_loop().create_future()
        await self._queue.put((goal, future))
        return await future

    def cancel(self):
        """中止当前任务。由 IPC 层调用。"""
        self._cancel_flag = True

    def status(self) -> dict:
        return {
            "connected": self._agent.cdp.is_connected,
            "busy": self._busy,
            "current_goal": self._current_goal,
            "last_result": self._last_result,
        }

    @property
    def is_connected(self) -> bool:
        return self._agent.cdp.is_connected

    @property
    def is_busy(self) -> bool:
        return self._busy
