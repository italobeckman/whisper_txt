# Workflow de Implementação para IAs — Projeto whisper_txt

> **Propósito:** este documento define o padrão obrigatório que qualquer IA (ou dev assistido por IA) deve seguir para dar continuidade à implementação do app, conforme as issues do backlog.
> **Auditoria:** toda execução deve passar por este fluxo do início ao fim, sem atalhos.

---

## 1. Princípios

- **`dev` é a branch de integração.** Toda branch de trabalho nasce de `dev` e todo merge volta para `dev`. `main` só recebe merge em marcos de entrega, nunca no dia a dia.
- **Uma issue por vez.** A IA pega uma issue do backlog, resolve, fecha e só então parte para a próxima (issues correlatas podem compartilhar branch, conforme §3).
- **A issue é a fonte da verdade.** Objetivo, Contexto, Critérios de Aceite e Comando de Verificação da issue definem o que é "resolvido". Não inventar escopo.
- **Verificação antes de fechar.** Nada de "está pronto" sem rodar o Comando de Verificação da issue e comprovar no comentário.
- **Rastreabilidade total.** Branch → commits → comentário na issue → merge → close: tudo ligado à issue correspondente.

---

## 2. Preparação do ambiente (só na primeira execução)

```bash
# 1. Garantir que existe a branch base dev (se ainda não existir)
git switch main
git pull origin main
git checkout -b dev
git push -u origin dev

# 2. Na máquina local, a partir daqui SEMPRE trabalhar em dev como base
git switch dev
git pull origin dev
```

> Se a `dev` já existir no repositório, pular a criação e apenas `git switch dev && git pull`.

Dependências do projeto: `uv sync`. As ferramentas de verificação (`pyflakes`, `pytest`) rodam via `uvx`/`uv run --with`, sem alterar o `pyproject.toml`.

---

## 3. Convenção de branches

- **Base:** sempre `dev` (nunca `main`, nunca outra branch de feature).
- **Padrão de nome:** `<tipo>/<numero-github>-<slug-curto>`
  - `<tipo>`: `feat` | `fix` | `chore` | `test` | `docs` | `refactor` | `perf`
  - `<numero-github>`: número da issue no GitHub (ex.: #2 → `2`)
  - `<slug-curto>`: 2–4 palavras do título, separadas por `-`

**Exemplos:**

- Issue #2 (`fix(core): importar is_audio_file ausente...`) → `fix/2-import-is-audio-file`
- Issue #10 (`feat(core): detecção real do backend e modo CPU...`) → `feat/10-backend-modo-cpu`

**Issues correlatas** podem compartilhar a mesma branch (mesmo grupo de correlação do backlog, ex.: #8 + #9, layout e atalhos da TUI). Nesse caso o nome usa o intervalo ou o número da principal: `feat/8-9-tui-layout-atalhos`.

> **Regra de ouro:** o nome da branch sempre contém o número da issue no GitHub, para o GitHub vincular a branch à issue automaticamente.

---

## 4. Ciclo completo de implementação (passo a passo)

### Etapa A — Iniciar

```bash
git switch dev
git pull origin dev                         # dev sempre atualizada
git checkout -b fix/2-import-is-audio-file  # branch nova a partir de dev
```

- Ler a issue inteira (Objetivo, Contexto, Critérios, Comando de Verificação, Arquivos Prováveis).
- Conferir a linha `**Depende de:** #N`. Se a dependência não estiver mergeada em `dev`, **não começar**: reportar e aguardar.

### Etapa B — Implementar

- Implementar a solução em um ou mais commits (quantos forem necessários para a resolução perfeita: commit por unidade lógica, mensagens descritivas, ver §5).
- Não misturar escopo de outras issues na mesma branch.

### Etapa C — Reanálise do implementado (auto-revisão obrigatória)

Reanalisar o próprio trabalho antes de comentar/fechar:

- [ ] Rodei o **Comando de Verificação** da issue e ele passou? (ou o equivalente manual/teste)
- [ ] Todos os **Critérios de Aceite** foram atendidos? (checar um a um)
- [ ] **Análise estática limpa?** `uvx pyflakes cli.py config.py core tui scripts` sem avisos.
- [ ] Segui a **arquitetura atual**? `core/` não depende de `tui/` nem de `cli.py`; `cli.py` e `tui/` são só interfaces; caminhos, URLs e downloads ficam em `config.py`; nada de `print` alcançável durante a TUI.
- [ ] Não quebrei nada que já estava em `dev`? Rodar a suíte inteira: `uv run --with pytest --with pytest-asyncio python -m pytest -q` (ou `uv run python -m unittest discover tests`).
- [ ] Não deixei código morto, TODO solto, segredos/tokens hardcoded ou arquivos desnecessários (binários em `bin/`, modelos em `models/`, WAVs temporários)?
- [ ] Mensagens de commit claras e convencionais?

> Se encontrei problema na reanálise: corrigi com **novo commit** na mesma branch (nunca fecho com pendência).

### Etapa D — Comentar a implementação na issue

Comentar na issue (seguindo o template da §6) com:

- Branch usada + hash(es) do(s) commit(s)
- Resumo do que foi implementado
- Validação (comandos rodados e saída/resultado)

### Etapa E — Fechar a issue

Fechar a issue **somente** após:

1. Reanálise OK (Etapa C)
2. Comentário de implementação postado (Etapa D)
3. A branch já ter sido **mergeada em `dev`** (Etapa F). A ordem correta é **merge → close**. Fechar antes do merge quebra a rastreabilidade.

> **Alternativa aceitável:** fechar com `Closes #N` no corpo do PR, para o GitHub fechar automaticamente no merge.

### Etapa F — Merge para `dev`

```bash
git push -u origin fix/2-import-is-audio-file
```

- Abrir PR para `dev`: título e corpo referenciando a issue (`Closes #2`), resumo das mudanças e resultado da verificação.
- Aguardar o merge do PR em `dev` (por humano ou por regra do grupo, ver §7). Após o merge, fechar a issue se ainda não foi fechada.
- **Limpeza:** deletar a branch remota após o merge (`git push origin --delete fix/2-import-is-audio-file`).

---

## 5. Convenção de commits

- **Formato (Conventional Commits):** `<tipo>(<escopo>): <descrição> (#NúmeroDaIssue)`
  - `fix(core): importa is_audio_file em cli e tui (#2)`
  - `feat(tui): adiciona cancelamento da transcrição (#5)`
  - `chore(infra): fixa versão do uv no Dockerfile (#14)`
- **Escopo:** área afetada (`core`, `audio`, `transcriber`, `config`, `cli`, `tui`, `tests`, `infra`, `scripts`, `docs`).
- **Referencie a issue em todos os commits** da branch (ex.: `(#2)`) para rastreabilidade.
- **Corpo do commit** quando necessário: explica o *porquê*, não o *o quê*.
- **Proibido:** commit gigante "wip", commit com várias issues, commit sem mensagem.

---

## 6. Template do comentário de implementação (colar na issue)

````markdown
Branch: `{branch}` | Commit(s): `{hash}`

## Resumo

{2–5 linhas: o que foi feito, decisões, desvios do plano}

## Validação

```bash
{comando(s) executados para comprovar — o Comando de Verificação da issue}
{saída/resultado}
```
````

---

## 7. Regras de merge e revisão

1. **PR para `dev` é o caminho de merge** (merges diretos para `dev` sem PR só em casos triviais, documentados e com ciência do grupo).
2. **Code review cruzado:** todo PR deve ser revisado por **pelo menos 1 dev diferente do autor** antes do merge. Uma IA nunca mergeia o próprio PR.
3. **CI como gate** (quando houver CI configurado): PR não mergeável com CI vermelho.
4. **Conflitos:** resolver a partir da `dev` local (`git switch dev && git pull && git switch -` e rebase/merge). Nunca forçar push na `dev` (`--force` proibido em `dev` e `main`).
5. **`main`:** recebe merge apenas em marcos de entrega, via PR revisado por todo o grupo.

---

## 8. O que NÃO fazer

- ❌ Branch a partir de `main` ou de outra branch de feature
- ❌ Push direto para `dev`/`main` sem PR (fora exceção documentada)
- ❌ `git push --force` em branches compartilhadas
- ❌ Fechar issue sem rodar/registrar a verificação
- ❌ Fechar issue antes do merge em `dev`
- ❌ Implementar issue cuja dependência (`Depende de: #N`) não está em `dev`
- ❌ Commitar segredos (`.env`, tokens de API/Hugging Face) ou artefatos grandes (`bin/`, `models/`, áudios de teste). Ver `.gitignore`
- ❌ Alterar `pyproject.toml`/`uv.lock` (dependências) fora do escopo da issue sem registrar no comentário

---

## 9. Quando a IA deve PARAR e reportar (não "resolver de qualquer jeito")

- A issue depende de outra que ainda não foi mergeada em `dev`.
- O Comando de Verificação falha e a causa foge do escopo da issue (ex.: bug em outra parte do código, binário `whisper-cli` ou driver Vulkan).
- A implementação exige uma decisão não resolvida (ex.: trocar o modelo/preset padrão, adicionar dependência nova, mudar o formato do `.txt` de saída, mudar a fonte de download do binário).
- Há conflito entre o que a issue pede e o que já existe em `dev` (ex.: API de outro módulo que mudou).
- O escopo da issue é grande demais para uma execução. **Não** partir em duas issues: reportar e sugerir desmembramento.

Nesses casos: comentar na issue o bloqueio (template acima, com o motivo), **não** fechar, e aguardar orientação.

---

## 10. Resumo visual do fluxo

```
dev ──► branch <tipo>/<N-github>-<slug> ──► commits ──► reanálise ──► comentário na issue
   ▲                                                                        │
   └──────────── close da issue ◄──── merge (PR para dev) ◄─────────────────┘
```

**Ordem final (não inverter):** branch → commits → verificação/reanálise → comentário → **merge em `dev` → close da issue**.

---

*Documento vivo: atualizar junto com as decisões do grupo. Introduzido pela issue #16.*
