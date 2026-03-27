from __future__ import annotations

import argparse
import json
import random
import sys
import textwrap
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# Allow importing DocumentValidator from the src package
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.analysis import DocumentValidator

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise SystemExit(
        "Missing dependency 'reportlab'. Install it with: pip3 install reportlab"
    ) from exc


VALID_DOC_TYPES = {
    "IndiceProcedimento.html",
    "Ricorso",
    "Procura",
    "Atto di nascita",
    "Atto di morte",
    "Certificato Negativo di Naturalizzazione",
    "Apostille",
    "Traduzione",
    "Asseverazione",
}

SUPPORTED_PRIMARY_DOC_TYPES = {
    "IndiceProcedimento.html",
    "Ricorso",
    "Procura",
    "Atto di nascita",
    "Atto di morte",
    "Certificato Negativo di Naturalizzazione",
}

ACCESSORY_TARGET_DOC_TYPES = {
    "Procura",
    "Atto di nascita",
    "Atto di morte",
    "Certificato Negativo di Naturalizzazione",
}

USELESS_DOC_TYPES = [
    "Nota Spese",
    "Avviso Udienza",
    "Comunicazione PEC",
    "Bozza Sentenza",
    "Documenti Personali Vari",
]

ITALIAN_NAMES = [
    ("Luca", "Bianchi"),
    ("Elena", "Rossi"),
    ("Marco", "Moretti"),
    ("Giulia", "Conti"),
    ("Matteo", "Gallo"),
    ("Francesca", "Leoni"),
    ("Paolo", "Neri"),
    ("Chiara", "Costa"),
    ("Davide", "Lombardi"),
    ("Sara", "Marini"),
]

BRAZIL_CITIES = ["Sao Paulo", "Rio de Janeiro", "Brasilia", "Salvador", "Campinas"]
AREE = ["A", "B", "C", "D", "E"]


@dataclass
class ScenarioConfig:
    include_indice: bool
    include_avo_death: bool
    death_required: bool
    include_useless_docs: bool
    include_useless_apostilles: bool
    include_irrelevant_cert_chains: bool
    descendants_with_married_name: bool
    all_docs_in_single_pdf: bool
    max_docs_per_pdf: int


def random_person(rng: random.Random) -> dict[str, str]:
    nome, cognome = rng.choice(ITALIAN_NAMES)
    return {"nome": nome, "cognome": cognome}


def random_date(rng: random.Random, start_year: int, end_year: int) -> str:
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    span = (end - start).days
    picked = start + timedelta(days=rng.randint(0, max(1, span)))
    return picked.strftime("%d-%m-%Y")


def build_family(rng: random.Random, descendants: int) -> dict[str, Any]:
    avo = random_person(rng)
    avo["nome"] = f"{avo['nome']} {rng.choice(['Luigi', 'Maria', 'Carlo'])}"

    lineage = [avo]
    parent = avo

    for _ in range(descendants):
        child = random_person(rng)
        if rng.random() < 0.35:
            child["nome"] = f"{child['nome']} {rng.choice(['Ana', 'Joao', 'Luz'])}"
        lineage.append(child)
        parent = child

    ricorrenti = [lineage[-1]]
    if descendants > 2 and rng.random() < 0.45:
        ricorrenti.append(lineage[-2])

    return {
        "avo": avo,
        "lineage": lineage,
        "ricorrenti": ricorrenti,
    }


def make_indice(rng: random.Random) -> dict[str, Any]:
    interventi = rng.random() < 0.3
    intervenuti = []
    if interventi:
        for _ in range(rng.randint(1, 2)):
            p = random_person(rng)
            intervenuti.append({"nome": p["nome"], "cognome": p["cognome"], "data": random_date(rng, 2024, 2025)})

    return {
        "document_type": "IndiceProcedimento.html",
        "schema": {
            "numero_anno_ruolo": f"RG {rng.randint(100, 999)}/{rng.choice([2024, 2025])}",
            "data_iscrizione": random_date(rng, 2024, 2025),
            "iscrizione_post_28_02_2023": "OK",
            "iscrizione_pre_27_03_2025": "OK" if rng.random() < 0.85 else "KO",
            "comparsa_avvocatura": "SI" if rng.random() < 0.5 else "NO",
            "data_comparsa_avvocatura": random_date(rng, 2024, 2025),
            "visibilita_pm": "SI" if rng.random() < 0.5 else "NO",
            "data_visibilita_pm": random_date(rng, 2024, 2025),
            "interventi": "SI" if interventi else "NO",
            "numero_interventi": len(intervenuti),
            "intervenuti": intervenuti,
        },
    }


def make_ricorso(rng: random.Random, family: dict[str, Any], married_name: bool) -> dict[str, Any]:
    avvocato = random_person(rng)
    ricorrenti = []

    for r in family["ricorrenti"]:
        r_copy = {"nome": r["nome"], "cognome": r["cognome"], "nazionalita": "Brasiliana"}
        if married_name and r is family["ricorrenti"][0]:
            r_copy["cognome"] = f"{r_copy['cognome']}-Silva"
        ricorrenti.append(r_copy)

    lineage = [{"nome": p["nome"], "cognome": p["cognome"]} for p in family["lineage"]]

    return {
        "document_type": "Ricorso",
        "schema": {
            "avvocati": [avvocato],
            "numero_ricorrenti": len(ricorrenti),
            "ricorrenti_maggiorenni": ricorrenti,
            "ricorrenti_minorenni": [],
            "ricorrenti_per_matrimonio": [],
            "linea_discendenza": lineage,
            "racconto_linea_discendenza": "Linea di discendenza ricostruita da certificati esteri e italiani allegati al fascicolo.",
            "riassunto_linea_discendenza": " -> ".join(f"{p['nome']} {p['cognome']}" for p in lineage),
            "coerenza_linea_discendenza": "SI",
            "proveniente_dal_brasile": "SI",
            "data_ricorso": random_date(rng, 2024, 2025),
        },
    }


def make_procura(
    rng: random.Random,
    ricorrente: dict[str, str],
    avvocati: list[dict[str, str]],
    before_iso: str | None = None,
) -> dict[str, Any]:
    """Generate a Procura document.

    ``before_iso`` constrains ``data_procura`` to be strictly before that date
    (format ``DD-MM-YYYY``), ensuring the procura always pre-dates the ricorso.
    """
    in_italia = rng.random() < 0.35
    in_italiano = in_italia or rng.random() < 0.3

    if before_iso:
        try:
            upper = date(*reversed([int(x) for x in before_iso.split("-")]))
        except Exception:
            upper = None
    else:
        upper = None

    if upper is not None:
        # Generate a date in 2024-2025 that is strictly before the ricorso date.
        # Use the day before the ricorso as the hard upper bound.
        end = min(upper - timedelta(days=1), date(2025, 12, 31))
        start = date(2024, 1, 1)
        span = (end - start).days
        if span < 1:
            # Fallback: just use 30 days before
            end = upper - timedelta(days=1)
            start = end - timedelta(days=365)
            span = (end - start).days
        picked = start + timedelta(days=rng.randint(0, max(1, span)))
        data_procura = picked.strftime("%d-%m-%Y")
    else:
        data_procura = random_date(rng, 2024, 2025)

    return {
        "document_type": "Procura",
        "schema": {
            "soggetto": [
                {
                    "nome": ricorrente["nome"],
                    "cognome": ricorrente["cognome"],
                    "minorenne": "NO",
                    "rappresentanti_legali": [],
                    "firma_presente": "OK",
                }
            ],
            "oggetto": "delego a rappresentarmi nel giudizio per il riconoscimento della cittadinanza italiana",
            "avvocati": avvocati,
            "tribunale_brescia_indicato": "SI" if rng.random() < 0.85 else "NO",
            "tribunale_indicato": "Tribunale civile competente",
            "data_procura": data_procura,
            "rilasciata_in_italia": "OK" if in_italia else "NO",
            "scritta_in_italiano": "OK" if in_italiano else "NO",
        },
    }


def make_birth(rng: random.Random, person: dict[str, str], father: dict[str, str], mother: dict[str, str], italy: bool) -> dict[str, Any]:
    return {
        "document_type": "Atto di nascita",
        "schema": {
            "soggetto": {"nome": person["nome"], "cognome": person["cognome"]},
            "tipo": "anagrafico" if rng.random() < 0.75 else "parrocchiale",
            "timbro_diocesi": "OK" if rng.random() < 0.7 else "NO",
            "comune_nascita": rng.choice(["Brescia", "Bergamo", "Cremona", "Mantova"]) if italy else rng.choice(BRAZIL_CITIES),
            "provincia": rng.choice(["brescia", "bergamo", "cremona", "mantova"]) if italy else "altro",
            "padre": father,
            "madre": mother,
            "data_nascita": random_date(rng, 1870 if italy else 1930, 1965 if italy else 2010),
            "area_nascita": rng.choice(AREE),
            "stato": "Italia" if italy else "Brasile",
        },
    }


def make_avo_death(rng: random.Random, avo: dict[str, str]) -> dict[str, Any]:
    return {
        "document_type": "Atto di morte",
        "schema": {
            "soggetto": {"nome": avo["nome"], "cognome": avo["cognome"]},
            "data_decesso": random_date(rng, 1900, 1995),
        },
    }


def make_cnn(rng: random.Random, avo: dict[str, str], avo_birth_date: str) -> dict[str, Any]:
    alias = {
        "nome": avo["nome"].split()[0],
        "cognome": f"{avo['cognome'][: max(2, len(avo['cognome']) - 1)]}o",
    }
    return {
        "document_type": "Certificato Negativo di Naturalizzazione",
        "schema": {
            "soggetto": {"nome": avo["nome"], "cognome": avo["cognome"]},
            "pseudonimi": [alias] if rng.random() < 0.6 else [],
            "formula_negativa_presente": "OK",
            "data_nascita": avo_birth_date,
        },
    }


def make_apostille(doc_type: str, soggetto: dict[str, str] | list[dict[str, str]], original_doc: str | None = None) -> dict[str, Any]:
    subj_list = soggetto if isinstance(soggetto, list) else [soggetto]
    schema = {
        "oggetto": {
            "document_type": doc_type,
            "soggetto": [{"nome": p["nome"], "cognome": p["cognome"]} for p in subj_list],
        }
    }
    if original_doc:
        schema["oggetto"]["documento_originale"] = original_doc

    return {
        "document_type": "Apostille",
        "schema": schema,
    }


def make_translation(doc_type: str, soggetto: dict[str, str], sede: str) -> dict[str, Any]:
    return {
        "document_type": "Traduzione",
        "schema": {
            "oggetto": {
                "document_type": doc_type,
                "soggetto": [{"nome": soggetto["nome"], "cognome": soggetto["cognome"]}],
            },
            "sede_traduttore": sede,
        },
    }


def make_asseverazione(doc_type: str, soggetto: dict[str, str], original_doc: str) -> dict[str, Any]:
    return {
        "document_type": "Asseverazione",
        "schema": {
            "oggetto": {
                "document_type": doc_type,
                "documento_originale": original_doc,
                "soggetto": [{"nome": soggetto["nome"], "cognome": soggetto["cognome"]}],
            }
        },
    }


def make_useless_doc(rng: random.Random) -> dict[str, Any]:
    doc_type = rng.choice(USELESS_DOC_TYPES)
    return {
        "document_type": doc_type,
        "schema": {
            "id": f"UD-{rng.randint(1000, 9999)}",
            "descrizione": "Documento non pertinente ai fini della verifica di cittadinanza.",
            "data": random_date(rng, 2023, 2025),
        },
    }


def make_irrelevant_marriage_certificate(rng: random.Random) -> tuple[dict[str, Any], list[dict[str, str]]]:
    spouse_a = random_person(rng)
    spouse_b = random_person(rng)
    doc = {
        "document_type": "Certificato di matrimonio",
        "schema": {
            "soggetti": [spouse_a, spouse_b],
            "luogo": rng.choice(BRAZIL_CITIES),
            "data_matrimonio": random_date(rng, 1930, 2020),
            "note": "Documento non richiesto ai fini del riconoscimento richiesto.",
        },
    }
    return doc, [spouse_a, spouse_b]


def is_expected_supported_document(doc: dict[str, Any]) -> bool:
    doc_type = doc.get("document_type")

    if doc_type in SUPPORTED_PRIMARY_DOC_TYPES:
        return True

    if doc_type not in {"Apostille", "Traduzione", "Asseverazione"}:
        return False

    obj = doc.get("schema", {}).get("oggetto", {})
    target_doc_type = obj.get("document_type")
    original_doc_type = obj.get("documento_originale")

    if target_doc_type in ACCESSORY_TARGET_DOC_TYPES:
        return True

    # Apostille/asseverazione for translations are valid only when the original
    # translated document is one of the supported target document types.
    if target_doc_type == "Traduzione" and original_doc_type in ACCESSORY_TARGET_DOC_TYPES:
        return True

    return False


def document_to_text(doc: dict[str, Any], idx: int) -> str:
    title = doc["document_type"]
    body = json.dumps(doc["schema"], ensure_ascii=False, indent=2)
    return f"DOCUMENTO {idx} - {title}\n{body}\n"


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _humanize_key(key: str) -> str:
    parts = re.split(r"[_\-]+", key)
    return " ".join(p.capitalize() for p in parts)


def _flatten_schema_lines(prefix: str, value: Any) -> list[str]:
    if isinstance(value, dict):
        lines: list[str] = []
        for k, v in value.items():
            p = f"{prefix}{_humanize_key(k)}"
            if isinstance(v, (dict, list)):
                lines.extend(_flatten_schema_lines(f"{p} / ", v))
            else:
                lines.append(f"{p}: {_stringify(v)}")
        return lines
    if isinstance(value, list):
        lines: list[str] = []
        for i, item in enumerate(value, start=1):
            p = f"{prefix}Elemento {i}"
            if isinstance(item, (dict, list)):
                lines.extend(_flatten_schema_lines(f"{p} / ", item))
            else:
                lines.append(f"{p}: {_stringify(item)}")
        return lines
    return [f"{prefix}: {_stringify(value)}"]


def format_document_content(doc: dict[str, Any]) -> list[str]:
    doc_type = doc["document_type"]
    schema = doc.get("schema", {})

    if doc_type == "Ricorso":
        ric_names = ", ".join(
            f"{p.get('nome', '')} {p.get('cognome', '')}" for p in schema.get("ricorrenti_maggiorenni", [])
        ) or "N.D."
        lawyer_names = ", ".join(
            f"{a.get('nome', '')} {a.get('cognome', '')}" for a in schema.get("avvocati", [])
        ) or "N.D."
        line = schema.get("riassunto_linea_discendenza", "N.D.")
        return [
            "TRIBUNALE ORDINARIO DI BRESCIA",
            "RICORSO AI SENSI DELL'ART. 281-DECIES C.P.C.",
            f"Ricorrenti: {ric_names}",
            f"Difensore/i: {lawyer_names}",
            f"Data in calce al ricorso: {schema.get('data_ricorso', 'N.D.')}",
            f"Provenienza dal Brasile: {schema.get('proveniente_dal_brasile', 'N.D.')}",
            "",
            "FATTO",
            schema.get("racconto_linea_discendenza", "N.D."),
            f"Linea di discendenza allegata: {line}",
            "",
            "DIRITTO",
            "I ricorrenti chiedono il riconoscimento della cittadinanza italiana iure sanguinis.",
            "P.Q.M. si chiede l'accoglimento del ricorso.",
        ]

    if doc_type == "Procura":
        soggetti = schema.get("soggetto", [])
        names = ", ".join(f"{p.get('nome', '')} {p.get('cognome', '')}" for p in soggetti) or "N.D."
        avvocati = ", ".join(f"{a.get('nome', '')} {a.get('cognome', '')}" for a in schema.get("avvocati", [])) or "N.D."
        return [
            "PROCURA ALLE LITI",
            f"Il sottoscritto/i {names} delega a rappresentarlo e difenderlo nel giudizio.",
            f"Difensore/i nominati: {avvocati}",
            f"Oggetto del giudizio: {schema.get('oggetto', 'N.D.')}",
            f"Tribunale indicato nel testo: {schema.get('tribunale_indicato', 'N.D.')}",
            f"Tribunale di Brescia indicato: {schema.get('tribunale_brescia_indicato', 'N.D.')}",
            f"Data rilascio procura: {schema.get('data_procura', 'N.D.')}",
            f"Rilasciata in Italia: {schema.get('rilasciata_in_italia', 'N.D.')}",
            f"Scritta in italiano: {schema.get('scritta_in_italiano', 'N.D.')}",
            "Conferiti tutti i poteri di legge, compresa rinuncia agli atti e impugnazione.",
            "Firma/e del/i conferente/i in calce.",
        ]

    if doc_type == "Atto di nascita":
        soggetto = schema.get("soggetto", {})
        padre = schema.get("padre", {})
        madre = schema.get("madre", {})
        matricola = f"{random.randint(1000000,9999999)} {random.randint(10,99)} {random.randint(1000,9999)}"
        return [
            "CERTIDAO DE NASCIMENTO EM INTEIRO TEOR / ATTO DI NASCITA",
            f"Matricula: {matricola}",
            f"Nominativo: {soggetto.get('nome', '')} {soggetto.get('cognome', '')}",
            f"Filho(a) de: {padre.get('nome', '')} {padre.get('cognome', '')} e {madre.get('nome', '')} {madre.get('cognome', '')}",
            f"Data di nascita: {schema.get('data_nascita', 'N.D.')}",
            f"Comune/Stato: {schema.get('comune_nascita', 'N.D.')} / {schema.get('stato', 'N.D.')}",
            f"Tipo certificato: {schema.get('tipo', 'N.D.')}",
            f"Timbro diocesi: {schema.get('timbro_diocesi', 'N.D.')}",
            "Avvertenza: la data di registrazione puo differire dalla data effettiva di nascita.",
        ]

    if doc_type == "Atto di morte":
        soggetto = schema.get("soggetto", {})
        matricola = f"{random.randint(1000000,9999999)} {random.randint(10,99)} {random.randint(1000,9999)}"
        return [
            "CERTIDAO DE INTEIRO TEOR DE OBITO / ATTO DI MORTE",
            f"Matricula: {matricola}",
            f"Defunto: {soggetto.get('nome', '')} {soggetto.get('cognome', '')}",
            f"Data decesso: {schema.get('data_decesso', 'N.D.')}",
            "Consta no assento de obito a data do falecimento.",
            "Documento rilasciato in copia conforme.",
        ]

    if doc_type == "Certificato Negativo di Naturalizzazione":
        soggetto = schema.get("soggetto", {})
        pseudonimi = schema.get("pseudonimi", [])
        aliases = ", ".join(f"{p.get('nome', '')} {p.get('cognome', '')}" for p in pseudonimi) or "Nessuno"
        return [
            "CERTIFICADO NEGATIVO DE NATURALIZACAO",
            f"Soggetto: {soggetto.get('nome', '')} {soggetto.get('cognome', '')}",
            f"Data di nascita dichiarata: {schema.get('data_nascita', 'N.D.')}",
            f"Formula negativa presente: {schema.get('formula_negativa_presente', 'N.D.')}",
            f"Pseudonimi/alias: {aliases}",
            "Nao consta, ate a presente data, registro de naturalizacao em nome do requerente.",
            "Certidao emitida pelo Ministerio da Justica.",
        ]

    if doc_type == "Traduzione":
        obj = schema.get("oggetto", {})
        people = ", ".join(f"{p.get('nome', '')} {p.get('cognome', '')}" for p in obj.get("soggetto", [])) or "N.D."
        return [
            "TRADUZIONE IN LINGUA ITALIANA",
            f"Documento tradotto: {obj.get('document_type', 'N.D.')}",
            f"Soggetti citati: {people}",
            f"Sede traduttore: {schema.get('sede_traduttore', 'N.D.')}",
            "Il sottoscritto traduttore certifica che la presente e traduzione fedele del testo originale.",
        ]

    if doc_type == "Apostille":
        obj = schema.get("oggetto", {})
        people = ", ".join(f"{p.get('nome', '')} {p.get('cognome', '')}" for p in obj.get("soggetto", [])) or "N.D."
        code = f"BR{random.randint(100000,999999)}-{random.randint(1000,9999)}"
        return [
            "CNJ - Conselho Nacional de Justica",
            "BRASIL Apostille (Convention de La Haye du 5 octobre 1961)",
            f"Numero identificativo: {code}",
            "QR-Code: [presente]",
            f"Tipo de Documento: {obj.get('document_type', 'N.D.')}",
            f"Documento originale: {obj.get('documento_originale', 'N.D.')}",
            f"Riferimento soggetti: {people}",
            "Autoridade competente: Cartorio / Tribunal local.",
        ]

    if doc_type == "Asseverazione":
        obj = schema.get("oggetto", {})
        people = ", ".join(f"{p.get('nome', '')} {p.get('cognome', '')}" for p in obj.get("soggetto", [])) or "N.D."
        return [
            "VERBALE DI GIURAMENTO / ASSEVERAZIONE DELLA TRADUZIONE",
            f"Documento asseverato: {obj.get('document_type', 'N.D.')}",
            f"Originale di riferimento: {obj.get('documento_originale', 'N.D.')}",
            f"Soggetti menzionati: {people}",
            "Il traduttore giura di aver bene e fedelmente tradotto il documento.",
        ]

    if doc_type == "IndiceProcedimento.html":
        intervenuti = schema.get("intervenuti", [])
        row_interventi = " / ".join(
            f"{p.get('data','N.D.')} - {p.get('nome','')} {p.get('cognome','')}"
            for p in intervenuti
        ) or "N.D."
        return [
            "indice storico procedimenti",
            f"numero_anno_ruolo: {schema.get('numero_anno_ruolo', 'N.D.')}",
            "",
            "data evento | descrizione | note storico | documenti allegati",
            f"{schema.get('data_iscrizione','N.D.')} | iscritto a ruolo generale | - | Ricorso",
            f"{schema.get('data_comparsa_avvocatura','N.D.')} | comparsa avvocatura: {schema.get('comparsa_avvocatura','N.D.')} | - | Comparsa",
            f"{schema.get('data_visibilita_pm','N.D.')} | visibilita PM: {schema.get('visibilita_pm','N.D.')} | - | Comunicazione",
            f"interventi: {schema.get('interventi','N.D.')} ({schema.get('numero_interventi','N.D.')}) | {row_interventi}",
        ]

    lines = [f"{doc_type}"]
    lines.extend(_flatten_schema_lines("", schema))
    return lines


def draw_scan_background(c: canvas.Canvas, width: float, height: float, rng: random.Random) -> None:
    c.setFillColorRGB(0.95, 0.95, 0.93)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # Light horizontal streaks to mimic scanner banding.
    for _ in range(18):
        y = rng.uniform(30, height - 30)
        h = rng.uniform(0.6, 2.0)
        g = rng.uniform(0.88, 0.96)
        c.setFillColorRGB(g, g, g)
        c.rect(0, y, width, h, fill=1, stroke=0)

    # Small speckle noise.
    c.setFillColorRGB(0.75, 0.75, 0.75)
    for _ in range(80):
        x = rng.uniform(10, width - 10)
        y = rng.uniform(10, height - 10)
        r = rng.uniform(0.2, 0.8)
        c.circle(x, y, r, fill=1, stroke=0)


def draw_scan_stamp(c: canvas.Canvas, width: float, height: float, doc_type: str, rng: random.Random) -> None:
    c.saveState()
    c.setStrokeColorRGB(0.65, 0.2, 0.2)
    c.setLineWidth(1.2)
    stamp_x = width - 185 + rng.uniform(-10, 10)
    stamp_y = height - 145 + rng.uniform(-8, 8)
    c.translate(stamp_x, stamp_y)
    c.rotate(rng.uniform(-12, 12))
    c.rect(0, 0, 165, 42, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.65, 0.2, 0.2)
    c.drawString(8, 26, "COPIA CONFORME")
    c.drawString(8, 12, f"TIPO: {doc_type[:20].upper()}")
    c.restoreState()


def render_scan_document(c: canvas.Canvas, width: float, height: float, title: str, idx: int, doc: dict[str, Any]) -> None:
    seed_material = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    local_seed = int.from_bytes(seed_material.encode("utf-8", errors="ignore")[:8] or b"0", "little", signed=False)
    rng = random.Random(local_seed)

    draw_scan_background(c, width, height, rng)

    left = 42
    right = width - 42
    top = height - 42
    line_height = 14
    y = top

    c.setStrokeColorRGB(0.4, 0.4, 0.4)
    c.setLineWidth(0.6)
    c.rect(28, 28, width - 56, height - 56, fill=0, stroke=1)

    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.12, 0.12, 0.12)
    c.drawString(left, y, f"FASCICOLO: {title}  |  DOC {idx:02d}  |  {doc['document_type'].upper()}")
    y -= 22

    c.setFont("Courier", 9)
    c.drawString(left, y, f"Protocollo interno n. {rng.randint(10000, 99999)} / {rng.choice([2023, 2024, 2025])}")
    y -= 16

    lines = format_document_content(doc)
    c.setFont("Times-Roman", 11)
    for line in lines:
        wrapped = textwrap.wrap(line, width=95) or [""]
        for piece in wrapped:
            if y < 54:
                c.setFont("Helvetica-Oblique", 8)
                c.drawString(left, 36, "continua nella pagina successiva")
                c.showPage()
                draw_scan_background(c, width, height, rng)
                y = top
                c.setFont("Times-Roman", 11)

            jitter_x = rng.uniform(-1.8, 1.8)
            jitter_y = rng.uniform(-0.8, 0.8)
            c.drawString(left + jitter_x, y + jitter_y, piece)
            y -= line_height

    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.18, 0.18, 0.18)
    c.drawString(left, 36, f"Pagina scansita - riferimento documento {idx:02d}")
    c.drawRightString(right, 36, f"hash {rng.randint(100000, 999999)}")

    draw_scan_stamp(c, width, height, doc["document_type"], rng)


def render_pdf(output_path: Path, title: str, docs: list[dict[str, Any]]) -> None:
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    # Rule: each logical document starts on a new page.
    for i, doc in enumerate(docs, start=1):
        if i > 1:
            c.showPage()
        render_scan_document(c, width, height, title, i, doc)

    c.save()


def chunk_documents(docs: list[dict[str, Any]], single_pdf: bool, max_docs_per_pdf: int) -> list[list[dict[str, Any]]]:
    if single_pdf:
        return [docs]

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for doc in docs:
        current.append(doc)
        if len(current) >= max_docs_per_pdf:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def add_supporting_docs(rng: random.Random, docs: list[dict[str, Any]], scenario: ScenarioConfig) -> None:
    additional: list[dict[str, Any]] = []

    for doc in list(docs):
        dt = doc["document_type"]

        if dt == "Procura":
            subject = doc["schema"]["soggetto"][0]
            if doc["schema"]["rilasciata_in_italia"] == "NO":
                additional.append(make_apostille("Procura", subject))
            if doc["schema"]["scritta_in_italiano"] == "NO":
                sede = "Estero" if rng.random() < 0.5 else "Italia"
                tr = make_translation("Procura", subject, sede)
                additional.append(tr)
                if sede == "Estero":
                    additional.append(make_apostille("Traduzione", subject, original_doc="Procura"))
                else:
                    additional.append(make_asseverazione("Traduzione", subject, original_doc="Procura"))

        if dt == "Atto di nascita":
            subject = doc["schema"]["soggetto"]
            if doc["schema"]["stato"] != "Italia":
                additional.append(make_apostille("Atto di nascita", subject))
                sede = "Estero" if rng.random() < 0.5 else "Italia"
                tr = make_translation("Atto di nascita", subject, sede)
                additional.append(tr)
                if sede == "Estero":
                    additional.append(make_apostille("Traduzione", subject, original_doc="Atto di nascita"))
                else:
                    additional.append(make_asseverazione("Traduzione", subject, original_doc="Atto di nascita"))

        if dt == "Atto di morte":
            subject = doc["schema"]["soggetto"]
            additional.append(make_apostille("Atto di morte", subject))
            tr = make_translation("Atto di morte", subject, "Estero")
            additional.append(tr)
            additional.append(make_apostille("Traduzione", subject, original_doc="Atto di morte"))

        if dt == "Certificato Negativo di Naturalizzazione":
            subject = doc["schema"]["soggetto"]
            additional.append(make_apostille("Certificato Negativo di Naturalizzazione", subject))
            sede = "Estero" if rng.random() < 0.5 else "Italia"
            tr = make_translation("Certificato Negativo di Naturalizzazione", subject, sede)
            additional.append(tr)
            if sede == "Estero":
                additional.append(make_apostille("Traduzione", subject, original_doc="Certificato Negativo di Naturalizzazione"))
            else:
                additional.append(make_asseverazione("Traduzione", subject, original_doc="Certificato Negativo di Naturalizzazione"))

    docs.extend(additional)


def build_case_documents(rng: random.Random, scenario: ScenarioConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    family = build_family(rng, descendants=rng.randint(2, 4))

    docs: list[dict[str, Any]] = []

    if scenario.include_indice:
        docs.append(make_indice(rng))

    ricorso = make_ricorso(rng, family, married_name=scenario.descendants_with_married_name)
    docs.append(ricorso)

    avvocati = ricorso["schema"]["avvocati"]
    data_ricorso = ricorso["schema"].get("data_ricorso")

    for ric in ricorso["schema"]["ricorrenti_maggiorenni"]:
        docs.append(make_procura(rng, ric, avvocati, before_iso=data_ricorso))

    lineage = family["lineage"]
    avo = lineage[0]

    avo_father = random_person(rng)
    avo_mother = random_person(rng)
    avo_birth = make_birth(rng, avo, avo_father, avo_mother, italy=True)
    if scenario.death_required:
        avo_birth["schema"]["data_nascita"] = random_date(rng, 1840, 1860)
        avo_birth["schema"]["area_nascita"] = rng.choice(["B", "C", "D"])

    docs.append(avo_birth)

    for i, person in enumerate(lineage[1:], start=1):
        father = lineage[i - 1]
        mother = random_person(rng)
        docs.append(make_birth(rng, person, father, mother, italy=False))

    if scenario.include_avo_death:
        docs.append(make_avo_death(rng, avo))

    docs.append(make_cnn(rng, avo, avo_birth["schema"]["data_nascita"]))

    add_supporting_docs(rng, docs, scenario)

    if scenario.include_useless_docs:
        noise_count = rng.randint(2, 5)
        for _ in range(noise_count):
            noise = make_useless_doc(rng)
            docs.append(noise)
            if scenario.include_useless_apostilles and rng.random() < 0.8:
                # Intentionally confusing apostilles linked to unsupported source docs.
                fake_subject = random_person(rng)
                docs.append(make_apostille("Documento non supportato", fake_subject, original_doc=noise["document_type"]))

    if scenario.include_irrelevant_cert_chains:
        chain_count = rng.randint(1, 3)
        for _ in range(chain_count):
            marriage_doc, spouses = make_irrelevant_marriage_certificate(rng)
            docs.append(marriage_doc)

            # Full accessory chain on an irrelevant document to stress extraction logic.
            docs.append(make_apostille("Certificato di matrimonio", spouses))
            docs.append(make_translation("Certificato di matrimonio", spouses[0], "Estero"))
            docs.append(make_apostille("Traduzione", spouses, original_doc="Certificato di matrimonio"))

    expected_extraction = [d for d in docs if is_expected_supported_document(d)]

    rng.shuffle(docs)
    return docs, expected_extraction


def default_scenarios() -> list[ScenarioConfig]:
    return [
        ScenarioConfig(
            include_indice=True,
            include_avo_death=False,
            death_required=False,
            include_useless_docs=True,
            include_useless_apostilles=True,
            include_irrelevant_cert_chains=True,
            descendants_with_married_name=True,
            all_docs_in_single_pdf=True,
            max_docs_per_pdf=50,
        ),
        ScenarioConfig(
            include_indice=True,
            include_avo_death=True,
            death_required=True,
            include_useless_docs=True,
            include_useless_apostilles=True,
            include_irrelevant_cert_chains=True,
            descendants_with_married_name=False,
            all_docs_in_single_pdf=False,
            max_docs_per_pdf=5,
        ),
        ScenarioConfig(
            include_indice=False,
            include_avo_death=True,
            death_required=False,
            include_useless_docs=True,
            include_useless_apostilles=False,
            include_irrelevant_cert_chains=True,
            descendants_with_married_name=True,
            all_docs_in_single_pdf=False,
            max_docs_per_pdf=4,
        ),
    ]


def generate_fascicoli(output_dir: Path, count: int, seed: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    scenarios = default_scenarios()

    fascicoli_root = output_dir / "fascicoli"
    support_root = output_dir / "support"
    fascicoli_root.mkdir(parents=True, exist_ok=True)
    support_root.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        scenario = scenarios[i % len(scenarios)]
        case_name = f"fascicolo_sintetico_{i:03d}"
        case_pdf_dir = fascicoli_root / case_name
        case_support_dir = support_root / case_name
        case_pdf_dir.mkdir(parents=True, exist_ok=True)
        case_support_dir.mkdir(parents=True, exist_ok=True)

        mixed_docs, expected = build_case_documents(rng, scenario)

        chunks = chunk_documents(mixed_docs, scenario.all_docs_in_single_pdf, scenario.max_docs_per_pdf)

        pdf_files = []
        for j, chunk in enumerate(chunks, start=1):
            pdf_name = f"{case_name}_bundle_{j:02d}.pdf"
            pdf_path = case_pdf_dir / pdf_name
            render_pdf(pdf_path, title=case_name, docs=chunk)
            pdf_files.append({
                "file": pdf_name,
                "logical_docs": [d["document_type"] for d in chunk],
                "count": len(chunk),
            })

        (case_support_dir / "expected_extraction.json").write_text(
            json.dumps(expected, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (case_support_dir / "mixed_logical_docs.json").write_text(
            json.dumps(mixed_docs, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        manifest = {
            "case": case_name,
            "seed": seed,
            "pdf_case_dir": str(case_pdf_dir.as_posix()),
            "support_case_dir": str(case_support_dir.as_posix()),
            "scenario": {
                "include_indice": scenario.include_indice,
                "include_avo_death": scenario.include_avo_death,
                "death_required": scenario.death_required,
                "include_useless_docs": scenario.include_useless_docs,
                "include_useless_apostilles": scenario.include_useless_apostilles,
                "include_irrelevant_cert_chains": scenario.include_irrelevant_cert_chains,
                "descendants_with_married_name": scenario.descendants_with_married_name,
                "all_docs_in_single_pdf": scenario.all_docs_in_single_pdf,
                "max_docs_per_pdf": scenario.max_docs_per_pdf,
            },
            "pdf_files": pdf_files,
            "expected_doc_count": len(expected),
            "mixed_doc_count": len(mixed_docs),
        }

        (case_support_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Derive expected analysis checklist by running DocumentValidator against
        # the ground-truth expected_extraction and write it to the support folder
        # so that evaluate_results.py can compare actual pipeline output against it.
        validator_report = DocumentValidator(expected).run()
        (case_support_dir / "expected_report.json").write_text(
            json.dumps(validator_report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic fascicoli with stress-test PDFs and expected extraction JSON."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("res") / "synthetic_fascicoli",
        help="Output directory for generated synthetic cases.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=6,
        help="Number of synthetic fascicoli to generate.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic generation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count <= 0:
        raise SystemExit("--count must be > 0")

    generate_fascicoli(args.output_dir, args.count, args.seed)
    print(f"Generated {args.count} synthetic fascicoli in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
