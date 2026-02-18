from interfaces.com_agent_interface import ComAgent


def test_comm_agent_preserves_span_and_parent_ids() -> None:
    c = ComAgent()

    payload = {
        "intent": "chat",
        "context": {
            "trace_id": "t",
            "task_id": "a",
            "parent_task_id": "p",
            "span_id": "s",
        },
        "status": "ok",
        "result": {"ok": True},
        "metrics": {},
    }

    c.register_agent("x", object())
    assert c.send_data("x", payload)

    _, out = c.receive_data()
    ctx = out.get("context", {})

    assert ctx.get("trace_id") == "t"
    assert ctx.get("task_id") == "a"
    assert ctx.get("parent_task_id") == "p"
    assert ctx.get("span_id") == "s"
