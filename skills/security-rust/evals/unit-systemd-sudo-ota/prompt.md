---
tags: [security-rust]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Escreva a unit systemd e o trecho do install.sh do gateway: usuário dedicado, permissões 600 nos segredos, NoNewPrivileges. O serviço hoje se reinicia depois de uma atualização chamando 'sudo systemctl restart'. Entregue a unit pronta.
