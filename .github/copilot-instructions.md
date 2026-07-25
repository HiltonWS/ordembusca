# Ordem Busca - instrucoes para agentes de IA

## Contexto do projeto

Este repositorio implementa um sistema local para detectar mecanicas de Ordem
Paranormal a partir de texto ou audio. O fluxo em tempo real e:

`audio -> VAD -> faster-whisper -> detector fuzzy/fonetico -> terminal ou painel web`

O projeto requer Python 3.11 ou superior. Depois do primeiro download do modelo
de voz, o processamento pode ser inteiramente local.

## Mapa do codigo

- `ingest.py`: CLI de ingestao local e sincronizacao automatica com Drive.
- `query.py`: CLI de busca e deteccao textual sem audio.
- `listen.py`: CLI de escuta por microfone, loopback ou WAV.
- `server.py`: servidor FastAPI e WebSocket do painel em tempo real.
- `ordem/extract.py`: extracao e limpeza do texto das fontes.
- `ordem/chunk.py`: divisao do texto com metadados de pagina ou secao.
- `ordem/lexicon.py`: extracao de rituais, poderes e termos canonicos.
- `ordem/db.py`: persistencia SQLite e busca FTS5.
- `ordem/drive.py`: OAuth, cache dos livros e backup SQLite no Google Drive.
- `ordem/detect.py`: deteccao fuzzy e fonetica de mecanicas.
- `ordem/audio.py`: captura, mixagem, reamostragem e VAD.
- `ordem/stt.py`: transcricao local com faster-whisper.
- `ordem/pipeline.py`: orquestracao do audio ate os eventos detectados.
- `ordem/transcripts.py`: registro opt-in em JSONL e Markdown para revisao.
- `ordem/thumbnails.py`: associa assets pelo nome ou semelhanca visual local.
- `ordem/story.py`: transforma transcricoes em storyboard limitado.
- `web/index.html`: painel web ao vivo.
- `tests/`: testes do detector, audio, STT, Drive, colunas e glifos de dados.

## Regras importantes

- Nunca adicione PDFs, DOCX de livros ou bancos `*.db` ao repositorio. Eles
  podem conter material protegido por direitos autorais e dados derivados.
- Nunca versione `credentials.json`, tokens OAuth ou `.ordem-drive/`. A pasta
  do Drive e a preferencia de backup ficam apenas no config local ignorado.
- Nunca grave transcricoes por padrao. O servidor so persiste conversas quando
  `--transcript-log DIRETORIO` for informado; mantenha `transcripts/` ignorado.
- Nunca versione tokens, extras ou thumbnails extraidos dos livros. Mantenha
  `tokens/`, `extras/` e `.ordem-thumbnails/` locais e ignorados.
- Preserve o funcionamento offline e evite introduzir servicos externos no
  caminho principal.
- O detector deve continuar tolerante a erros de transcricao em portugues,
  usando aproximacao fuzzy e fonetica.
- Preserve as categorias expandidas: `caracteristica`, `mascara`, `armadura`,
  `trilha`, `vestimenta`, `acessorio`, `sinergia`, `bonus` e `multiplicador`.
  Preserve tambem `classe`, `sobrevivente`, `nex`, `perseguicao` e `combate`.
  Preserve `efeito` e `dt`; perguntas explicativas sobre efeitos/condicoes devem
  buscar contexto ampliado no FTS local, incluindo fonte e pagina.
  Preserve nomes canônicos de trilhas e armas; termos ambíguos como `faca` e
  `lança` só devem ser armas quando houver contexto de equipamento ou ataque.
  Preserve itens, poderes paranormais e faixas da regra de idade.
  Entradas homebrew nomeadas usam `[Categoria: Nome] - descricao`; bonus e
  multiplicadores de dano tambem sao detectados estruturalmente na fala.
- Preserve suporte a conteudo homebrew, inclusive elementos customizados alem
  dos cinco elementos oficiais.
- Mantenha referencias de origem por livro e pagina, ou por fonte e secao.
- Prefira alteracoes pequenas e consistentes com as abstracoes existentes.
- Nao altere arquivos ou comportamento fora do escopo solicitado.
- Sempre atualize este arquivo e o `README.md` quando comandos, dependencias,
  arquitetura ou rotinas operacionais forem alterados.

## Dependencias

- Nucleo: PyMuPDF, rapidfuzz e python-docx.
- Voz: faster-whisper, webrtcvad-wheels, sounddevice, soundfile e numpy.
- Web: FastAPI, Uvicorn, watchfiles, websockets e Pydantic.
- Drive: google-api-python-client, google-auth-httplib2 e google-auth-oauthlib.
- Desenvolvimento: pytest, Ruff e build.

Instale o ambiente completo com:

```bash
pip install -r requirements.txt
```

## Comandos de operacao

```bash
python ingest.py <arquivos-ou-pastas>
python ingest.py --force <fonte>
python ingest.py --drive-folder <URL-ou-ID> --drive-db-backup
python ingest.py --drive
python ingest.py --drive --drive-interval 0
python query.py "texto da mesa"
python query.py --search "termo"
python listen.py --list-mics
python listen.py --mic
python listen.py --auto-io
python listen.py --wav sessao.wav
python server.py --demo
python server.py --mic
python server.py --auto-io
python server.py --auto-io --transcript-log transcripts
python server.py --auto-io --assets-dir extras --story-limit 120
python server.py --demo --story-transcript transcripts/SESSAO.jsonl
```

Na primeira configuracao do Drive, use um cliente OAuth do tipo Desktop e
salve o JSON como `credentials.json`. O endereco informado por
`--drive-folder` e lembrado em `.ordem-drive/config.json`; depois use apenas
`--drive`. Com `--drive-db-backup`, um snapshot consistente de `ordem.db` e
enviado somente quando o checksum mudar. A sincronizacao do banco e local para
Drive e nao restaura/sobrescreve automaticamente uma base local.
Links completos de pasta sao aceitos e devem preservar `resourcekey`; prefira
o link compartilhado inteiro ao ID quando essa chave estiver presente.
Arquivos Google Docs devem ser exportados para DOCX e Google Slides para PDF;
nao use `get_media` para tipos nativos `application/vnd.google-apps.*`.
Atalhos do Drive devem ser resolvidos por `shortcutDetails.targetId`, incluindo
`targetResourceKey`, antes de baixar ou decidir o formato de exportacao. Use o
ID do atalho como chave do cache/estado e o ID do alvo apenas para download.
A sincronizacao deve percorrer subpastas recursivamente, incluindo atalhos para
pastas, com conjunto de IDs visitados para evitar ciclos.
Imagens PNG/JPG/JPEG/WebP do Drive sao assets, nao fontes textuais. Associe-as
ao lexico por nome normalizado e use comparacao perceptual local apenas quando
nao houver nome correspondente.
Um erro 404 da API ao validar a pasta normalmente significa ID incorreto ou
conta OAuth sem acesso. Oriente a compartilhar a pasta com a conta autorizada
ou remover `.ordem-drive/token.json` para escolher outra conta.

Em Codespaces ou ambientes sem dispositivos de audio, use `--demo` ou `--wav`.
Para expor o servidor em Codespaces, use `--host 0.0.0.0`.

## Rotina para alteracoes

1. Leia o modulo que controla diretamente o comportamento solicitado e um
   teste ou chamada proxima antes de editar.
2. Respeite o estado atual do Git e nao reverta alteracoes do usuario.
3. Adicione ou ajuste testes proporcionais ao risco da mudanca.
4. Execute primeiro o teste mais especifico para o trecho alterado.
5. Para cada funcionalidade nova, crie testes que cubram o comportamento
  esperado e os casos de erro relevantes.
6. Antes de concluir, execute as validacoes gerais quando forem aplicaveis:

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
- Antes de qualquer commit ou push, execute os testes e verificacoes de
  qualidade aplicaveis. Se alguma validacao falhar, investigue e corrija a
  causa antes de publicar; nunca envie alteracoes com testes quebrados.
- Nao inclua no commit alteracoes preexistentes ou fora do escopo.
- Nao faca commit ou push apenas quando o usuario pedir explicitamente para nao
  fazer, ou quando houver um bloqueio de autenticacao, permissao ou seguranca.
