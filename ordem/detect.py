"""Detecção de mecânicas em texto de fala transcrita.

Recebe uma linha de transcrição, normaliza e casa (fuzzy) contra o léxico.
A tolerância fuzzy absorve os erros típicos de STT ("ocultismo"->"ocultismo",
"lâminas de sangue" mal transcrito etc.).

Projetado para uso em tempo real: carregue o léxico uma vez, chame
detect() a cada trecho de transcrição.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from .extract import normalize_term


# --- Chave fonética pt-BR ---------------------------------------------------
# Reduz variações de transcrição a uma forma aproximada: ss/ç/sc→s,
# ch→x, qu/c(hard)→k, c(e/i)→s, z→s, remove h mudo, colapsa letras dobradas.
def phonetic_pt(s: str) -> str:
    out = []
    for w in s.split():
        w = w.replace("lh", "l").replace("nh", "n")
        w = w.replace("ch", "x")
        w = w.replace("qu", "k").replace("q", "k")
        w = re.sub(r"c([ei])", r"s\1", w)   # ce/ci -> se/si
        w = w.replace("ss", "s").replace("sc", "s").replace("ç", "s")
        w = w.replace("c", "k")             # c restante -> som duro
        w = w.replace("z", "s")
        w = w.replace("ph", "f")
        w = re.sub(r"h", "", w)             # h mudo
        w = re.sub(r"y", "i", w)
        w = re.sub(r"(.)\1+", r"\1", w)     # colapsa letras dobradas
        out.append(w)
    return " ".join(out)

# Termos que também são palavras comuns do português — só contam como
# mecânica se houver um "gatilho" de jogo por perto (evita falso-positivo
# em conversa normal). Valores são formas já normalizadas.
AMBIGUOUS_FORMS = {
    "luta", "crime", "artes", "vontade", "religiao", "profissao", "ciencias",
    "forca", "presenca", "vida", "esforco", "resistencia", "dano", "vigor",
    "luz", "mascara", "armadura", "protecao", "trilha", "vestimenta",
    "veste", "acessorio", "utensilio", "combo", "combinacao", "sinergia",
    "classe", "combatente", "especialista", "ocultista", "sobrevivente",
    "perseguicao", "combate",
    "efeito",
    "guerreiro", "faca", "lanca", "corrente", "arco", "martelo",
    "item", "idade",
}

# Palavras que sinalizam uso de mecânica na mesa.
TRIGGERS = {
    "teste", "testes", "testa", "testar", "rola", "rolar", "role",
    "rolou", "faz", "fazer", "faca", "faça", "fiz", "pericia", "pericias",
    "prova", "dificuldade", "dt", "treinado", "bonus", "checagem", "dado",
    "dados", "d20", "conjura", "conjurar", "conjuro", "ritual", "gasta",
    "gastar", "recupera", "recuperar", "perde", "perder", "sofre", "sofrer",
    "reduz", "ataque", "atacar", "ataca", "pontos", "ponto", "resistencia",
    "lanca", "lancar", "lanco", "usa", "usar", "ativa", "ativar", "ativo",
    "habilidade", "equipa", "equipar", "veste", "vestir", "armadura",
    "mascara", "trilha", "vestimenta", "acessorio", "utensilio", "combo",
    "combina", "combinacao", "sinergia",
    "classe", "combatente", "especialista", "ocultista", "sobrevivente",
    "nex", "aumenta", "mudanca", "marco", "perseguicao", "persegue",
    "escapa", "combate", "turno", "rodada",
    "efeito", "condicao", "dt", "passar", "sair", "resistir",
    "versatilidade", "arma", "armas", "empunha", "empunhar", "golpe",
    "dispara", "disparar", "tiro", "municao",
}

_AMBIGUOUS_WEAPONS = {"faca", "lanca", "corrente", "arco", "martelo"}
_WEAPON_TRIGGERS = {
    "arma", "armas", "ataque", "atacar", "ataca", "dano", "equipa", "equipar",
    "empunha", "empunhar", "golpe", "dispara", "disparar", "tiro", "municao",
}

_BONUS_RE = re.compile(
    r"\b(?:b[oô]nus(?:\s+de)?|recebe|ganha|concede|fornece)\s*"
    r"(?P<value>[+\-]\s*\d+|\d+d20)\b"
    r"(?:\s+(?:em|no|na|nos|nas|para)\s+"
    r"(?P<context>[^,.;]+?)(?=\s+e\s+(?:o|a|um|uma)\s+|[,.;]|$))?",
    re.I,
)
_DAMAGE_MULTIPLIER_RES = [
    re.compile(r"\b(?:o\s+)?dano\s+(?P<value>dobrado|triplicado|x\s*[2-9])\b", re.I),
    re.compile(r"\b(?P<value>dobro|triplo)\s+(?:do\s+)?dano\b", re.I),
    re.compile(r"\bmultiplica(?:r|do)?\s+(?:o\s+)?dano\s+por\s+(?P<value>[2-9])\b", re.I),
]
_NEX_CHANGE_RE = re.compile(
    r"\bnex\b[^,.;\d]{0,30}(?P<value>\d{1,3})\s*(?:%|por\s+cento)",
    re.I,
)
_DT_RE = re.compile(
    r"(?:(?:teste\s+de\s+)?(?P<test>Fortitude|Reflexos|Vontade)\s*"
    r"(?:\([^)]*\)\s*)?)?\bDT\s*(?P<value>\d{1,3})\b"
    r"(?:\s+(?P<context>para\s+[^,.;]+))?",
    re.I,
)
_AGE_RE = re.compile(r"\b(?:idade\s*(?:de|é|e)?\s*)?(?P<value>\d{1,3})\s*anos\b", re.I)


def _age_band(age: int) -> str:
    if age <= 12:
        return "Criança"
    if age <= 17:
        return "Adolescente"
    if age <= 24:
        return "Jovem"
    if age <= 44:
        return "Adulto"
    if age <= 64:
        return "Maduro"
    return "Idoso"


def is_explanation_question(text: str) -> bool:
    norm = normalize_term(text)
    prompts = ("o que", "como funciona", "qual efeito", "o que faz",
               "o que da", "me explica", "explique", "qual a regra")
    return any(prompt in norm for prompt in prompts)


@dataclass
class Detection:
    term: str
    category: str
    score: float
    meta: dict
    summary: str | None
    page: int | None
    loc: str | None
    source: str | None
    matched_text: str
    tier: str | None = None            # 'Discente'|'Verdadeiro'|'Afinidade'
    tier_summary: str | None = None    # texto do aprimoramento falado


def format_ref(d: Detection) -> str:
    """'Livro p.135' (página real) ou 'Homebrew · Seção X' (sem paginação)."""
    if not d.source:
        return ""
    loc = d.loc or (f"p.{d.page}" if d.page else None)
    return f"{d.source} · {loc}" if loc else d.source


class Detector:
    def __init__(self, lexicon: list[dict], threshold: float = 86.0):
        self.threshold = threshold
        # pré-computa cada forma: (form, form_ns, form_ph_ns, nwords, entry)
        self.forms: list[tuple] = []
        for e in lexicon:
            raw_forms = {normalize_term(e["term"])}
            for a in e.get("aliases", []):
                raw_forms.add(normalize_term(a))
            for f in raw_forms:
                if not f:
                    continue
                nwords = len(f.split())
                form_ns = f.replace(" ", "")
                form_ph = phonetic_pt(f).replace(" ", "")
                self.forms.append((f, form_ns, form_ph, nwords, e))
        self.forms.sort(key=lambda x: -x[3])   # expressões maiores primeiro

    @staticmethod
    def _threshold_for(form_ns: str, nwords: int, base: float) -> float:
        if len(form_ns) <= 3:
            return 100.0            # siglas exigem match exato
        if nwords >= 3:
            return 84.0
        if nwords == 2:
            return 85.0
        return max(base, 88.0)      # 1 palavra: rígido

    def detect(self, text: str) -> list[Detection]:
        norm = normalize_term(text)
        if not norm:
            return []
        tokens = norm.split()
        ph_tokens = phonetic_pt(norm).split()
        # alinhamento defensivo (phonetic_pt preserva a contagem de palavras)
        if len(ph_tokens) != len(tokens):
            ph_tokens = tokens
        found: dict[tuple[str, str], Detection] = {}

        for form, form_ns, form_ph, nwords, entry in self.forms:
            thr = self._threshold_for(form_ns, nwords, self.threshold)
            best, best_span = 0.0, ""
            # janelas de nwords-1 a nwords+1 tokens (absorve divisão/junção)
            for w in range(max(1, nwords - 1), nwords + 2):
                if w > len(tokens):
                    continue
                for i in range(0, len(tokens) - w + 1):
                    span_toks = tokens[i:i + w]
                    span = " ".join(span_toks)
                    span_ns = "".join(span_toks)
                    # guarda de comprimento: evita casar janela curta com
                    # termo longo (e vice-versa), fonte de falso-positivo
                    if len(form_ns) > 3 and not (
                            0.6 * len(form_ns) <= len(span_ns) <= 1.7 * len(form_ns)):
                        continue
                    # 1) espaçado, 2) colado (splits), 3) fonético colado
                    s = fuzz.ratio(form, span)
                    if len(form_ns) > 3:
                        s = max(s, fuzz.ratio(form_ns, span_ns))
                        span_ph = "".join(ph_tokens[i:i + w])
                        s = max(s, fuzz.ratio(form_ph, span_ph))
                    if s > best:
                        best, best_span = s, span
            if best >= thr:
                key = (entry["term"], entry["category"])
                if key not in found or best > found[key].score:
                    found[key] = Detection(
                        term=entry["term"], category=entry["category"],
                        score=round(best, 1), meta=entry.get("meta", {}),
                        summary=entry.get("summary"),
                        page=entry.get("page"), loc=entry.get("loc"),
                        source=entry.get("title") or entry.get("filename"),
                        matched_text=best_span,
                    )

        for detection in self._detect_structural(text):
            found[(detection.term, detection.category)] = detection

        results = sorted(found.values(), key=lambda d: -d.score)
        weapons = [d for d in results if d.category == "arma"]
        results = [d for d in results if d.category != "arma"]
        results = self._gate_ambiguous(results, tokens)
        has_weapon_trigger = bool(set(tokens) & _WEAPON_TRIGGERS)
        results.extend(
            detection for detection in weapons
            if not self._weapon_false_positive(detection, tokens, has_weapon_trigger)
        )
        results = self._suppress_substrings(results)
        results = self._attach_tiers(results, tokens)
        return self._attach_track_context(results, tokens)

    @staticmethod
    def _weapon_false_positive(
        detection: Detection, tokens: list[str], has_weapon_trigger: bool
    ) -> bool:
        term = normalize_term(detection.term)
        if term not in _AMBIGUOUS_WEAPONS or has_weapon_trigger or len(tokens) == 1:
            return False
        if term == "faca" and "teste" in tokens:
            return True
        if term == "lanca" and any(token in tokens for token in ("ritual", "conjura")):
            return True
        return False

    @staticmethod
    def _attach_track_context(dets: list[Detection], tokens: list[str]) -> list[Detection]:
        if "versatilidade" not in tokens:
            return dets
        marker = tokens.index("versatilidade")
        tail = set(tokens[marker + 1:])
        for detection in dets:
            if detection.category == "trilha" and normalize_term(detection.term) in " ".join(tail):
                detection.meta = {**detection.meta, "selection": "versatilidade"}
        return dets

    @staticmethod
    def _detect_structural(text: str) -> list[Detection]:
        detections: list[Detection] = []
        nex_match = _NEX_CHANGE_RE.search(text)
        if nex_match:
            value = int(nex_match.group("value"))
            if 0 <= value <= 100:
                detections.append(Detection(
                    term=f"NEX {value}%", category="nex", score=100.0,
                    meta={"nex": value}, summary=f"Marco ou alteração para NEX {value}%.",
                    page=None, loc=None, source=None, matched_text=nex_match.group(0),
                ))
        age_match = _AGE_RE.search(text)
        if age_match:
            age = int(age_match.group("value"))
            if 1 <= age <= 150:
                band = _age_band(age)
                detections.append(Detection(
                    term=f"Idade {age} anos", category="idade", score=100.0,
                    meta={"age": age, "band": band},
                    summary=f"Faixa etária: {band}.", page=None, loc=None,
                    source=None, matched_text=age_match.group(0),
                ))
        for match in _DT_RE.finditer(text):
            value = int(match.group("value"))
            test = match.group("test")
            context = (match.group("context") or "").strip()
            summary = f"Teste de {test} contra DT {value}" if test else f"Teste contra DT {value}"
            if context:
                summary += f" {context}"
            matched_text = match.group(0)
            if context:
                matched_text = matched_text[:-len(context)].strip()
            detections.append(Detection(
                term=f"DT {value}", category="dt", score=100.0,
                meta={"dt": value, "test": test, "context": context or None},
                summary=summary + ".", page=None, loc=None, source=None,
                matched_text=matched_text,
            ))
        for match in _BONUS_RE.finditer(text):
            value = re.sub(r"\s+", "", match.group("value"))
            context = (match.group("context") or "").strip()
            summary = f"Bônus {value}"
            if context:
                summary += f" aplicado em {context}"
            detections.append(Detection(
                term=f"Bônus {value}", category="bonus", score=100.0,
                meta={"value": value, "context": context or None},
                summary=summary, page=None, loc=None, source=None,
                matched_text=match.group(0),
            ))

        for pattern in _DAMAGE_MULTIPLIER_RES:
            match = pattern.search(text)
            if not match:
                continue
            value = match.group("value").lower().replace(" ", "")
            labels = {"2": "dobro", "3": "triplo", "dobrado": "dobro",
                      "triplicado": "triplo", "x2": "dobro", "x3": "triplo"}
            label = labels.get(value, value)
            detections.append(Detection(
                term=f"Dano {label}", category="multiplicador", score=100.0,
                meta={"multiplier": label},
                summary=f"Multiplicador de dano: {label}.",
                page=None, loc=None, source=None, matched_text=match.group(0),
            ))
            break
        return detections

    # palavras faladas -> chave do aprimoramento no meta
    _TIER_WORDS = {
        "discente": "discente",
        "verdadeiro": "verdadeiro", "verdadeira": "verdadeiro",
        "afinidade": "afinidade",
    }

    @classmethod
    def _attach_tiers(cls, dets: list[Detection],
                      tokens: list[str]) -> list[Detection]:
        """Reconhece o combo falado 'Ritual + Discente/Verdadeiro/Afinidade'.

        Ex.: 'conjuro Eletrocussão Verdadeira' → anexa o texto da versão
        Verdadeiro ao card. O tier só é anexado a rituais/poderes que
        possuem aquele aprimoramento extraído dos livros.
        """
        spoken = {cls._TIER_WORDS[t] for t in tokens if t in cls._TIER_WORDS}
        if not spoken:
            return dets
        for d in dets:
            if d.category not in ("ritual", "poder"):
                continue
            for key in ("verdadeiro", "discente", "afinidade"):
                if key in spoken and d.meta.get(key):
                    d.tier = key.capitalize()
                    d.tier_summary = d.meta[key]
                    break
        return dets

    @staticmethod
    def _gate_ambiguous(dets: list[Detection], tokens: list[str]) -> list[Detection]:
        """Termo que também é palavra comum só conta com um gatilho de jogo."""
        has_trigger = any(t in TRIGGERS for t in tokens)
        kept = []
        for d in dets:
            if d.term == "Regra de Idade" and not any(
                token in tokens for token in ("idade", "etaria", "etario")
            ):
                continue
            amb = (d.matched_text in AMBIGUOUS_FORMS
                   or normalize_term(d.term) in AMBIGUOUS_FORMS)
            if amb and not has_trigger:
                continue
            kept.append(d)
        return kept

    @staticmethod
    def _suppress_substrings(dets: list[Detection]) -> list[Detection]:
        """Remove detecção cujo trecho casado está contido no de outra maior.

        Ex.: "presença do medo" (ritual) engole "presença" (atributo).
        """
        kept: list[Detection] = []
        spans = sorted(dets, key=lambda d: -len(d.matched_text))
        for d in spans:
            covered = any(
                d is not o
                and d.matched_text
                and d.matched_text in o.matched_text
                and len(d.matched_text) < len(o.matched_text)
                and o.score >= d.score - 0.5      # não engole um match mais forte
                for o in kept
            )
            if not covered:
                kept.append(d)
        return sorted(kept, key=lambda d: -d.score)
