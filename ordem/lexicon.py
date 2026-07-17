"""Construção do léxico de mecânicas de Ordem Paranormal.

O léxico é o que permite reconhecer, na fala transcrita, QUE mecânica
está sendo usada. Combina:
  - termos canônicos do sistema (perícias, condições, recursos) — fixos
  - entidades extraídas dos livros (rituais nomeados) — dinâmicos

Cada entrada tem: term (canônico), category, aliases, e opcionalmente
metadados (elemento/círculo de ritual) e a referência (fonte, página).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .extract import Source, normalize_term


@dataclass
class LexEntry:
    term: str
    category: str                       # ritual|pericia|condicao|recurso|atributo|poder
    aliases: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    summary: str | None = None          # resumo curto da regra
    source_filename: str | None = None
    page: int | None = None
    loc: str | None = None              # rótulo de localização (seção, se houver)

    def all_forms(self) -> list[str]:
        return [self.term, *self.aliases]


# --- Termos canônicos do sistema (independem do PDF) -----------------------

PERICIAS = [
    "Acrobacia", "Adestramento", "Artes", "Atletismo", "Atualidades",
    "Ciências", "Crime", "Diplomacia", "Enganação", "Fortitude",
    "Furtividade", "Iniciativa", "Intimidação", "Intuição", "Investigação",
    "Luta", "Medicina", "Ocultismo", "Percepção", "Pilotagem", "Pontaria",
    "Profissão", "Reflexos", "Religião", "Sobrevivência", "Tática", "Vontade",
]

CONDICOES = [
    "Abalado", "Agarrado", "Alquebrado", "Apavorado", "Atordoado", "Caído",
    "Cego", "Confuso", "Debilitado", "Desprevenido", "Doente", "Enfeitiçado",
    "Enjoado", "Envenenado", "Esmorecido", "Exausto", "Fascinado", "Fraco",
    "Frustrado", "Imóvel", "Inconsciente", "Indefeso", "Lento", "Ofuscado",
    "Paralisado", "Pasmo", "Petrificado", "Sangrando", "Surdo", "Surpreendido",
    "Vulnerável", "Zonzo", "Enrijecido", "Machucado", "Trêmulo",
]

# recursos e siglas — incluem formas faladas comuns
RECURSOS = [
    LexEntry("NEX", "recurso", aliases=["nex", "nível de exposição",
             "nivel de exposicao paranormal", "exposição paranormal"],
             summary="Nível de Exposição Paranormal (0–99%). Mede o quanto o "
             "personagem foi exposto ao Outro Lado; define poder e limites."),
    LexEntry("PE", "recurso", aliases=["pontos de esforço", "ponto de esforço",
             "esforço", "pe"],
             summary="Pontos de Esforço. Gastos para ativar habilidades, "
             "rituais e melhorias. Recuperados com descanso."),
    LexEntry("PV", "recurso", aliases=["pontos de vida", "vida", "ponto de vida"],
             summary="Pontos de Vida. Chega a 0 → personagem morrendo/morto."),
    LexEntry("SAN", "recurso", aliases=["sanidade", "pontos de sanidade", "san"],
             summary="Sanidade. Reduzida por horrores paranormais; a 0 o "
             "personagem enlouquece (fica insano)."),
    LexEntry("Resistência", "recurso", aliases=["resistencia"],
             summary="Teste para reduzir ou evitar um efeito (geralmente "
             "Fortitude, Reflexos ou Vontade contra um valor de dificuldade)."),
    LexEntry("Dano", "recurso", aliases=["dano mental", "dano de medo",
             "dano de sangue", "dano de morte", "dano de energia",
             "dano de conhecimento"],
             summary="Redução de PV. Tipos paranormais: Sangue, Morte, "
             "Conhecimento, Energia e Medo; alguns ignoram resistências comuns."),
]

ATRIBUTOS = [
    LexEntry("Agilidade", "atributo", aliases=["agi"],
             summary="Destreza, reflexos e coordenação."),
    LexEntry("Força", "atributo", aliases=["for", "forca"],
             summary="Poder físico e capacidade de carga."),
    LexEntry("Intelecto", "atributo", aliases=["int"],
             summary="Raciocínio, memória e conhecimento."),
    LexEntry("Presença", "atributo", aliases=["pre", "presenca"],
             summary="Força de vontade, carisma e percepção do entorno."),
    LexEntry("Vigor", "atributo", aliases=["vig"],
             summary="Saúde, fôlego e resistência física."),
]

# resumos curados das perícias (curtos e estáveis; o livro descreve em detalhe)
PERICIA_SUMMARY = {
    "Acrobacia": "Equilíbrio, saltos e escapar de agarrões (Agilidade).",
    "Adestramento": "Lidar com e comandar animais (Presença).",
    "Artes": "Criar e avaliar obras artísticas; atuação (Presença).",
    "Atletismo": "Correr, escalar, nadar e saltar (Força).",
    "Atualidades": "Conhecimentos gerais e cultura contemporânea (Intelecto).",
    "Ciências": "Conhecimento científico e análise técnica (Intelecto).",
    "Crime": "Furtar, arrombar e agir na ilegalidade (Agilidade).",
    "Diplomacia": "Persuadir e negociar de boa-fé (Presença).",
    "Enganação": "Mentir, blefar e disfarçar (Presença).",
    "Fortitude": "Resistência física a dano e efeitos (Vigor).",
    "Furtividade": "Mover-se sem ser visto ou ouvido (Agilidade).",
    "Iniciativa": "Rapidez para agir no início do combate (Agilidade).",
    "Intimidação": "Coagir pelo medo ou ameaça (Presença).",
    "Intuição": "Perceber intenções, mentiras e pistas sociais (Presença).",
    "Investigação": "Procurar pistas e deduzir conclusões (Intelecto).",
    "Luta": "Ataques corpo a corpo (Força).",
    "Medicina": "Primeiros socorros, estabilizar e tratar (Intelecto).",
    "Ocultismo": "Conhecimento sobre o paranormal e o Outro Lado (Intelecto).",
    "Percepção": "Notar detalhes e ameaças no ambiente (Presença).",
    "Pilotagem": "Conduzir veículos (Agilidade).",
    "Pontaria": "Ataques à distância (Agilidade).",
    "Profissão": "Conhecimento e renda de um ofício (Intelecto).",
    "Reflexos": "Esquivar-se de perigos em área (Agilidade).",
    "Religião": "Fé, rituais religiosos e simbologia sagrada (Presença).",
    "Sobrevivência": "Orientar-se, rastrear e sobreviver na natureza (Intelecto).",
    "Tática": "Coordenar aliados e explorar o campo de batalha (Intelecto).",
    "Vontade": "Resistência mental a medo e controle (Presença).",
}

ELEMENTOS = ["SANGUE", "MORTE", "CONHECIMENTO", "ENERGIA", "MEDO",
             "PROFUNDEZAS"]   # "Profundezas": 6º elemento homebrew (Alto Mar)

# padrão da linha de elemento+círculo de um ritual: " MEDO 4 " (PDF, maiúsculo)
# ou " Sangue 1 " (docx homebrew, capitalizado) — aceita qualquer capitalização
_RITUAL_HEADER = re.compile(
    r"^\s*(" + "|".join(ELEMENTOS) + r")\s*([1-4])\s*$", re.I
)


def _looks_like_ritual_name(line: str) -> bool:
    line = line.strip()
    if not (2 <= len(line) <= 50):
        return False
    if line.isupper():            # cabeçalhos de seção em caixa alta não são nomes
        return False
    if re.search(r"[.:;]$", line):
        return False
    if re.search(r"\d", line):
        return False
    # deve começar com maiúscula
    return bool(re.match(r"^[A-ZÀ-Ú]", line))


_RITUAL_FIELDS = re.compile(
    r"^(Execução|Alcance|Alvo|Área|Area|Duração|Duracao|Resistência|Resistencia)"
    r"\b\s*[:\-–—]?\s+\S",
    re.I,
)
_RITUAL_DESC = re.compile(r"^Descrição\s*[:\-–—]?\s+(.*)", re.I)
_RITUAL_TIER = re.compile(r"^(Discente|Verdadeiro|Afinidade)\b", re.I)  # upgrades


def _ritual_summary(lines: list[str], header_idx: int) -> str | None:
    """Compõe um resumo a partir das linhas após o cabeçalho do ritual."""
    fields: list[str] = []
    effect: list[str] = []
    for line in lines[header_idx + 1: header_idx + 24]:
        s = line.strip()
        if not s:
            break                              # linha em branco = fim do bloco
        if _RITUAL_HEADER.match(line):        # começou outro ritual
            break
        if _RITUAL_TIER.match(s):             # Discente/Verdadeiro: pula
            continue
        m = _RITUAL_DESC.match(s)
        if m:
            effect.append(m.group(1))
            continue
        if _RITUAL_FIELDS.match(s):
            fields.append(re.sub(r"\s+", " ", s))
        else:
            effect.append(s)
    parts = []
    if fields:
        parts.append(" · ".join(fields))
    if effect:
        text = " ".join(effect)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        parts.append(" ".join(sentences[:2]).strip())
    summary = " — ".join(parts)
    return _trim(summary, 400) if summary else None


def _has_ritual_fields_nearby(lines: list[str], header_idx: int) -> bool:
    """Confirma que é um bloco de verdade (não uma linha solta de tabela/
    pré-requisito): exige um campo ou nível de upgrade reconhecível logo
    após o cabeçalho (Execução/Alcance/Descrição/Afinidade/Discente...)."""
    for line in lines[header_idx + 1: header_idx + 10]:
        s = line.strip()
        if not s:
            break
        if _RITUAL_FIELDS.match(s) or _RITUAL_DESC.match(s) or _RITUAL_TIER.match(s):
            return True
    return False


def extract_rituais(source: Source) -> list[LexEntry]:
    """Detecta rituais/poderes paranormais pelo padrão: <Nome>\\n <ELEMENTO><Círculo>.

    Esse padrão de campos (Execução/Alcance/Duração...) é usado tanto para
    Rituais quanto para Poderes Paranormais nos livros/homebrew. Quando a
    fonte tem seção (loc) identificável, usamos-a para categorizar certo;
    sem seção (PDFs oficiais), assume-se "ritual" (comportamento original).
    """
    entries: list[LexEntry] = []
    seen: set[str] = set()
    for page in source.pages:
        lines = page.text.split("\n")
        category = "ritual"
        if page.loc and "poder" in page.loc.lower():
            category = "poder"
        for i, line in enumerate(lines):
            m = _RITUAL_HEADER.match(line)
            if not m:
                continue
            elemento, circulo = m.group(1), int(m.group(2))
            name = None
            for j in range(i - 1, max(-1, i - 4), -1):
                cand = lines[j].strip()
                if not cand:
                    continue
                if _looks_like_ritual_name(cand):
                    name = cand
                break
            if not name:
                continue
            if not _has_ritual_fields_nearby(lines, i):
                continue    # provável linha solta de tabela/pré-requisito
            key = normalize_term(name) + "|" + category
            if key in seen:
                continue
            seen.add(key)
            entries.append(LexEntry(
                term=name,
                category=category,
                meta={"elemento": elemento.capitalize(), "circulo": circulo},
                summary=_ritual_summary(lines, i),
                source_filename=source.filename,
                page=page.number,
                loc=page.loc,
            ))
    return entries


# regex para uma entrada do apêndice de condições: "Nome. Descrição..."
_COND_ENTRY = re.compile(r"^([A-ZÀ-Ú][a-zà-ú]+)\.\s+(.*)")


def extract_condicao_summaries(source: Source) -> dict[str, tuple[str, int, str | None]]:
    """Extrai {nome_normalizado: (descrição, página, loc)} do apêndice de condições."""
    out: dict[str, tuple[str, int, str | None]] = {}
    known = {normalize_term(c) for c in CONDICOES}
    in_appendix = False
    for page in source.pages:
        text = page.text
        if "CONDIÇÕES" in text and "APÊNDICE" in text:
            in_appendix = True
        if not in_appendix:
            continue
        lines = text.split("\n")
        cur_name = None
        cur_desc: list[str] = []

        def commit():
            if cur_name:
                norm = normalize_term(cur_name)
                if norm in known and norm not in out:
                    desc = re.sub(r"\s+", " ", " ".join(cur_desc)).strip()
                    out[norm] = (_trim(desc, 300), page.number, page.loc)

        for line in lines:
            m = _COND_ENTRY.match(line.strip())
            if m and normalize_term(m.group(1)) in known:
                commit()
                cur_name, cur_desc = m.group(1), [m.group(2)]
            elif cur_name:
                cur_desc.append(line.strip())
        commit()
        if in_appendix and "APÊNDICE" in text and out and \
           text.count("APÊNDICE") and page.number > 0 and len(out) >= 5 and \
           "CONDIÇÕES" not in text:
            break
    return out


def _trim(text: str, limit: int) -> str:
    """Corta em fronteira de frase (ou palavra) até o limite."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # tenta terminar numa frase completa
    m = list(re.finditer(r"[.!?]\s", cut))
    if m and m[-1].end() > limit * 0.5:
        return cut[:m[-1].end()].strip()
    # senão, corta na última palavra
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _find_page_of(source: Source, term: str) -> tuple[int | None, str | None]:
    norm = normalize_term(term)
    for page in source.pages:
        if norm in normalize_term(page.text):
            return page.number, page.loc
    return None, None


def canonical_entries(source: Source | None = None) -> list[LexEntry]:
    """Perícias, condições, recursos, atributos — com página e resumo."""
    out: list[LexEntry] = []

    cond_summaries = extract_condicao_summaries(source) if source else {}

    for name in PERICIAS:
        e = LexEntry(name, "pericia", summary=PERICIA_SUMMARY.get(name))
        if source:
            e.source_filename = source.filename
            e.page, e.loc = _find_page_of(source, name)
        out.append(e)

    for name in CONDICOES:
        e = LexEntry(name, "condicao")
        norm = normalize_term(name)
        if norm in cond_summaries:
            e.summary, page, loc = cond_summaries[norm]
            e.page, e.loc = page, loc
            e.source_filename = source.filename if source else None
        elif source:
            e.source_filename = source.filename
            e.page, e.loc = _find_page_of(source, name)
        out.append(e)

    for e in RECURSOS + ATRIBUTOS:
        out.append(e)
    return out


def build_lexicon(source: Source) -> list[LexEntry]:
    """Léxico completo para uma fonte: rituais + poderes + termos canônicos."""
    return (extract_rituais(source) + extract_poderes(source)
            + canonical_entries(source))


# poderes/habilidades nomeados no formato "[Nome] - descrição" (homebrew, fichas)
_PODER = re.compile(r"^\[([^\]]{2,50})\]\s*[-–—:]\s*(.+)")


def extract_poderes(source: Source) -> list[LexEntry]:
    entries: list[LexEntry] = []
    seen: set[str] = set()
    for page in source.pages:
        for line in page.text.split("\n"):
            m = _PODER.match(line.strip())
            if not m:
                continue
            nome = m.group(1).strip()
            # ignora rótulos puramente numéricos como [110%]
            if not re.search(r"[A-Za-zÀ-ú]", nome):
                continue
            key = normalize_term(nome)
            if key in seen or len(key) < 3:
                continue
            seen.add(key)
            desc = re.sub(r"\s+", " ", m.group(2)).strip()
            entries.append(LexEntry(
                term=nome, category="poder",
                summary=_trim(desc, 300),
                source_filename=source.filename, page=page.number,
                loc=page.loc,
            ))
    return entries
