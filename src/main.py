"""Entrypoint for the in-process communication bus."""

from src.interfaces.com_agent_interface import ComAgent


def main() -> None:
    bus = ComAgent()
    bus.register_agent("operator", object())
    print("lam-comm-agent ready")


if __name__ == "__main__":
    main()
