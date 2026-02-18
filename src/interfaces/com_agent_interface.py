"""
Коммуникационный агент LAM (v0.2)

⚙️  Минимальная логика:
• register_agent / unregister_agent — учёт участников.
• send_data — складывает сообщение в очередь (НЕ вызывает agent.answer).
• receive_data — забирает следующее сообщение или {}.
• log_communication — запись события через lam_logging (JSONL)

Этого достаточно, чтобы интег-тест ping-pong проходил.
"""

from collections import deque
from typing import Any, Deque, Tuple

from lam_logging import log as lam_log


def _looks_like_reply(payload: dict) -> bool:
    # не трогаем обычные task payload
    markers = {
        "status", "provider_used", "latency_ms", "attempts", "selected_chain",
        "errors", "tokens", "usage", "reply", "result", "error", "metrics",
    }
    return any(k in payload for k in markers)


def _enforce_envelope(reply: dict) -> dict:
    # Envelope Standard v1: status/context/result/error/metrics всегда есть
    reply.setdefault("status", "ok")

    ctx = reply.get("context")
    if not isinstance(ctx, dict):
        ctx = {}
    reply["context"] = ctx

    if "result" not in reply:
        if "reply" in reply:
            reply["result"] = {"reply": reply.get("reply")}
        else:
            reply["result"] = reply.get("result")
    
    reply.setdefault("error", None)
    reply.setdefault("metrics", {})

    if reply.get("status") != "ok" and reply.get("error") is None:
        reply["error"] = {"message": "unknown error"}

    return reply


class ComAgent:
    """Очередь сообщений между LAM-агентами."""

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {}
        self._queue: Deque[Tuple[str, dict]] = deque()

    # ─────── реестр ────────────────────────────────────────────────────────────
    def register_agent(self, name: str, obj: Any) -> None:
        self._registry[name] = obj
        # низкий шум: не comm.enqueue/comm.dequeue, а отдельное событие
        lam_log("debug", "comm.registry", "register", action="register", agent=name)

    def unregister_agent(self, name: str) -> None:
        self._registry.pop(name, None)
        lam_log("debug", "comm.registry", "unregister", action="unregister", agent=name)

    def list_agents(self) -> list[str]:
        return list(self._registry)

    # ─────── I/O ───────────────────────────────────────────────────────────────
    def send_data(self, recipient: str, payload: dict) -> bool:
        """Кладёт сообщение в очередь.

        Тесты сами вызывают `agent.answer`, поэтому здесь
        **не** преобразуем payload.
        """
        if recipient not in self._registry:
            lam_log("error", "comm.enqueue", "unknown recipient", recipient=recipient, error="unknown_recipient")
            return False

        self._queue.append((recipient, payload))

        ctx = payload.get("context") if isinstance(payload, dict) else None
        if not isinstance(ctx, dict):
            ctx = {}

        lam_log(
            "info",
            "comm.enqueue",
            "enqueue",
            recipient=recipient,
            intent=payload.get("intent") if isinstance(payload, dict) else None,
            task_id=ctx.get("task_id"),
            trace_id=ctx.get("trace_id"),
            parent_task_id=ctx.get("parent_task_id"),
            span_id=ctx.get("span_id"),
        )
        return True

    def receive_data(self) -> Tuple[str, dict]:
        """Достаёт следующее сообщение (или возвращает "", {})."""
        if self._queue:
            sender, data = self._queue.popleft()

            status = data.get("status") if isinstance(data, dict) else None
            ctx = data.get("context") if isinstance(data, dict) else None
            if not isinstance(ctx, dict):
                ctx = {}

            lam_log(
                "info",
                "comm.dequeue",
                "dequeue",
                sender=sender,
                status=status,
                task_id=ctx.get("task_id"),
                trace_id=ctx.get("trace_id"),
                parent_task_id=ctx.get("parent_task_id"),
                span_id=ctx.get("span_id"),
            )

            if isinstance(data, dict) and _looks_like_reply(data):
                data = _enforce_envelope(data)
            return sender, data

        # шум минимальный: empty не логируем (часто в тестах)
        return "", {}

    # ─────── утилита ───────────────────────────────────────────────────────────
    def log_communication(self, msg: str, level: str = "info") -> None:
        # Legacy API: пусть пишет через lam_logging
        lam_log(level.lower(), "comm.legacy", msg, message=msg)
