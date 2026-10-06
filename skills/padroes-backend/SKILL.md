---
name: padroes-backend
description: Padrões gerais de backend da equipe, válidos para Go, Fastify e AdonisJS — arquitetura, API, erros, segurança, dados e testes.
---

# Padrões de backend

> As convenções já existentes no projeto têm prioridade. Estas regras valem quando o projeto não define.
> Carregue também a skill da stack: `backend-go`, `backend-fastify` ou `backend-adonisjs`.

## Arquitetura
- Camadas: **transporte** (HTTP/handlers) → **serviço** (regra de negócio) → **repositório** (dados). Regra de negócio não conhece HTTP nem SQL.
- Dependências injetadas, não globais. Configuração via variáveis de ambiente validadas na inicialização.

## API
- REST com recursos no plural (`/users/:id`), JSON, `camelCase` nos payloads (ou o padrão do projeto).
- Validação de entrada **na borda**, com schema.
- Erros em formato único: `{ "error": { "code": "USER_NOT_FOUND", "message": "...", "details": {} } }`, com status HTTP correto (400 validação, 401, 403, 404, 409 conflito, 422, 500).
- Paginação por cursor ou `limit/offset` consistente; nunca retornar listas sem limite.
- Versionar quando houver quebra de contrato.

## Segurança
- Nunca confie no cliente: autorização checada no servidor em cada operação.
- Queries parametrizadas sempre. Segredos só via ambiente.
- Não logar senhas, tokens, documentos pessoais (LGPD).
- Rate limiting em rotas públicas e de autenticação.

## Dados
- Migrations versionadas e reversíveis. Índices para colunas de busca/junção.
- Transações em operações que alteram mais de uma entidade.

## Observabilidade
- Logs estruturados (JSON) com request id. Endpoint `/health`.

## Testes
- Unitários para regra de negócio; integração para rotas + banco (banco de teste real ou container, não mock do ORM).
- Todo bug corrigido ganha um teste de regressão.
