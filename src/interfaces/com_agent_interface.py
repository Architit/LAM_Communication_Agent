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
import json
import logging
import base64
from typing import Any, Deque, Tuple
try:
    import msgpack
except ModuleNotFoundError:  # pragma: no cover - depends on environment setup
    msgpack = None

try:
    from lam_logging import log as lam_log
except ModuleNotFoundError:  # pragma: no cover - depends on embedding environment
    _fallback_logger = logging.getLogger(__name__)

    def lam_log(level: str, component: str, message: str, **fields: Any) -> None:
        log_fn = getattr(_fallback_logger, level.lower(), _fallback_logger.info)
        if fields:
            log_fn(
                "%s | %s | %s",
                component,
                message,
                json.dumps(fields, ensure_ascii=True, default=str),
            )
            return
        log_fn("%s | %s", component, message)


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


def _encode_msgpack_payload(payload: dict) -> str:
    if msgpack is not None:
        raw = msgpack.packb(payload, use_bin_type=True)
    else:
        raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _decode_msgpack_payload(payload_b64: str) -> dict:
    raw = base64.b64decode(payload_b64.encode("ascii"))
    if msgpack is not None:
        decoded = msgpack.unpackb(raw, raw=False)
    else:
        decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("decoded msgpack payload must be an object")
    return decoded


def _build_transport_envelope(payload: dict) -> dict:
    msg_type = "TASK" if payload.get("intent") else "READY"
    return {
        "msg_type": msg_type,
        "msgpack_payload": _encode_msgpack_payload(payload),
        "credit_delta": 0,
    }


def _normalize_transport_envelope(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    msg_type = data.get("msg_type")
    payload_b64 = data.get("msgpack_payload")
    if not isinstance(msg_type, str) or not isinstance(payload_b64, str):
        return data
    unpacked = _decode_msgpack_payload(payload_b64)
    unpacked["_transport"] = {"msg_type": msg_type}
    if isinstance(data.get("credit_delta"), int):
        unpacked["_transport"]["credit_delta"] = data.get("credit_delta")
    return unpacked


class ComAgent:
    """Очередь сообщений между LAM-агентами."""

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {}
        self._queue: Deque[Tuple[str, dict]] = deque()
        self._credits: dict[str, int] = {}

    # ─────── реестр ────────────────────────────────────────────────────────────
    def register_agent(self, name: str, obj: Any) -> None:
        self._registry[name] = obj
        self._credits.setdefault(name, 0)
        # низкий шум: не comm.enqueue/comm.dequeue, а отдельное событие
        lam_log("debug", "comm.registry", "register", action="register", agent=name)

    def unregister_agent(self, name: str) -> None:
        self._registry.pop(name, None)
        self._credits.pop(name, None)
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

        if self._credits.get(recipient, 0) <= 0:
            lam_log("warning", "comm.backpressure", "credit_exhausted", recipient=recipient)
            return False

        envelope = _build_transport_envelope(payload if isinstance(payload, dict) else {})
        self._queue.append((recipient, envelope))
        self._credits[recipient] = self._credits.get(recipient, 0) - 1

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

            if isinstance(data, dict):
                data = _normalize_transport_envelope(data)
                if _looks_like_reply(data):
                    data = _enforce_envelope(data)
            return sender, data

        # шум минимальный: empty не логируем (часто в тестах)
        return "", {}

    # ─────── утилита ───────────────────────────────────────────────────────────
    def log_communication(self, msg: str, level: str = "info") -> None:
        # Legacy API: пусть пишет через lam_logging
        lam_log(level.lower(), "comm.legacy", msg, message=msg)

    # ─────── credit / backpressure ────────────────────────────────────────────
    def set_credit(self, agent: str, credits: int) -> None:
        self._credits[agent] = max(0, int(credits))
        lam_log("info", "comm.credit", "set", agent=agent, credits=self._credits[agent])

    def add_credit(self, agent: str, delta: int = 1) -> int:
        self._credits[agent] = max(0, self._credits.get(agent, 0) + int(delta))
        lam_log("info", "comm.credit", "add", agent=agent, credits=self._credits[agent], delta=int(delta))
        return self._credits[agent]

    def get_credit(self, agent: str) -> int:
        return self._credits.get(agent, 0)
