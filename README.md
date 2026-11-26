# qrs - Autonomous Quant Research System

Research platform for discovering and validating crypto market behaviors under a
reproducible statistical protocol. Research and paper trading only; no live orders.

- Spec: [docs/autonomous-quant-research-plan.md](docs/autonomous-quant-research-plan.md)
- Protocol: [protocol/protocol.yaml](protocol/protocol.yaml)
- Development guide: [CLAUDE.md](CLAUDE.md)

```bash
uv sync
uv run pytest
uv run qrs info
```

Status: P0 complete (protocol 1.2 frozen 2026-11-26). P1 (data foundation) planning.
