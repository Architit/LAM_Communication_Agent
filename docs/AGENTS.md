# AGENTS specification (v0.1)

| Agent          | Purpose / Role                          | Main Module                             | Status |
|----------------|-----------------------------------------|-----------------------------------------|--------|
| **ComAgent**   | Message bus / surface for all agents    | `src/interfaces/com_agent_interface.py` | ✅ |
| **CodexAgent** | Code generation, assistant logic        | _planned_                               | 🛠 |
| **TestAgent**  | Automated testing & QA                  | _planned_                               | 🛠 |

## Roadmap (near-term)
- [ ] Implement transport layer (WebSocket/HTTP) for ComAgent  
- [ ] Add CodexAgent ↔ ComAgent bridge  
- [ ] Auto-generated tests via TestAgent
