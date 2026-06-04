# Usar com Obsidian

O Meeting Processor escreve as reuniões em `vault/wiki/reunioes/` no
formato Markdown padrão, compatível com Obsidian e com o ecossistema
[claude-obsidian](https://github.com/) (wiki / index / hot / log).

## 1. Instalar o Obsidian

Baixe em <https://obsidian.md/download> (Windows / macOS / Linux).

## 2. Abrir o vault

1. Abra o Obsidian.
2. Clique em "Open folder as vault".
3. Selecione a pasta `vault/` deste repositório.

## 3. Plugins recomendados

Vá em **Settings → Community plugins → Browse** e instale:

| Plugin                | Para quê                                                    |
|-----------------------|-------------------------------------------------------------|
| **Kanban**            | Renderiza `Tarefas - *.md` como quadro Kanban arrastável.   |
| **Calendar**          | Mostra reuniões por data (criadas com frontmatter `created`). |
| **Banners** (opcional)| Capa visual das notas.                                      |

Os plugins já estão pré-configurados em `vault/.obsidian/plugins/`, então
provavelmente o Obsidian vai apenas pedir para habilitá-los.

## 4. Estrutura criada

Cada reunião gera uma pasta com 4 arquivos:

```
vault/wiki/reunioes/2026-05-07 14h30 - Reuniao com X/
├── 2026-05-07 14h30 - Reuniao com X.md         # nó central no grafo
├── Resumo - 2026-05-07 14h30 - Reuniao com X.md
├── Tarefas - 2026-05-07 14h30 - Reuniao com X.md   # vira Kanban
└── Transcricao - 2026-05-07 14h30 - Reuniao com X.md
```

Você pode renomear a pasta (e o `.md` central de mesmo nome) sem quebrar
nada — o grafo do Obsidian acompanha.

## 5. Dashboard ao vivo no Obsidian

Enquanto o watcher roda (`python -m meeting_processor watch`), o arquivo
`vault/wiki/reunioes/Dashboard.md` é atualizado em tempo real com:

- Status do watcher (ATIVO/OFFLINE).
- Job em processamento, com barra de progresso por etapa.
- Histórico das últimas execuções.

Abra esse arquivo no Obsidian e deixe num painel lateral.

## 6. Não usar Obsidian

Se preferir não instalar Obsidian, use o frontend local:

```bash
python -m meeting_processor web
```

Veja [`frontend-local.md`](frontend-local.md).
