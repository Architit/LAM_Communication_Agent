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
        "errors", "tokens", "usage", "result", "error", "metrics",
    }
    return any(k in payload for k in markers)


def _enforce_envelope(reply: dict) -> dict:
    # Envelope Standard v1: status/context/result/error/metrics всегда есть
    reply.setdefault("status", "ok")

    ctx = reply.get("context")
    if not isinstance(ctx, dict):
        ctx = {}
    reply["context"] = ctx

    reply.setdefault("result", reply.get("result"))
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
        # низкий шум: не comm.enqueue/comm.dequeue
        lam_log("comm.registry", action="register", agent=name)

    def unregister_agent(self, name: str) -> None:
        self._registry.pop(name, None)
        lam_log("comm.registry", action="unregister", agent=name)

    def list_agents(self) -> list[str]:
        return list(self._registry)

    # ─────── I/O ───────────────────────────────────────────────────────────────
    def send_data(self, recipient: str, payload: dict) -> bool:
        """Кладёт сообщение в очередь.

        Тесты сами вызывают `agent.answer`, поэтому здесь
        **не** преобразуем payload.
        """
        if recipient not in self._registry:
            # comm.enqueue (ошибка) — минимально и структурно
            lam_log("comm.enqueue", status="error", recipient=recipient, error="unknown_recipient")
            return False

        self._queue.append((recipient, payload))

        ctx = payload.get("context") if isinstance(payload, dict) else None
        if not isinstance(ctx, dict):
            ctx = {}

        # comm.enqueue — JSONL + авто-inject контекста (если есть ContextVar)
        lam_log(
            "comm.enqueue",
            status="ok",
            recipient=recipient,
            intent=payload.get("intent") if isinstance(payload, dict) else None,
            task_id=ctx.get("task_id"),
            trace_id=ctx.get("trace_id"),
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

            # comm.dequeue — JSONL + фильтрация через env (LAM_LOG_LEVEL/LAM_LOG_EVENTS)
            lam_log(
                "comm.dequeue",
                sender=sender,
                status=status,
                task_id=ctx.get("task_id"),
                trace_id=ctx.get("trace_id"),
            )

            if isinstance(data, dict) and _looks_like_reply(data):
                data = _enforce_envelope(data)
            return sender, data

        # шум минимальный: empty не логируем (часто в тестах)
        return "", {}

    # ─────── утилита ───────────────────────────────────────────────────────────
    def log_communication(self, msg: str, level: str = "info") -> None:
        # Legacy API: пусть пишет через lam_logging
        lam_log("comm.legacy", level=level.lower(), message=msg)
