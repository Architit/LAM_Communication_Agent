"""
Коммуникационный агент LAM (v0.2)

⚙️  Минимальная логика:
• register_agent / unregister_agent — учёт участников.
• send_data — складывает сообщение в очередь (НЕ вызывает agent.answer).  
• receive_data — забирает следующее сообщение или {}.
• log_communication — запись в файл logs/com_agent.log

Этого достаточно, чтобы интег-тест ping-pong проходил.
"""

from collections import deque
from pathlib import Path
from typing import Any, Deque, Tuple

import logging

# ── настройка логов ────────────────────────────────────────────────────────────
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOGS_DIR / "com_agent.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class ComAgent:
    """Очередь сообщений между LAM-агентами."""

    def __init__(self) -> None:
        self._registry: dict[str, Any] = {}
        self._queue: Deque[Tuple[str, dict]] = deque()

    # ─────── реестр ────────────────────────────────────────────────────────────
    def register_agent(self, name: str, obj: Any) -> None:
        self._registry[name] = obj
        logger.info("registered %s", name)

    def unregister_agent(self, name: str) -> None:
        self._registry.pop(name, None)
        logger.info("unregistered %s", name)

    def list_agents(self) -> list[str]:
        return list(self._registry)

    # ─────── I/O ───────────────────────────────────────────────────────────────
    def send_data(self, recipient: str, payload: dict) -> bool:
        """Кладёт сообщение в очередь.

        Тесты сами вызывают `agent.answer`, поэтому здесь
        **не** преобразуем payload.
        """
        if recipient not in self._registry:
            logger.error("unknown recipient %s", recipient)
            return False

        self._queue.append((recipient, payload))
        logger.info("queued for %s: %s", recipient, payload)
        return True

    def receive_data(self) -> Tuple[str, dict]:
        """Достаёт следующее сообщение (или возвращает "", {})."""
        if self._queue:
            sender, data = self._queue.popleft()
            logger.info("dequeued from %s: %s", sender, data)
            return sender, data
        logger.warning("queue empty")
        return "", {}

    # ─────── утилита ───────────────────────────────────────────────────────────
    def log_communication(self, msg: str, level: str = "info") -> None:
        getattr(logger, level.lower(), logger.info)(msg)
