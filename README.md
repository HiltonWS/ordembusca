# Ordem Paranormal — Detector de Mecânicas em Tempo Real

![CI](https://github.com/SEU_USUARIO/ordem-mecanicas/actions/workflows/ci.yml/badge.svg)

Sistema **100% local** que, a partir dos livros e PDFs de Ordem Paranormal,
reconhece na fala da mesa *quais mecânicas estão sendo usadas* (perícias,
rituais, condições, recursos) e mostra a regra e a página de referência.

> **Aviso legal:** este repositório contém apenas **código**. Os livros de
> Ordem Paranormal são material com direitos autorais e **não são (nem devem
> ser) versionados aqui** — cada pessoa ingere seus próprios PDFs localmente
> com `ingest.py`. O `.gitignore` já bloqueia `*.pdf` e `*.db`.

Este repositório está **completo nas três fases** — ingestão, voz e web —
todas funcionais e testadas. Roda inteiramente na sua máquina.

---

## O que já funciona

1. **Ingestão** de PDFs e TXT → limpa marca d'água, junta palavras quebradas
   por hífen, divide em chunks com página e seção.
2. **Léxico automático** de mecânicas:
   - **Rituais** extraídos dos livros pelo padrão `Nome / ELEMENTO Círculo`
     (ex.: *Sopro do Caos — Energia 2*), com página.
   - **Perícias, condições, recursos e atributos** canônicos do sistema.
3. **Busca full-text** (SQLite FTS5, sem acento) para trazer o texto da regra.
4. **Detector** que recebe uma frase (a fala transcrita) e casa, com
   tolerância a erros de transcrição (fuzzy), contra o léxico — devolvendo
   a mecânica, categoria, elemento/círculo e a referência (livro + página).

### Números da ingestão atual
- 3 fontes · 897 chunks · 153 termos de léxico
- **81 rituais** detectados automaticamente, 27 perícias, 34 condições

---

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

**Ingerir fontes** (aceita arquivos ou pastas; rode de novo para adicionar mais):

```bash
python ingest.py "Livro_de_Regras.pdf" "Sobrevivendo_ao_Horror.pdf" homebrew.txt
python ingest.py minha_pasta_de_livros/        # ingere tudo da pasta
python ingest.py --force livro.pdf              # reprocessa uma fonte
```

**Detectar mecânicas numa frase** (simula o que a voz vai enviar):

```bash
python query.py "o ocultista gasta 4 PE e conjura Presença do Medo, todos rolam Vontade ou ficam apavorados"
```

Saída:
```
● RITUAL    Presença do Medo [Medo 4]  (100%) — Livro de Regras p.149
    ↳ Você se torna um receptáculo para o Medo puro, emanando ondas de pavor...
● PERICIA   Vontade  (100%) — Livro de Regras p.20
● RECURSO   PE  (100%)
● CONDICAO  Apavorado  (94.7%) — Livro de Regras p.55
```

**Busca livre no texto das regras:**

```bash
python query.py --search "exposição paranormal"
```

**Ouvir a mesa ao vivo (Fase 2 — voz):**

```bash
python listen.py --list-mics             # descobrir o índice do microfone
python listen.py --mic                    # ouvir o microfone em tempo real
python listen.py --wav sessao.wav         # testar com uma gravação primeiro
python listen.py --mic --model medium --device cuda   # modelo maior em GPU
```

Na 1ª execução o modelo do Whisper (`small` por padrão) é baixado
automaticamente e fica em cache — depois roda **offline**. Cada fala é
segmentada por VAD, transcrita e analisada; as mecânicas aparecem no
terminal com cor por categoria e a página do livro.

Dica: teste com `--wav` de um trecho gravado antes de depender do microfone
ao vivo — o pipeline é o mesmo.

**Página web ao vivo (Fase 3):**

```bash
python server.py --mic                 # ouve o microfone e transmite pra web
python server.py --wav sessao.wav      # processa uma gravação
python server.py --demo                # sem áudio: só o painel + teste por texto
```

Abra **http://localhost:8000**. A página mostra, lado a lado, a transmissão
(transcrição rolando com timestamp) e os **cards de mecânica** — cada um
codificado pela cor do elemento do ritual (Sangue, Morte, Conhecimento,
Energia, Medo) ou pela categoria, com o **resumo da regra** e a página do
livro.

No rodapé há um campo de texto: digite uma fala e veja a detecção na hora
(útil para testar sem microfone, ou para o mestre lançar mecânicas manualmente).

---

## Estrutura

```
ordem/
  extract.py   extração + limpeza (PDF/TXT), normalização de termos
  chunk.py     divisão em chunks com página/seção
  lexicon.py   extração de rituais + termos canônicos do sistema
  db.py        SQLite + FTS5: schema, ingestão, busca, contexto
  detect.py    detecção fuzzy de mecânicas na fala (tempo real)
  audio.py     captura (microfone/WAV) + segmentação por VAD
  stt.py       transcrição local com faster-whisper
  pipeline.py  orquestração áudio → STT → detecção (Event)
ingest.py      CLI de ingestão
query.py       CLI de detecção/busca (sem áudio)
listen.py      CLI de escuta ao vivo (microfone ou WAV)
server.py      servidor web (FastAPI + WebSocket)
web/index.html painel ao vivo (transmissão + cards de mecânica)
```

O banco (`ordem.db`) guarda `sources`, `chunks`, `chunks_fts` e `lexicon`.
Dedup por SHA-256 evita reingerir o mesmo arquivo.

---

## Arquitetura completa (tempo real, tudo local)

```
🎤 microfone ─► VAD (webrtcvad) ─► faster-whisper (STT pt-BR)
                                        │ trecho de fala transcrito
                                        ▼
                              detect.Detector  ◄── lexicon (ordem.db)
                                        │ mecânicas reconhecidas
                                        ▼
                        FastAPI + WebSocket ──► 🌐 página web
                                                 (transcrição ao vivo +
                                                  cards de mecânica com
                                                  regra e página do livro)
```

O núcleo (ingestão + `Detector`) e a voz já estão prontos. Falta plugar:

### Fase 2 — Voz ✅ (pronta)
- `faster-whisper` (modelo `small`/`medium`, roda offline após 1º download)
  transcreve em blocos curtos.
- `sounddevice` + `webrtcvad` capturam o microfone e cortam silêncio.
- Cada trecho transcrito passa por `Detector.detect()`.
- CLI: `python listen.py --mic` (ou `--wav` para testar com gravação).

### Fase 3 — Web ✅ (pronta)
- `FastAPI` + WebSocket empurram transcrição + detecções ao navegador,
  reutilizando `ordem/pipeline.py` (que já emite `Event` em JSON).
- Painel mostra a transmissão ao vivo e cards de mecânica codificados por
  elemento, com o resumo da regra e a referência de página.
- Endpoint `/simulate` e campo de texto permitem testar sem áudio.

---

## Resumos de regras
Cada mecânica detectada traz um resumo curto da regra:
- **Rituais**: Execução/Alcance/Duração + as primeiras frases do efeito,
  extraídos direto do livro.
- **Condições**: descrição do apêndice de condições.
- **Poderes** (homebrew): extraídos de fichas/documentos no formato
  `[Nome do Poder] - descrição`.
- **Perícias, recursos, atributos**: resumo curado, estável.

## Testes
Duas formas de rodar:

```bash
python -m pytest tests/ -v          # suíte pytest (a mesma do CI)
python tests/test_detection.py      # runner colorido no terminal
```

A suíte cobre: rituais dos 5 elementos, perícias, condições, recursos,
poderes homebrew, robustez a ruído de STT (acentos, erros fonéticos,
**palavras partidas** e **distorção pesada**), casos negativos difíceis e
cobertura dos 81 rituais (este último só roda se `ordem.db` existir).

**CI**: o workflow em `.github/workflows/ci.yml` roda pytest (Python 3.11 e
3.12) e ruff a cada push/PR. Como os livros não são versionados, os testes
no CI usam a fixture de `tests/fixtures.py` — termos canônicos do sistema +
entradas sintéticas — cobrindo o detector por completo sem o material
protegido.

Estresse amplo sobre todo o léxico (199 termos): **100%** de detecção com
fala limpa e **~91%** com erros aleatórios de STT (queda concentrada nas
siglas curtas — PE, PV, SAN, NEX — que exigem match exato de propósito).

O detector aguenta transcrição bem imperfeita. Exemplo real:
*"o okultista gasta 3 pe e konjura sopro do ca os, todos rolam resistensia
de vontade ou fikam apavorrados"* → detecta Sopro do Caos [Energia 2], PE,
Resistência, Vontade e Apavorado. Isso vem de três camadas: janelas
"coladas" (juntam palavras partidas), uma chave fonética pt-BR
(ss/ç→s, ch→x, qu/c→k…) e limiares por tamanho de termo.

Detalhe importante: perícias/atributos que também são palavras comuns
(Luta, Crime, Artes, Vontade, Força, Luz…) só são detectados quando há um
**gatilho de jogo** por perto (teste, rola, faz, conjura, lança, usa,
ataque…), evitando falso-positivo em conversa normal da mesa.

## Refinamentos possíveis (próximos)
- Embeddings locais (`sentence-transformers` multilíngue) para busca
  semântica — complementa o FTS quando a fala não usa o termo exato.
- Registro da sessão (log do que foi usado, com timestamps) para revisão
  pós-jogo e exportação.
- Botão na página para abrir o PDF na página exata da regra.
