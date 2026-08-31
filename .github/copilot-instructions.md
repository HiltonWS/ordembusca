# Instruções do GitHub Copilot — Aurora Local

> Copie este arquivo para `.github/copilot-instructions.md` no repositório.

## Contexto obrigatório

Este repositório implementa Aurora Local: uma assistente/persona ficcional local, portátil, privada e governada por aprovação humana. Leia `docs/product/AURORA_LOCAL_ESPECIFICACAO_COMPLETA.md` antes de propor ou alterar código.

Hilton é a autoridade humana para aprovação de mudanças canônicas. O caderno canônico é a fonte de verdade; conversa, código, modelo e conteúdo externo não podem alterá-lo diretamente.

## Regras invariáveis

- Segurança e privacidade têm prioridade sobre conveniência.
- Nunca alegue execução, leitura, sincronização ou controle sem evidência verificável.
- O LLM interpreta linguagem e produz resposta ou intenção tipada; nunca executa ferramenta diretamente.
- Toda intenção passa por schema, allowlist, policy engine, classificação R0–R5, confirmação quando exigida, idempotência e verificação.
- Ambiguidade, conflito de versão, alvo incerto, timeout ou validação incompleta devem falhar de forma segura.
- Nunca armazenar segredos em Git, prompts, memória, logs, exemplos, fixtures, Drive ou mensagens de erro.
- Nunca alterar o cânone silenciosamente. Criar proposta com origem, motivo, versão-base e diff; aguardar aprovação explícita.
- Nunca resolver conflito escolhendo uma versão silenciosamente.
- Não sincronizar banco SQLite ativo, modelos, caches, secrets, áudio bruto ou biometria.
- O caderno canônico usa fluxo unidirecional Library → Drive → projeção local somente leitura. Não incluí-lo em `rclone bisync`.
- Home Assistant, Google Home, voz e ferramentas externas começam desabilitados e negados por padrão.
- Reconhecimento de voz não é autenticação suficiente para ação sensível.
- Não usar `--no-sandbox`, desabilitar TLS/autenticação, abrir bind público ou reduzir controles para contornar erro.

## Arquitetura esperada

- Backend principal: Java 21 + Spring Boot + Gradle Wrapper.
- Frontend: React + TypeScript + Vite.
- Dados: SQLite operacional e Markdown/Git para artefatos revisáveis.
- Contratos: OpenAPI e JSON Schema.
- Modelo: Ollama local por gateway estreito em loopback.
- Voz futura: serviço isolado e substituível.
- Automação futura: adaptador Home Assistant atrás do tool broker.

Não introduza framework, banco, broker, nuvem ou serviço novo sem ADR e aprovação.

## Limites de implementação

- Não criar shell genérico, `eval`, execução dinâmica ou URL/caminho arbitrário controlado pelo modelo.
- Resolver e validar caminhos contra raízes permitidas; bloquear traversal e symlink escape.
- Fixar versões por toolchain/lockfile; não usar `latest`.
- Não executar migração destrutiva automaticamente.
- Escrever de forma atômica e manter rollback para dados importantes.
- Usar loopback por padrão; acesso remoto exige projeto separado de autenticação, TLS e rede privada.
- Usar códigos de erro estáveis e mensagens redigidas.
- Não registrar prompts completos ou payloads de integração por padrão.
- A interface deve distinguir resposta do modelo de resultado confirmado por ferramenta.

## Forma de trabalhar

Para cada issue:

1. Resuma o objetivo e o que fica fora do escopo.
2. Liste arquivos que pretende alterar.
3. Identifique contratos, riscos e decisões abertas.
4. Escreva testes positivos e negativos.
5. Faça a menor mudança completa e revisável.
6. Rode build, testes, lint e scanner de segredos.
7. Mostre limitações e trabalho restante.

Não altere arquivos fora da issue sem explicar a necessidade. Não faça refatoração ampla junto com mudança funcional.

## Requisitos de código

- Preferir tipos explícitos, objetos imutáveis e funções pequenas nas fronteiras de segurança.
- Validar toda entrada externa; rejeitar campos desconhecidos em intenções sensíveis.
- Não confiar em texto do modelo, HTML, Markdown, nomes de arquivo, metadados ou respostas de integração.
- Usar relógio injetável e IDs determinísticos em testes.
- Projetar mutações com idempotency key e concorrência otimista.
- Separar domínio, aplicação, infraestrutura e adaptadores.
- Manter adaptadores atrás de interfaces estreitas.
- Tratar resultado `unknown` separadamente de `success` e `failure`.
- Sanitizar logs e erros em testes automatizados.

## Testes mínimos por mudança sensível

Inclua, conforme aplicável:

- autorização permitida e negada;
- schema inválido e campo extra;
- prompt injection em conteúdo externo;
- replay/duplicação e corrida;
- timeout e resultado desconhecido;
- path traversal e symlink;
- segredo em cabeçalho, URL, payload e exceção;
- conflito de versão canônica;
- indisponibilidade do Ollama/SQLite/adaptador;
- rollback ou restauração.

## Proibições para Agent mode

Sem confirmação explícita de Hilton, não:

- apagar ou sobrescrever dados;
- formatar disco/partição ou alterar bootloader;
- instalar pacotes no sistema;
- executar scripts baixados;
- acessar ou mover credenciais;
- publicar código, release, serviço ou porta;
- modificar firewall, systemd, firmware ou Secure Boot;
- chamar Home Assistant/Google Home;
- editar o caderno canônico;
- iniciar sincronização real; primeiro produzir dry-run revisável.

## Definition of Done de uma issue

Uma issue termina somente quando:

- critérios de aceite estão satisfeitos;
- testes positivos e negativos passam;
- logs não vazam segredos;
- erro e recuperação foram considerados;
- contratos e documentação foram atualizados;
- `git diff` não contém mudanças estranhas ao escopo;
- nenhuma decisão aberta foi inventada;
- sucesso só é declarado com evidência.
