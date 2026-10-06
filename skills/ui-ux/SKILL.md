---
name: ui-ux
description: Princípios de UI/UX da equipe — hierarquia visual, layout, estados de interface, formulários, feedback, responsividade e acessibilidade WCAG 2.2 AA.
---

# UI/UX

## Hierarquia e layout
- Uma ação principal por tela, visualmente dominante. Ações secundárias com menos peso.
- Agrupe por proximidade; alinhe em grade; espaço em branco é estrutura, não desperdício.
- Leitura: linhas de texto com 60–80 caracteres; contraste de tamanho e peso para títulos.

## Estados (toda tela e componente que depende de dados)
- **Carregando**: skeleton no formato do conteúdo (spinner só para ações curtas).
- **Vazio**: explica o que é e oferece a primeira ação.
- **Erro**: diz o que aconteceu em linguagem humana e como resolver; oferece tentar de novo.
- **Sucesso**: confirmação discreta (toast) sem bloquear o fluxo.

## Formulários
- Label visível sempre (placeholder não é label). Campos agrupados logicamente.
- Validação ao sair do campo e no envio; mensagem junto ao campo, específica ("CPF deve ter 11 dígitos").
- Botão de envio com estado de carregamento e proteção contra duplo clique. Preserve os dados digitados em caso de erro.
- Use o tipo de input certo (`email`, `tel`, `inputmode="numeric"`) e `autocomplete`.

## Feedback e interação
- Toda ação responde em até 100 ms (mesmo que seja só um estado visual).
- Ações destrutivas pedem confirmação ou oferecem desfazer.
- Animações curtas (150–300 ms), com propósito, respeitando `prefers-reduced-motion`.

## Responsividade
- Mobile first. Alvos de toque ≥ 44×44 px. Sem rolagem horizontal. Teste em 360 px, 768 px e 1280 px.

## Acessibilidade (WCAG 2.2 AA — obrigatório)
- HTML semântico (`button` para ação, `a` para navegação, landmarks, um `h1` por página, títulos em ordem).
- Tudo operável por teclado, com **foco visível** e ordem lógica; modais prendem e devolvem o foco.
- Contraste: 4,5:1 texto normal, 3:1 texto grande e elementos de interface.
- Imagens com `alt` significativo (ou vazio se decorativas). Ícone-botão com `aria-label`.
- Cor nunca é o único indicador (erro = cor + ícone + texto).
- Erros de formulário anunciados (`aria-live` / `aria-describedby`).

## Escrita na interface
- Verbos claros nos botões ("Salvar alterações", não "OK"). Linguagem do usuário, sem jargão técnico. Consistência de termos.
