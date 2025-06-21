"""
interfaces/com_agent_interface.py
Простейший «коммуникационный» агент-шлюз между несколькими агентами
(в нашем случае — между тестовым скриптом и Codex-агентом).

• register_agent(name, obj) — регистрируем объект-агент.
• send_data(to, payload)    — шлём сообщение; если у целевого
  объекта есть метод ``answer`` — вызываем его и кладём результат
  в очередь входящих.
• receive_data()            — читаем очередной ответ (FIFO).

Этого поведения достаточно, чтобы тест
``tests/it/test_agents_ping_pong.py`` стал зелёным.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Tuple


class ComAgent:
    """Минимальный коммуникационный менеджер."""

    def __init__(self) -> None:
        # зарегистрированные под-агенты
        self._agents: Dict[str, Any] = {}
        # очередь (отправитель, данные)
        self._inbox: deque[Tuple[str, Dict[str, Any]]] = deque()

    # ────────────────────────────────────────────
    def register_agent(self, name: str, agent: Any) -> None:
        self._agents[name] = agent

    # ────────────────────────────────────────────
    def send_data(self, to: str, payload: Dict[str, Any]) -> bool:
        """
        Посылает ``payload`` агенту *to*.

        • Если у целевого объекта есть метод ``answer`` —
          сразу вызываем его и кладём результат в ``_inbox``;
        • иначе просто проксируем исходное сообщение.

        Возвращает *True*, если адресат известен.
        """
        agent = self._agents.get(to)
        if agent is None:
            return False

        # если у агента есть «умный» ответ
        if hasattr(agent, "answer"):
            reply = agent.answer(payload)
            self._inbox.append((to, reply))
        else:
            # эхо-поведение
            self._inbox.append((to, payload))

        return True

    # ────────────────────────────────────────────
    def receive_data(self) -> Tuple[str, Dict[str, Any]]:
        """
        Блокирующего ожидания нет — просто читаем очередной
        элемент или бросаем IndexError, если очередь пуста.
        """
        return self._inbox.popleft()
