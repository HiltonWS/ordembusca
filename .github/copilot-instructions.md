# Ordem Busca - instrucoes para agentes de IA

## Contexto do projeto

Este repositorio implementa um sistema local para detectar mecanicas de Ordem
Paranormal a partir de texto ou audio. O fluxo em tempo real e:

`audio -> VAD -> faster-whisper -> detector fuzzy/fonetico -> terminal ou painel web`

O projeto requer Python 3.11 ou superior. Depois do primeiro download do modelo
de voz, o processamento pode ser inteiramente local.

## Mapa do codigo

- `ingest.py`: CLI de ingestao de arquivos PDF, TXT e DOCX.
- `query.py`: CLI de busca e deteccao textual sem audio.
- `listen.py`: CLI de escuta por microfone, loopback ou WAV.
- `server.py`: servidor FastAPI e WebSocket do painel em tempo real.
- `ordem/extract.py`: extracao e limpeza do texto das fontes.
- `ordem/chunk.py`: divisao do texto com metadados de pagina ou secao.
- `ordem/lexicon.py`: extracao de rituais, poderes e termos canonicos.
- `ordem/db.py`: persistencia SQLite e busca FTS5.
- `ordem/detect.py`: deteccao fuzzy e fonetica de mecanicas.
- `ordem/audio.py`: captura, mixagem, reamostragem e VAD.
- `ordem/stt.py`: transcricao local com faster-whisper.
- `ordem/pipeline.py`: orquestracao do audio ate os eventos detectados.
- `web/index.html`: painel web ao vivo.
- `tests/`: testes do detector, audio, STT, colunas e glifos de dados.

## Regras importantes

- Nunca adicione PDFs, DOCX de livros ou bancos `*.db` ao repositorio. Eles
  podem conter material protegido por direitos autorais e dados derivados.
- Preserve o funcionamento offline e evite introduzir servicos externos no
  caminho principal.
- O detector deve continuar tolerante a erros de transcricao em portugues,
  usando aproximacao fuzzy e fonetica.
- Preserve suporte a conteudo homebrew, inclusive elementos customizados alem
  dos cinco elementos oficiais.
- Mantenha referencias de origem por livro e pagina, ou por fonte e secao.
- Prefira alteracoes pequenas e consistentes com as abstracoes existentes.
- Nao altere arquivos ou comportamento fora do escopo solicitado.

## Dependencias

- Nucleo: PyMuPDF, rapidfuzz e python-docx.
- Voz: faster-whisper, webrtcvad-wheels, sounddevice, soundfile e numpy.
- Web: FastAPI, Uvicorn, watchfiles, websockets e Pydantic.
- Desenvolvimento: pytest, Ruff e build.

Instale o ambiente completo com:

```bash
pip install -r requirements.txt
```

## Comandos de operacao

```bash
python ingest.py <arquivos-ou-pastas>
python ingest.py --force <fonte>
python query.py "texto da mesa"
python query.py --search "termo"
python listen.py --list-mics
python listen.py --mic
python listen.py --auto-io
python listen.py --wav sessao.wav
python server.py --demo
python server.py --mic
python server.py --auto-io
```

Em Codespaces ou ambientes sem dispositivos de audio, use `--demo` ou `--wav`.
Para expor o servidor em Codespaces, use `--host 0.0.0.0`.

## Rotina para alteracoes

1. Leia o modulo que controla diretamente o comportamento solicitado e um
   teste ou chamada proxima antes de editar.
2. Respeite o estado atual do Git e nao reverta alteracoes do usuario.
3. Adicione ou ajuste testes proporcionais ao risco da mudanca.
4. Execute primeiro o teste mais especifico para o trecho alterado.
5. Antes de concluir, execute as validacoes gerais quando forem aplicaveis:

```bash
pytest
ruff check .
```

O Ruff usa limite de 100 colunas, alvo Python 3.11 e regras `E`, `F`, `W` e `I`.
Consulte o `README.md` quando precisar de detalhes de uso, ingestao, audio ou
arquitetura que nao estejam resumidos aqui.

## Git

- Ao concluir e validar uma alteracao solicitada, crie um commit com mensagem
  objetiva e envie a branch atual ao remoto com `git push`.
- Nao inclua no commit alteracoes preexistentes ou fora do escopo.
- Nao faca commit ou push apenas quando o usuario pedir explicitamente para nao
  fazer, ou quando houver um bloqueio de autenticacao, permissao ou seguranca.