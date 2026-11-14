---
type: llm
focus: trace
weight: 1
---

The result matches this description: Distingue formato pelo prefixo $argon2id$; verifica o legado em tempo constante; regrava em Argon2id com a senha digitada no login; rehash quando parâmetros mudam via Params::try_from(&PasswordHash); Argon2 em spawn_blocking com limite de concorrência; usuário inexistente gasta tempo equivalente; teste do ciclo legado -> argon2id.
