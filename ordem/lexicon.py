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
    category: str
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
    "Fatigado", "Enredado",
]

CONDICAO_SUMMARY = {
    "Fatigado": "Fica fraco e vulnerável; sofrer essa condição novamente pode causar exaustão.",
    "Enredado": "Fica lento, vulnerável e sofre penalidade em testes de ataque.",
}

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

MECANICAS = [
    LexEntry("Poder", "poder", aliases=["poderes", "poder paranormal"],
             summary="Habilidade que concede uma opção ou efeito especial ao personagem."),
    LexEntry("Item", "item", aliases=["itens", "equipamento"],
             summary="Objeto com propriedades e usos mecânicos próprios."),
    LexEntry("Regra de Idade", "idade", aliases=["idade", "faixa etária", "faixa etaria"],
             summary="A idade define a faixa etária e seus efeitos na criação do personagem."),
    LexEntry("Efeito", "efeito", aliases=["efeitos"],
             summary="Consequência mecânica aplicada por uma habilidade, item ou condição."),
    LexEntry("Classe", "classe", aliases=["classes"],
             summary="Arquétipo principal que define habilidades e progressão do personagem."),
    LexEntry("Combatente", "classe",
             summary="Classe voltada a combate, resistência e domínio de armas."),
    LexEntry("Especialista", "classe",
             summary="Classe versátil focada em perícias, conhecimento e utilidade."),
    LexEntry("Ocultista", "classe",
             summary="Classe que usa rituais e conhecimento paranormal."),
    LexEntry("Sobrevivente", "sobrevivente", aliases=["classe sobrevivente"],
             summary="Personagem em estágio inicial de exposição e sobrevivência ao paranormal."),
    LexEntry("Alteração de NEX", "nex",
             aliases=["mudança de NEX", "aumento de NEX", "marco de NEX"],
             summary="Mudança de exposição que pode liberar ou alterar habilidades."),
    LexEntry("Perseguição", "perseguicao", aliases=["cena de perseguição"],
             summary="Mecânica de disputa por rodadas para alcançar ou escapar de um alvo."),
    LexEntry("Combate", "combate", aliases=["cena de combate"],
             summary="Mecânica estruturada em rodadas, turnos, ações, ataques e reações."),
    LexEntry("Característica Única", "caracteristica",
             aliases=["caracteristica unica", "habilidade unica"],
             summary="Mecânica exclusiva do personagem, com vantagens e limitações próprias."),
    LexEntry("Habilidade de Máscara", "mascara",
             aliases=["habilidade da mascara", "poder de mascara", "máscara"],
             summary="Habilidade vinculada a uma máscara ou identidade especial."),
    LexEntry("Armadura", "armadura", aliases=["proteção", "protecao"],
             summary="Proteção equipada que pode fornecer Defesa, resistência ou efeitos."),
    LexEntry("Trilha", "trilha", aliases=["trilha de classe"],
             summary="Especialização de classe que concede habilidades em marcos de NEX."),
    LexEntry("Vestimenta", "vestimenta", aliases=["veste"],
             summary="Acessório vestido que fornece bônus ou propriedades especiais."),
    LexEntry("Acessório", "acessorio", aliases=["acessório", "utensílio", "utensilio"],
             summary="Item utilitário que auxilia perícias ou concede outros benefícios."),
    LexEntry("Combinação", "sinergia", aliases=["combo", "combinação"],
             summary="Interação planejada entre duas ou mais mecânicas."),
    LexEntry("Sinergia", "sinergia", aliases=["sinergias"],
             summary="Efeito conjunto em que mecânicas reforçam umas às outras."),
]

TRILHAS = [
    LexEntry("Aniquilador", "trilha", meta={"classe": "Combatente"},
             summary="Trilha de Combatente especializada em uma arma favorita."),
    LexEntry("Comandante de Campo", "trilha", meta={"classe": "Combatente"},
             summary="Trilha de Combatente focada em coordenar e apoiar aliados."),
    LexEntry("Guerreiro", "trilha", meta={"classe": "Combatente"},
             summary="Trilha de Combatente focada em combate corpo a corpo e manobras."),
    LexEntry("Operações Especiais", "trilha", aliases=["Operacoes Especiais"],
             meta={"classe": "Combatente"},
             summary="Trilha de Combatente focada em mobilidade e ações rápidas."),
    LexEntry("Tropa de Choque", "trilha", meta={"classe": "Combatente"},
             summary="Trilha de Combatente focada em resistência e proteção do grupo."),
    LexEntry("Atirador de Elite", "trilha", meta={"classe": "Especialista"},
             summary="Trilha de Especialista focada em armas de fogo de longo alcance."),
    LexEntry("Infiltrador", "trilha", meta={"classe": "Especialista"},
             summary="Trilha de Especialista focada em furtividade e ataques oportunos."),
    LexEntry("Médico de Campo", "trilha", aliases=["Medico de Campo"],
             meta={"classe": "Especialista"},
             summary="Trilha de Especialista focada em tratamento e suporte médico."),
    LexEntry("Negociador", "trilha", meta={"classe": "Especialista"},
             summary="Trilha de Especialista focada em interação social e negociação."),
    LexEntry("Técnico", "trilha", aliases=["Tecnico"], meta={"classe": "Especialista"},
             summary="Trilha de Especialista focada em equipamentos e improvisação."),
    LexEntry("Conduíte", "trilha", aliases=["Conduite"], meta={"classe": "Ocultista"},
             summary="Trilha de Ocultista focada em ampliar alcance e fluxo de rituais."),
    LexEntry("Flagelador", "trilha", meta={"classe": "Ocultista"},
             summary="Trilha de Ocultista que converte vitalidade em poder paranormal."),
    LexEntry("Graduado", "trilha", meta={"classe": "Ocultista"},
             summary="Trilha de Ocultista focada em conhecer e preparar mais rituais."),
    LexEntry("Intuitivo", "trilha", meta={"classe": "Ocultista"},
             summary="Trilha de Ocultista focada em resistência e percepção paranormal."),
    LexEntry("Lâmina Paranormal", "trilha",
             aliases=["Lamina Paranormal", "Lâmina", "Lamina"],
             meta={"classe": "Ocultista"},
             summary="Trilha de Ocultista que combina rituais e combate com armas."),
]

ARMAS = [
    LexEntry(name, "arma", aliases=aliases, meta={"grupo": group}, summary=summary)
    for name, aliases, group, summary in [
        ("Bastão", ["Bastao"], "corpo a corpo", "Arma simples de impacto."),
        ("Faca", [], "corpo a corpo", "Arma simples leve e ágil."),
        ("Lança", ["Lanca"], "corpo a corpo", "Arma simples de haste e alcance."),
        ("Machadinha", [], "corpo a corpo", "Arma simples de corte."),
        ("Martelo", [], "corpo a corpo", "Arma simples de impacto."),
        ("Arco", [], "disparo", "Arma simples de disparo."),
        ("Balestra", [], "disparo", "Arma simples de disparo mecânico."),
        ("Pistola", [], "fogo", "Arma de fogo curta."),
        ("Revólver", ["Revolver"], "fogo", "Arma de fogo curta."),
        ("Acha", [], "corpo a corpo", "Arma tática pesada de corte."),
        ("Corrente", [], "corpo a corpo", "Arma tática flexível."),
        ("Espada", [], "corpo a corpo", "Arma tática de corte."),
        ("Florete", [], "corpo a corpo", "Arma tática ágil de perfuração."),
        ("Katana", ["Catana"], "corpo a corpo", "Arma tática ágil de corte."),
        ("Machado", [], "corpo a corpo", "Arma tática de corte."),
        ("Marreta", [], "corpo a corpo", "Arma tática pesada de impacto."),
        ("Montante", [], "corpo a corpo", "Arma tática pesada de corte."),
        ("Motosserra", [], "corpo a corpo", "Arma tática motorizada de corte."),
        ("Nunchaku", ["Nunchaco"], "corpo a corpo", "Arma tática ágil de impacto."),
        ("Arco Composto", [], "disparo", "Arma tática de disparo."),
        ("Espingarda", [], "fogo", "Arma de fogo de alto impacto a curta distância."),
        ("Fuzil de Assalto", [], "fogo", "Arma de fogo longa automática."),
        ("Fuzil de Caça", ["Fuzil de Caca"], "fogo", "Arma de fogo longa."),
        ("Metralhadora", [], "fogo", "Arma de fogo pesada automática."),
        ("Rifle de Precisão", ["Rifle de Precisao"], "fogo",
         "Arma de fogo de precisão e longo alcance."),
        ("Submetralhadora", [], "fogo", "Arma de fogo automática compacta."),
    ]
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
# linha completa de aprimoramento: "Discente (+2 PE): texto" | "Afinidade: texto"
_TIER_LINE = re.compile(
    r"^(Discente|Verdadeiro|Afinidade)\s*(\([^)]*\))?\s*[:\-–—]?\s*(.*)", re.I
)


def _extract_tiers(lines: list[str], header_idx: int) -> dict[str, str]:
    """Captura os aprimoramentos do bloco (Discente/Verdadeiro/Afinidade).

    Devolve {'discente': '(+2 PE) muda o alcance...', 'verdadeiro': ...}.
    A varredura para no próximo bloco (cabeçalho elemento+círculo) e cada
    texto de aprimoramento termina em linha vazia, novo aprimoramento ou
    quando a linha seguinte é um cabeçalho (a atual seria o nome do
    próximo ritual).
    """
    tiers: dict[str, list[str]] = {}
    current: str | None = None
    window = lines[header_idx + 1: header_idx + 60]
    for j, line in enumerate(window):
        s = line.strip()
        if _RITUAL_HEADER.match(line) or _PODER_PARANORMAL.match(line):
            break                      # começou o próximo bloco
        if (j + 1 < len(window)
                and (_RITUAL_HEADER.match(window[j + 1])
                     or _PODER_PARANORMAL.match(window[j + 1]))
                and _looks_like_ritual_name(s)):
            break                      # esta linha é o nome do próximo bloco
        if s.isdigit():
            continue                   # número de página no rodapé
        if len(s) > 3 and s.isupper():
            current = None             # rótulo/cabeçalho: fecha o texto
            continue                   # atual, mas segue procurando tiers
        m = _TIER_LINE.match(s)
        if m and _RITUAL_TIER.match(s):
            key = m.group(1).lower()
            if key in tiers:
                break                  # repetiu: já é o bloco seguinte
            cost = (m.group(2) or "").strip()
            rest = m.group(3).strip()
            tiers[key] = [f"{cost} {rest}".strip() if cost else rest]
            current = key
            continue
        if not s:
            current = None
            continue
        if current:
            tiers[current].append(s)
    out: dict[str, str] = {}
    for key, parts in tiers.items():
        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        if text:
            out[key] = _trim(text, 300)
    return out


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
            meta = {"elemento": elemento.capitalize(), "circulo": circulo}
            meta.update(_extract_tiers(lines, i))
            entries.append(LexEntry(
                term=name,
                category=category,
                meta=meta,
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
        e = LexEntry(name, "condicao", summary=CONDICAO_SUMMARY.get(name))
        norm = normalize_term(name)
        if norm in cond_summaries:
            e.summary, page, loc = cond_summaries[norm]
            e.page, e.loc = page, loc
            e.source_filename = source.filename if source else None
        elif source:
            e.source_filename = source.filename
            e.page, e.loc = _find_page_of(source, name)
        out.append(e)

    for e in RECURSOS + ATRIBUTOS + MECANICAS + TRILHAS + ARMAS:
        out.append(e)
    return out


# rótulo dos Poderes Paranormais nos Arquivos Secretos: "PODER PARANORMAL MORTE"
_PODER_PARANORMAL = re.compile(
    r"^\s*PODER\s+PARANORMAL\s+(" + "|".join(ELEMENTOS) + r")\s*$", re.I
)


def extract_poderes_paranormais(source: Source) -> list[LexEntry]:
    """Poderes Paranormais no formato dos Arquivos Secretos:
    <Nome>\\n PODER PARANORMAL <ELEMENTO> (sem círculo)."""
    entries: list[LexEntry] = []
    seen: set[str] = set()
    for page in source.pages:
        lines = page.text.split("\n")
        for i, line in enumerate(lines):
            m = _PODER_PARANORMAL.match(line)
            if not m:
                continue
            name = None
            for j in range(i - 1, max(-1, i - 3), -1):
                cand = lines[j].strip()
                if not cand:
                    continue
                if _looks_like_ritual_name(cand):
                    name = cand
                break
            if not name:
                continue
            key = normalize_term(name)
            if key in seen:
                continue
            seen.add(key)
            meta = {"elemento": m.group(1).capitalize()}
            meta.update(_extract_tiers(lines, i))
            # resumo: linhas após o rótulo até vazio/próximo bloco/tier
            desc: list[str] = []
            for nxt in lines[i + 1: i + 14]:
                s = nxt.strip()
                if (not s or _PODER_PARANORMAL.match(nxt)
                        or _RITUAL_TIER.match(s)):
                    break
                if s.isdigit():
                    continue
                if len(s) > 3 and s.isupper():
                    break
                desc.append(s)
            summary = _trim(re.sub(r"\s+", " ", " ".join(desc)).strip(), 300) \
                if desc else None
            entries.append(LexEntry(
                term=name, category="poder", meta=meta, summary=summary,
                source_filename=source.filename, page=page.number,
                loc=page.loc,
            ))
    return entries


def build_lexicon(source: Source) -> list[LexEntry]:
    """Léxico completo para uma fonte: rituais + poderes + termos canônicos."""
    return (extract_rituais(source) + extract_poderes(source)
            + extract_poderes_paranormais(source)
            + canonical_entries(source))


# poderes/habilidades nomeados no formato "[Nome] - descrição" (homebrew, fichas)
_PODER = re.compile(r"^\[([^\]]{2,50})\]\s*[-–—:]\s*(.+)")
_NAMED_LABEL = re.compile(r"^(.{2,30}?)\s*[:\-–—]\s*(.{2,50})$")
_NAMED_CATEGORIES = {
    "efeito": "efeito",
    "classe": "classe",
    "sobrevivente": "sobrevivente",
    "alteracao de nex": "nex",
    "marco de nex": "nex",
    "perseguicao": "perseguicao",
    "combate": "combate",
    "caracteristica": "caracteristica",
    "caracteristica unica": "caracteristica",
    "habilidade unica": "caracteristica",
    "mascara": "mascara",
    "habilidade de mascara": "mascara",
    "armadura": "armadura",
    "arma": "arma",
    "item": "item",
    "poder": "poder",
    "poder paranormal": "poder",
    "regra de idade": "idade",
    "trilha": "trilha",
    "vestimenta": "vestimenta",
    "acessorio": "acessorio",
    "combinacao": "sinergia",
    "combo": "sinergia",
    "sinergia": "sinergia",
}


def _named_category(raw_name: str) -> tuple[str, str]:
    match = _NAMED_LABEL.match(raw_name)
    if not match:
        return raw_name, "poder"
    category = _NAMED_CATEGORIES.get(normalize_term(match.group(1)))
    if not category:
        return raw_name, "poder"
    return match.group(2).strip(), category


def extract_poderes(source: Source) -> list[LexEntry]:
    entries: list[LexEntry] = []
    seen: set[str] = set()
    for page in source.pages:
        for line in page.text.split("\n"):
            m = _PODER.match(line.strip())
            if not m:
                continue
            nome, category = _named_category(m.group(1).strip())
            # ignora rótulos puramente numéricos como [110%]
            if not re.search(r"[A-Za-zÀ-ú]", nome):
                continue
            key = normalize_term(nome)
            if key in seen or len(key) < 3:
                continue
            seen.add(key)
            desc = re.sub(r"\s+", " ", m.group(2)).strip()
            entries.append(LexEntry(
                term=nome, category=category,
                summary=_trim(desc, 300),
                source_filename=source.filename, page=page.number,
                loc=page.loc,
            ))
    return entries
