---
tags: [security-rust]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

O login da UI do gateway guarda a senha como SHA-256 hex. Migre para Argon2id sem obrigar ninguém a trocar a senha e sem quebrar quem já está logando. Crate argon2 0.6 já está no Cargo.toml.
