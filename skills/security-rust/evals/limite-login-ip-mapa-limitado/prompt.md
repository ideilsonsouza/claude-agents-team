---
tags: [security-rust]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

No gateway em axum 0.8, o POST /login precisa limitar tentativas por IP. Desenhe e implemente o limitador (pode ser um módulo novo) e diga como o IP é obtido. O gateway roda direto na LAN do cliente, sem proxy.
