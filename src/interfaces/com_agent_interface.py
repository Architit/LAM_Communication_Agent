import logging
from pathlib import Path
from typing import Any, Deque, Tuple
from collections import deque

# Ensure the logs directory exists
Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    filename="logs/com_agent.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
)
logger = logging.getLogger(__name__)


class ComAgent:
    """Коммуникационный агент для взаимодействия между другими агентами."""

    def __init__(self) -> None:
        self.agent_registry: dict[str, Any] = {}
        self._message_queue: Deque[Tuple[str, dict]] = deque()

    def register_agent(self, agent_name: str, agent_obj: Any) -> None:
        """Регистрирует нового агента для взаимодействия."""
        self.agent_registry[agent_name] = agent_obj
        logger.info("Агент '%s' успешно зарегистрирован.", agent_name)

    def unregister_agent(self, agent_name: str) -> None:
        """Удаляет агента из реестра."""
        if agent_name in self.agent_registry:
            del self.agent_registry[agent_name]
            logger.info("Агент '%s' успешно удалён из реестра.", agent_name)
        else:
            logger.warning("Попытка удалить несуществующего агента '%s'.", agent_name)

    def list_agents(self) -> list[str]:
        """Возвращает список имён зарегистрированных агентов."""
        return list(self.agent_registry.keys())

    # ───────────────────────── I/O wrapper methods
    def input(self) -> Tuple[str, dict]:
        """Публичная точка чтения сообщений (обёртка над receive_data)."""
        return self.receive_data()

    def output(self, agent_name: str, data: dict) -> bool:
        """Публичная точка отправки сообщений (обёртка над send_data)."""
        return self.send_data(agent_name, data)

    def send_data(self, agent_name: str, data: dict) -> bool:
        """Отправляет данные указанному агенту."""
        if agent_name not in self.agent_registry:
            logger.error("Агент '%s' не зарегистрирован.", agent_name)
            return False
        try:
            # Имитация отправки: сохраняем сообщение в очередь
            self._message_queue.append((agent_name, data))
            logger.info("Данные успешно отправлены агенту %s.", agent_name)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка отправки данных агенту %s: %s", agent_name, exc)
            return False

    def receive_data(self) -> Tuple[str, dict]:
        """Получает данные от других агентов."""
        try:
            agent_name, data = self._message_queue.popleft()
            logger.info("Данные успешно получены от агента %s.", agent_name)
            return agent_name, data
        except IndexError:
            logger.warning("Очередь сообщений пуста.")
            return "", {}
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка при получении данных: %s", exc)
            return "", {}

    def log_communication(self, event: str, level: str = "INFO") -> None:
        """Записывает лог события с указанным уровнем."""
        if level == "INFO":
            logger.info(event)
        elif level == "WARNING":
            logger.warning(event)
        elif level == "ERROR":
            logger.error(event)
        else:
            logger.debug("Неизвестный уровень логирования '%s': %s", level, event)
