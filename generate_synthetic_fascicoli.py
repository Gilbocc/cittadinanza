from __future__ import annotations

import argparse
import json
import random
import sys
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
    from reportlab.lib.utils import simpleSplit
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

BRAZILIAN_MALE_NAMES = ["Joao", "Jose", "Carlos", "Antonio", "Paulo", "Pedro", "Marcos", "Mateus", "Rafael", "Diego"]
BRAZILIAN_FEMALE_NAMES = ["Maria", "Ana", "Fernanda", "Juliana", "Patricia", "Camila", "Larissa", "Beatriz", "Carolina", "Renata"]
BRAZILIAN_SURNAMES = ["Silva", "Santos", "Oliveira", "Souza", "Costa", "Pereira", "Rodrigues", "Almeida", "Nunes", "Lima", "Araujo", "Barbosa", "Cardoso", "Mendes", "Ribeiro"]

BRAZIL_CITIES = [
    "Sao Paulo",
    "Rio de Janeiro",
    "Brasilia",
    "Salvador",
    "Campinas",
    "Belo Horizonte",
    "Curitiba",
    "Porto Alegre",
    "Recife",
    "Fortaleza",
    "Santos",
    "Niteroi",
]
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
    inject_lineage_incoherence: bool = False
    inject_marriage_claimants: bool = False
    inject_procura_weakness: bool = False
    drop_one_descendant_birth: bool = False
    selection_weight: float = 1.0


@dataclass
class RenderProfile:
    noise_scale: float
    artifact_scale: float
    jitter_scale: float
    watermark_prob: float
    punch_hole_prob: float
    stamp_prob: float
    seal_prob: float


def random_render_profile(rng: random.Random) -> RenderProfile:
    return RenderProfile(
        noise_scale=rng.uniform(0.65, 1.55),
        artifact_scale=rng.uniform(0.60, 1.70),
        jitter_scale=rng.uniform(0.70, 1.90),
        watermark_prob=rng.uniform(0.20, 0.92),
        punch_hole_prob=rng.uniform(0.15, 0.85),
        stamp_prob=rng.uniform(0.65, 0.98),
        seal_prob=rng.uniform(0.20, 0.85),
    )


def random_person(rng: random.Random, gender: str | None = None) -> dict[str, str]:
    if gender == "M":
        nome = rng.choice(BRAZILIAN_MALE_NAMES)
    elif gender == "F":
        nome = rng.choice(BRAZILIAN_FEMALE_NAMES)
    else:
        nome = rng.choice(BRAZILIAN_MALE_NAMES + BRAZILIAN_FEMALE_NAMES)
    cognome = rng.choice(BRAZILIAN_SURNAMES)
    person = {"nome": nome, "cognome": cognome}
    if gender in {"M", "F"}:
        person["gender"] = gender
    return person


def random_date(rng: random.Random, start_year: int, end_year: int) -> str:
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    span = (end - start).days
    picked = start + timedelta(days=rng.randint(0, max(1, span)))
    return picked.strftime("%d-%m-%Y")


def build_family(rng: random.Random, descendants: int) -> dict[str, Any]:
    avo_gender = rng.choice(["M", "F"])
    avo = random_person(rng, gender=avo_gender)
    middle = rng.choice(["Carlos", "Miguel", "Paulo"]) if avo_gender == "M" else rng.choice(["Maria", "Luz", "Aparecida"])
    avo["nome"] = f"{avo['nome']} {middle}"

    lineage = [avo]
    parent = avo

    for _ in range(descendants):
        child_gender = rng.choice(["M", "F"])
        child = random_person(rng, gender=child_gender)
        if rng.random() < 0.35:
            child["nome"] = f"{child['nome']} {rng.choice(['Joao', 'Carlos', 'Luis'])}" if child_gender == "M" else f"{child['nome']} {rng.choice(['Ana', 'Luz', 'Maria'])}"

        # Simulate realistic surname evolution (double surname, marriage-style changes).
        if rng.random() < 0.40 and parent.get("cognome"):
            parent_surname = str(parent["cognome"]).split()[0]
            if parent_surname and parent_surname not in child["cognome"]:
                if rng.random() < 0.55:
                    child["cognome"] = f"{child['cognome']} {parent_surname}"
                else:
                    child["cognome"] = f"{child['cognome']}-{parent_surname}"
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

    data_iscrizione = random_date(rng, 2024, 2025)
    try:
        iscrizione_dt = date(*reversed([int(x) for x in data_iscrizione.split("-")]))
    except Exception:
        iscrizione_dt = date(2025, 1, 1)
    iscrizione_pre_cutoff = "OK" if iscrizione_dt <= date(2025, 3, 27) else "KO"

    return {
        "document_type": "IndiceProcedimento.html",
        "schema": {
            "numero_anno_ruolo": f"{rng.randint(100, 999)}/{rng.choice([2024, 2025])}",
            "data_iscrizione": data_iscrizione,
            "iscrizione_post_28_02_2023": "OK",
            "iscrizione_pre_27_03_2025": iscrizione_pre_cutoff,
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
    avvocati = [random_person(rng)]
    if rng.random() < 0.35:
        alt = random_person(rng)
        if alt != avvocati[0]:
            avvocati.append(alt)
    ricorrenti = []

    for r in family["ricorrenti"]:
        r_copy = {"nome": r["nome"], "cognome": r["cognome"], "nazionalita": "Brasiliana"}
        if married_name and r is family["ricorrenti"][0]:
            r_copy["cognome"] = f"{r_copy['cognome']}-Souza"
        ricorrenti.append(r_copy)

    lineage = [{"nome": p["nome"], "cognome": p["cognome"]} for p in family["lineage"]]

    pseudo_notes = []
    for person in rng.sample(lineage, k=min(len(lineage), rng.randint(0, 2))):
        base_nome = person["nome"].split()[0]
        base_cognome = person["cognome"].split("-")[0].split()[0]
        if len(base_cognome) > 4:
            variant_surname = base_cognome[:-1]
        else:
            variant_surname = f"{base_cognome}s"
        pseudo_notes.append(f"{person['nome']} {person['cognome']} (alias: {base_nome} {variant_surname})")

    line_summary = " -> ".join(f"{p['nome']} {p['cognome']}" for p in lineage)
    if pseudo_notes:
        narrative = (
            "Linea di discendenza ricostruita da certificati esteri e italiani allegati al fascicolo. "
            f"Nel ricorso risultano varianti anagrafiche/pseudonimi: {'; '.join(pseudo_notes)}."
        )
    else:
        narrative = "Linea di discendenza ricostruita da certificati esteri e italiani allegati al fascicolo."

    return {
        "document_type": "Ricorso",
        "schema": {
            "avvocati": avvocati,
            "numero_ricorrenti": len(ricorrenti),
            "ricorrenti_maggiorenni": ricorrenti,
            "ricorrenti_minorenni": [],
            "ricorrenti_per_matrimonio": [],
            "linea_discendenza": lineage,
            "racconto_linea_discendenza": narrative,
            "riassunto_linea_discendenza": line_summary,
            "coerenza_linea_discendenza": "SI",
            "proveniente_dal_brasile": "SI",
            "data_ricorso": random_date(rng, 2024, 2025),
        },
    }


def _norm_person_key(person: dict[str, str]) -> tuple[str, str]:
    return (
        str(person.get("nome", "")).strip().lower(),
        str(person.get("cognome", "")).strip().lower(),
    )


def _same_person(a: dict[str, str], b: dict[str, str]) -> bool:
    return _norm_person_key(a) == _norm_person_key(b)


def _extract_subjects(doc: dict[str, Any]) -> list[dict[str, str]]:
    schema = doc.get("schema", {})
    if doc.get("document_type") in {"Atto di nascita", "Atto di morte", "Certificato Negativo di Naturalizzazione"}:
        subj = schema.get("soggetto")
        return [subj] if isinstance(subj, dict) else []
    if doc.get("document_type") == "Procura":
        sogg = schema.get("soggetto", [])
        return sogg if isinstance(sogg, list) else []
    obj = schema.get("oggetto", {})
    sogg = obj.get("soggetto", [])
    return sogg if isinstance(sogg, list) else []


def _remove_procura_chain(docs: list[dict[str, Any]], target: dict[str, str], remove_apostille: bool, remove_translation_chain: bool) -> None:
    kept: list[dict[str, Any]] = []
    for doc in docs:
        dt = doc.get("document_type")
        remove = False

        if dt == "Apostille":
            obj = doc.get("schema", {}).get("oggetto", {})
            obj_type = obj.get("document_type")
            obj_original = obj.get("documento_originale")
            subj = (obj.get("soggetto") or [{}])[0]
            if _same_person(subj, target):
                if remove_apostille and obj_type == "Procura":
                    remove = True
                if remove_translation_chain and obj_type == "Traduzione" and obj_original == "Procura":
                    remove = True

        elif dt == "Traduzione":
            obj = doc.get("schema", {}).get("oggetto", {})
            subj = (obj.get("soggetto") or [{}])[0]
            if remove_translation_chain and obj.get("document_type") == "Procura" and _same_person(subj, target):
                remove = True

        elif dt == "Asseverazione":
            obj = doc.get("schema", {}).get("oggetto", {})
            subj = (obj.get("soggetto") or [{}])[0]
            if (
                remove_translation_chain
                and obj.get("document_type") == "Traduzione"
                and obj.get("documento_originale") == "Procura"
                and _same_person(subj, target)
            ):
                remove = True

        if not remove:
            kept.append(doc)

    docs.clear()
    docs.extend(kept)


def _remove_birth_doc_and_chain(docs: list[dict[str, Any]], target: dict[str, str]) -> None:
    kept: list[dict[str, Any]] = []
    for doc in docs:
        dt = doc.get("document_type")
        remove = False

        if dt == "Atto di nascita":
            subj = doc.get("schema", {}).get("soggetto", {})
            if _same_person(subj, target):
                remove = True
        elif dt in {"Apostille", "Traduzione", "Asseverazione"}:
            obj = doc.get("schema", {}).get("oggetto", {})
            subj = (obj.get("soggetto") or [{}])[0]
            if _same_person(subj, target):
                obj_type = obj.get("document_type")
                obj_orig = obj.get("documento_originale")
                if obj_type == "Atto di nascita":
                    remove = True
                if obj_type == "Traduzione" and obj_orig == "Atto di nascita":
                    remove = True

        if not remove:
            kept.append(doc)

    docs.clear()
    docs.extend(kept)


def apply_challenging_variants(
    rng: random.Random,
    scenario: ScenarioConfig,
    docs: list[dict[str, Any]],
    family: dict[str, Any],
    ricorso: dict[str, Any],
) -> None:
    if scenario.inject_lineage_incoherence and rng.random() < 0.55:
        # Keep Ricorso lineage coherent; create mismatch only in documentary chain.
        lineage = family.get("lineage", [])
        ricorrenti = ricorso["schema"].get("ricorrenti_maggiorenni", [])
        descendants = []
        if lineage:
            for p in lineage[1:]:
                if not any(_same_person(p, r) for r in ricorrenti):
                    descendants.append(p)
        if descendants:
            target = rng.choice(descendants)
            _remove_birth_doc_and_chain(docs, target)

    if scenario.inject_marriage_claimants and rng.random() < 0.45:
        lineage = ricorso["schema"].get("linea_discendenza", [])
        lineage_keys = {_norm_person_key(p) for p in lineage if isinstance(p, dict)}
        ricorrenti = ricorso["schema"].get("ricorrenti_maggiorenni", [])
        ric_keys = {_norm_person_key(p) for p in ricorrenti if isinstance(p, dict)}

        # Richiedenti per matrimonio must be distinct from direct-line descendants.
        candidate = random_person(rng)
        tries = 0
        while (_norm_person_key(candidate) in lineage_keys or _norm_person_key(candidate) in ric_keys) and tries < 15:
            candidate = random_person(rng)
            tries += 1

        candidate["nazionalita"] = "Brasiliana"
        ricorso["schema"]["ricorrenti_per_matrimonio"] = [candidate]

    if scenario.inject_procura_weakness and rng.random() < 0.65:
        procure = [d for d in docs if d.get("document_type") == "Procura"]
        if procure:
            proc = rng.choice(procure)
            subject = proc.get("schema", {}).get("soggetto", [{}])[0]
            weakness = rng.choice([
                "missing_signature",
                "wrong_lawyer",
                "late_date",
                "missing_apostille",
                "missing_translation_chain",
            ])

            if weakness == "missing_signature":
                proc["schema"]["soggetto"][0]["firma_presente"] = "KO"
            elif weakness == "wrong_lawyer":
                proc["schema"]["avvocati"] = [random_person(rng)]
            elif weakness == "late_date":
                ricorso_dt = ricorso["schema"].get("data_ricorso")
                try:
                    d0 = date(*reversed([int(x) for x in ricorso_dt.split("-")]))
                    proc["schema"]["data_procura"] = (d0 + timedelta(days=rng.randint(1, 20))).strftime("%d-%m-%Y")
                except Exception:
                    pass
            elif weakness == "missing_apostille":
                proc["schema"]["rilasciata_in_italia"] = "NO"
                _remove_procura_chain(docs, subject, remove_apostille=True, remove_translation_chain=False)
            elif weakness == "missing_translation_chain":
                proc["schema"]["scritta_in_italiano"] = "NO"
                _remove_procura_chain(docs, subject, remove_apostille=False, remove_translation_chain=True)

    if scenario.drop_one_descendant_birth and rng.random() < 0.50:
        lineage = family.get("lineage", [])
        ricorrenti = ricorso["schema"].get("ricorrenti_maggiorenni", [])
        descendants = []
        if lineage:
            for p in lineage[1:]:
                if not any(_same_person(p, r) for r in ricorrenti):
                    descendants.append(p)
        if descendants:
            target = rng.choice(descendants)
            _remove_birth_doc_and_chain(docs, target)


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
            "tribunale_brescia_indicato": "OK" if rng.random() < 0.85 else "KO",
            "tribunale_indicato": "Tribunale civile competente",
            "data_procura": data_procura,
            "rilasciata_in_italia": "OK" if in_italia else "NO",
            "scritta_in_italiano": "OK" if in_italiano else "NO",
        },
    }


def make_birth(rng: random.Random, person: dict[str, str], father: dict[str, str], mother: dict[str, str], italy: bool) -> dict[str, Any]:
    italian_locations = {
        "Brescia": "brescia",
        "Bergamo": "bergamo",
        "Cremona": "cremona",
        "Mantova": "mantova",
    }
    if italy:
        comune_nascita = rng.choice(list(italian_locations.keys()))
        # Keep RNG consumption stable vs previous implementation.
        _ = rng.choice(["brescia", "bergamo", "cremona", "mantova"])
        provincia = italian_locations[comune_nascita]
    else:
        comune_nascita = rng.choice(BRAZIL_CITIES)
        provincia = "altro"

    # Keep only schema-level identity fields in generated birth documents.
    father_doc = {"nome": father.get("nome", ""), "cognome": father.get("cognome", "")}
    mother_doc = {"nome": mother.get("nome", ""), "cognome": mother.get("cognome", "")}

    return {
        "document_type": "Atto di nascita",
        "schema": {
            "soggetto": {"nome": person["nome"], "cognome": person["cognome"]},
            "tipo": "anagrafico" if rng.random() < 0.75 else "parrocchiale",
            "timbro_diocesi": "OK" if rng.random() < 0.7 else "NO",
            "comune_nascita": comune_nascita,
            "provincia": provincia,
            "padre": father_doc,
            "madre": mother_doc,
            "data_nascita": random_date(rng, 1870 if italy else 1930, 1965 if italy else 2010),
            "area_nascita": "A" if italy else "E",
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


def _append_declared_aliases_to_ricorso(ricorso: dict[str, Any], alias_people: list[dict[str, str]]) -> None:
    if not alias_people:
        return

    notes = []
    for p in alias_people:
        nome = str(p.get("nome", "")).strip()
        cognome = str(p.get("cognome", "")).strip()
        if nome or cognome:
            notes.append(f"{nome} {cognome}".strip())

    if not notes:
        return

    schema = ricorso.get("schema", {})
    base = str(schema.get("racconto_linea_discendenza", "")).strip()
    decl = f"Nel ricorso sono dichiarati i seguenti alias/pseudonimi: {'; '.join(notes)}."
    schema["racconto_linea_discendenza"] = f"{base} {decl}".strip() if base else decl


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


def format_document_content(doc: dict[str, Any], rng: random.Random) -> list[str]:
    doc_type = doc["document_type"]
    schema = doc.get("schema", {})

    if doc_type == "Ricorso":
        ric_list = schema.get("ricorrenti_maggiorenni", [])
        ric_matrimonio = schema.get("ricorrenti_per_matrimonio", [])
        ric_names = ", ".join(
            f"{p.get('nome', '')} {p.get('cognome', '')}" for p in ric_list
        ) or "N.D."
        ric_matrimonio_names = ", ".join(
            f"{p.get('nome', '')} {p.get('cognome', '')}" for p in ric_matrimonio
        ) or "Nessuno"
        ric_with_naz = ", ".join(
            f"{p.get('nome', '')} {p.get('cognome', '')} (nazionalita: {p.get('nazionalita', 'N.D.')})" 
            for p in ric_list
        ) or "N.D."
        lawyer_names = ", ".join(
            f"{a.get('nome', '')} {a.get('cognome', '')}" for a in schema.get("avvocati", [])
        ) or "N.D."
        line = schema.get("riassunto_linea_discendenza", "N.D.")
        return [
            "TRIBUNALE ORDINARIO DI BRESCIA",
            "RICORSO AI SENSI DELL'ART. 281-DECIES C.P.C.",
            f"Ricorrenti: {ric_names}",
            f"Ricorrenti con Nazionalita: {ric_with_naz}",
            f"Ricorrenti per matrimonio: {ric_matrimonio_names}",
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
        soggetti_details = "; ".join(
            f"{p.get('nome', '')} {p.get('cognome', '')} (minorenne: {p.get('minorenne', 'N.D.')}, firma: {p.get('firma_presente', 'N.D.')})"
            for p in soggetti
        ) or "N.D."
        return [
            "PROCURA ALLE LITI",
            f"Il sottoscritto/i {names} delega a rappresentarlo e difenderlo nel giudizio.",
            f"Soggetti: {soggetti_details}",
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
        matricola = f"{rng.randint(1000000,9999999)} {rng.randint(10,99)} {rng.randint(1000,9999)}"
        return [
            "CERTIDAO DE NASCIMENTO EM INTEIRO TEOR / ATTO DI NASCITA",
            f"Matricula: {matricola}",
            f"Nominativo: {soggetto.get('nome', '')} {soggetto.get('cognome', '')}",
            f"Filho(a) de: {padre.get('nome', '')} {padre.get('cognome', '')} e {madre.get('nome', '')} {madre.get('cognome', '')}",
            f"Data di nascita: {schema.get('data_nascita', 'N.D.')}",
            f"Comune/Stato: {schema.get('comune_nascita', 'N.D.')} / {schema.get('stato', 'N.D.')}",
            f"Provincia: {schema.get('provincia', 'N.D.')}",
            f"Area di nascita: {schema.get('area_nascita', 'N.D.')}",
            f"Tipo certificato: {schema.get('tipo', 'N.D.')}",
            f"Timbro diocesi: {schema.get('timbro_diocesi', 'N.D.')}",
            "Avvertenza: la data di registrazione puo differire dalla data effettiva di nascita.",
        ]

    if doc_type == "Atto di morte":
        soggetto = schema.get("soggetto", {})
        matricola = f"{rng.randint(1000000,9999999)} {rng.randint(10,99)} {rng.randint(1000,9999)}"
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
        code = f"BR{rng.randint(100000,999999)}-{rng.randint(1000,9999)}"
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


def draw_scan_background(c: canvas.Canvas, width: float, height: float, rng: random.Random, profile: RenderProfile) -> None:
    base_tone = rng.uniform(0.92, 0.97)
    c.setFillColorRGB(base_tone, base_tone, base_tone - 0.01)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # Light horizontal streaks to mimic scanner banding.
    for _ in range(max(8, int(24 * profile.noise_scale))):
        y = rng.uniform(30, height - 30)
        h = rng.uniform(0.6, 2.0)
        g = rng.uniform(0.88, 0.96)
        c.setFillColorRGB(g, g, g)
        c.rect(0, y, width, h, fill=1, stroke=0)

    # Vertical banding is common in low-quality scans.
    for _ in range(max(2, int(6 * profile.artifact_scale))):
        x = rng.uniform(20, width - 20)
        w = rng.uniform(0.8, 2.2)
        g = rng.uniform(0.90, 0.97)
        c.setFillColorRGB(g, g, g)
        c.rect(x, 0, w, height, fill=1, stroke=0)

    # Small speckle noise.
    c.setFillColorRGB(0.75, 0.75, 0.75)
    for _ in range(max(35, int(110 * profile.noise_scale))):
        x = rng.uniform(10, width - 10)
        y = rng.uniform(10, height - 10)
        r = rng.uniform(0.2, 0.8)
        c.circle(x, y, r, fill=1, stroke=0)

    # Mild fold/crease artifacts.
    for _ in range(rng.randint(1, max(1, int(2 * profile.artifact_scale)))):
        y = rng.uniform(90, height - 90)
        c.setStrokeColorRGB(0.80, 0.80, 0.78)
        c.setLineWidth(rng.uniform(0.5, 1.1))
        c.line(28, y, width - 28, y + rng.uniform(-2.5, 2.5))

    # Edge shading from scanner lid / paper curvature.
    c.setFillColorRGB(0.86, 0.86, 0.84)
    c.rect(0, 0, 9, height, fill=1, stroke=0)
    c.rect(width - 9, 0, 9, height, fill=1, stroke=0)
    c.setFillColorRGB(0.88, 0.88, 0.86)
    c.rect(0, height - 8, width, 8, fill=1, stroke=0)


def draw_punch_holes(c: canvas.Canvas, width: float, height: float, rng: random.Random, profile: RenderProfile) -> None:
    if rng.random() > profile.punch_hole_prob:
        return
    x = 16
    for frac in (0.22, 0.50, 0.78):
        y = height * frac + rng.uniform(-6, 6)
        c.setFillColorRGB(0.80, 0.80, 0.78)
        c.circle(x, y, 5.2, fill=1, stroke=0)
        c.setFillColorRGB(0.90, 0.90, 0.88)
        c.circle(x + 0.8, y + 0.5, 3.7, fill=1, stroke=0)


def draw_barcode(c: canvas.Canvas, x: float, y: float, width: float, height: float, seed: int) -> None:
    rng = random.Random(seed)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    xpos = x
    while xpos < x + width:
        bar_w = rng.choice([0.45, 0.7, 1.1, 1.6])
        gap = rng.choice([0.3, 0.45, 0.7])
        if rng.random() < 0.78:
            c.rect(xpos, y, bar_w, height, fill=1, stroke=0)
        xpos += bar_w + gap


def draw_hand_signature(c: canvas.Canvas, x: float, y: float, seed: int) -> None:
    rng = random.Random(seed)
    c.saveState()
    c.setStrokeColorRGB(0.12, 0.14, 0.18)
    c.setLineWidth(1.2)
    c.translate(x, y)
    c.rotate(rng.uniform(-8, 8))
    path = c.beginPath()
    path.moveTo(0, 0)
    cursor_x = 0.0
    for _ in range(14):
        cursor_x += rng.uniform(6, 10)
        path.curveTo(
            cursor_x - rng.uniform(4, 7), rng.uniform(-5, 7),
            cursor_x - rng.uniform(1, 3), rng.uniform(-6, 9),
            cursor_x, rng.uniform(-3, 6),
        )
    c.drawPath(path, stroke=1, fill=0)
    c.restoreState()


def draw_scan_stamp(c: canvas.Canvas, width: float, height: float, doc_type: str, rng: random.Random, profile: RenderProfile) -> None:
    if rng.random() > profile.stamp_prob:
        return
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


def draw_round_seal(c: canvas.Canvas, width: float, height: float, rng: random.Random, profile: RenderProfile) -> None:
    if rng.random() > profile.seal_prob:
        return
    c.saveState()
    cx = width - 105 + rng.uniform(-10, 10)
    cy = 86 + rng.uniform(-8, 8)
    c.translate(cx, cy)
    c.rotate(rng.uniform(-18, 18))
    c.setStrokeColorRGB(0.62, 0.22, 0.22)
    c.setLineWidth(1.1)
    c.circle(0, 0, 34, fill=0, stroke=1)
    c.circle(0, 0, 28, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColorRGB(0.62, 0.22, 0.22)
    c.drawCentredString(0, -2, "UFFICIO ATTI")
    c.restoreState()


def render_scan_document(
    c: canvas.Canvas,
    width: float,
    height: float,
    title: str,
    idx: int,
    doc: dict[str, Any],
    style_seed: int,
    profile: RenderProfile,
) -> None:
    seed_material = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    base_seed = int.from_bytes(seed_material.encode("utf-8", errors="ignore")[:8] or b"0", "little", signed=False)
    local_seed = (base_seed ^ style_seed ^ (idx * 7919)) & 0xFFFFFFFF
    rng = random.Random(local_seed)

    draw_scan_background(c, width, height, rng, profile)
    draw_punch_holes(c, width, height, rng, profile)

    left = 46
    right = width - 46
    top = height - 42
    line_height = 14
    y = top

    # Light watermark often visible in scanned office copies.
    if rng.random() < profile.watermark_prob:
        c.saveState()
        w = rng.uniform(0.82, 0.90)
        c.setFillColorRGB(w, w, w - 0.01)
        c.setFont("Helvetica-Bold", rng.uniform(28, 38))
        c.translate(width * rng.uniform(0.45, 0.58), height * rng.uniform(0.46, 0.58))
        c.rotate(rng.uniform(24, 40))
        c.drawCentredString(0, 0, "COPIA SCANSITA")
        c.restoreState()

    c.setStrokeColorRGB(0.4, 0.4, 0.4)
    c.setLineWidth(0.6)
    c.rect(28, 28, width - 56, height - 56, fill=0, stroke=1)

    header_font = rng.choice(["Helvetica-Bold", "Times-Bold", "Courier-Bold"])
    body_font = rng.choice(["Times-Roman", "Helvetica", "Courier"])

    c.setFont(header_font, 12)
    c.setFillColorRGB(0.12, 0.12, 0.12)
    c.drawString(left, y, f"FASCICOLO: {title}  |  DOC {idx:02d}  |  {doc['document_type'].upper()}")
    y -= 22

    c.setFont("Courier", 9)
    c.drawString(left, y, f"Protocollo interno n. {rng.randint(10000, 99999)} / {rng.choice([2023, 2024, 2025])}")
    c.drawRightString(right, y, f"Pag. {idx:02d}")
    y -= 16

    c.setStrokeColorRGB(0.52, 0.52, 0.52)
    c.setLineWidth(0.4)
    c.line(left, y + 3, right, y + 3)
    y -= 8

    lines = format_document_content(doc, rng)
    body_font_size = 10.5
    text_width = right - left - 6
    c.setFont(body_font, body_font_size)
    for line in lines:
        wrapped = simpleSplit(line, body_font, body_font_size, text_width) or [""]
        for piece in wrapped:
            if y < 54:
                c.setFont("Helvetica-Oblique", 8)
                c.drawString(left, 36, "continua nella pagina successiva")
                c.showPage()
                draw_scan_background(c, width, height, rng, profile)
                draw_punch_holes(c, width, height, rng, profile)
                y = top
                c.setFont(body_font, body_font_size)

            jitter_x = rng.uniform(-1.8, 1.8) * profile.jitter_scale
            jitter_y = rng.uniform(-0.8, 0.8) * profile.jitter_scale
            c.drawString(left + jitter_x, y + jitter_y, piece)
            y -= line_height

    # Signature line on procura originals when signature is expected.
    if doc.get("document_type") == "Procura":
        soggetti = doc.get("schema", {}).get("soggetto", [])
        if soggetti and soggetti[0].get("firma_presente") == "OK":
            sign_y = max(72, y - 10)
            c.setStrokeColorRGB(0.35, 0.35, 0.35)
            c.setLineWidth(0.5)
            c.line(left + 240, sign_y, right - 18, sign_y)
            draw_hand_signature(c, left + 248, sign_y + 7, local_seed + 77)

    draw_round_seal(c, width, height, rng, profile)

    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.18, 0.18, 0.18)
    c.drawString(left, 36, f"Pagina scansita - riferimento documento {idx:02d}")
    c.drawRightString(right, 36, f"hash {rng.randint(100000, 999999)}")
    draw_barcode(c, right - 120, 20, 110, 10, local_seed + 19)

    draw_scan_stamp(c, width, height, doc["document_type"], rng, profile)


def render_pdf(
    output_path: Path,
    title: str,
    docs: list[dict[str, Any]],
    style_seed: int,
    profile: RenderProfile,
) -> None:
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    # Rule: each logical document starts on a new page.
    for i, doc in enumerate(docs, start=1):
        if i > 1:
            c.showPage()
        render_scan_document(c, width, height, title, i, doc, style_seed=style_seed, profile=profile)

    c.save()


def chunk_documents(docs: list[dict[str, Any]], single_pdf: bool, max_docs_per_pdf: int) -> list[list[dict[str, Any]]]:
    # Hard cap requested: each generated PDF must not exceed 45 pages.
    max_docs_per_pdf = min(max_docs_per_pdf, 45)

    if single_pdf and len(docs) <= max_docs_per_pdf:
        return [docs]

    accessory_types = {"Apostille", "Traduzione", "Asseverazione"}

    # Build atomic blocks so primary documents and their contiguous accessories
    # are always kept together when creating PDF bundles.
    blocks: list[list[dict[str, Any]]] = []
    current_block: list[dict[str, Any]] = []
    for doc in docs:
        dt = doc.get("document_type")
        if dt in accessory_types:
            if not current_block:
                current_block = [doc]
            else:
                current_block.append(doc)
            continue

        if current_block:
            blocks.append(current_block)
        current_block = [doc]

    if current_block:
        blocks.append(current_block)

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for block in blocks:
        # If block would overflow current chunk, close current chunk first.
        # Never split blocks across PDFs.
        if current and len(current) + len(block) > max_docs_per_pdf:
            chunks.append(current)
            current = []

        current.extend(block)

        # If a single block is larger than max_docs_per_pdf, keep it intact
        # in its own chunk instead of splitting it.
        if len(current) >= max_docs_per_pdf:
            chunks.append(current)
            current = []

    if current:
        chunks.append(current)
    return chunks


def add_supporting_docs(rng: random.Random, docs: list[dict[str, Any]], scenario: ScenarioConfig) -> None:
    """Add supporting documents (Apostille, Traduzione, Asseverazione) as grouped chains.
    
    Each primary document stays with its accessory documents in a group,
    preserving document order while keeping chains together.
    """
    # Build a map of which documents get which accessories
    doc_accessories: dict[int, list[dict[str, Any]]] = {}

    for doc_idx, doc in enumerate(list(docs)):
        dt = doc["document_type"]
        accessories: list[dict[str, Any]] = []

        if dt == "Procura":
            subject = doc["schema"]["soggetto"][0]
            if doc["schema"]["rilasciata_in_italia"] == "NO":
                accessories.append(make_apostille("Procura", subject))
            if doc["schema"]["scritta_in_italiano"] == "NO":
                sede = "Estero" if rng.random() < 0.5 else "Italia"
                tr = make_translation("Procura", subject, sede)
                accessories.append(tr)
                if sede == "Estero":
                    accessories.append(make_apostille("Traduzione", subject, original_doc="Procura"))
                else:
                    accessories.append(make_asseverazione("Traduzione", subject, original_doc="Procura"))

        if dt == "Atto di nascita":
            subject = doc["schema"]["soggetto"]
            if doc["schema"]["stato"] != "Italia":
                accessories.append(make_apostille("Atto di nascita", subject))
                sede = "Estero" if rng.random() < 0.5 else "Italia"
                tr = make_translation("Atto di nascita", subject, sede)
                accessories.append(tr)
                if sede == "Estero":
                    accessories.append(make_apostille("Traduzione", subject, original_doc="Atto di nascita"))
                else:
                    accessories.append(make_asseverazione("Traduzione", subject, original_doc="Atto di nascita"))

        if dt == "Atto di morte":
            subject = doc["schema"]["soggetto"]
            accessories.append(make_apostille("Atto di morte", subject))
            tr = make_translation("Atto di morte", subject, "Estero")
            accessories.append(tr)
            accessories.append(make_apostille("Traduzione", subject, original_doc="Atto di morte"))

        if dt == "Certificato Negativo di Naturalizzazione":
            subject = doc["schema"]["soggetto"]
            accessories.append(make_apostille("Certificato Negativo di Naturalizzazione", subject))
            sede = "Estero" if rng.random() < 0.5 else "Italia"
            tr = make_translation("Certificato Negativo di Naturalizzazione", subject, sede)
            accessories.append(tr)
            if sede == "Estero":
                accessories.append(make_apostille("Traduzione", subject, original_doc="Certificato Negativo di Naturalizzazione"))
            else:
                accessories.append(make_asseverazione("Traduzione", subject, original_doc="Certificato Negativo di Naturalizzazione"))

        if accessories:
            doc_accessories[doc_idx] = accessories
    
    # Reconstruct docs with accessories inserted right after their primary documents
    result = []
    for doc_idx, doc in enumerate(list(docs)):
        result.append(doc)
        if doc_idx in doc_accessories:
            result.extend(doc_accessories[doc_idx])
    
    # Replace docs list in place
    docs.clear()
    docs.extend(result)


def build_case_documents(rng: random.Random, scenario: ScenarioConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    family = build_family(rng, descendants=rng.randint(2, 5))

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

    avo_father = random_person(rng, gender="M")
    avo_mother = random_person(rng, gender="F")
    avo_birth = make_birth(rng, avo, avo_father, avo_mother, italy=True)
    if scenario.death_required:
        avo_birth["schema"]["data_nascita"] = random_date(rng, 1840, 1860)
        avo_birth["schema"]["area_nascita"] = "A"

    docs.append(avo_birth)

    for i, person in enumerate(lineage[1:], start=1):
        prev = lineage[i - 1]
        prev_gender = prev.get("gender")
        if prev_gender == "M":
            father = {"nome": prev.get("nome", ""), "cognome": prev.get("cognome", "")}
            mother = random_person(rng, gender="F")
        else:
            father = random_person(rng, gender="M")
            mother = {"nome": prev.get("nome", ""), "cognome": prev.get("cognome", "")}
        docs.append(make_birth(rng, person, father, mother, italy=False))

    if scenario.include_avo_death:
        docs.append(make_avo_death(rng, avo))

    cnn = make_cnn(rng, avo, avo_birth["schema"]["data_nascita"])
    docs.append(cnn)
    _append_declared_aliases_to_ricorso(ricorso, cnn.get("schema", {}).get("pseudonimi", []))

    add_supporting_docs(rng, docs, scenario)
    apply_challenging_variants(rng, scenario, docs, family, ricorso)

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

    # Shuffle only useless docs at the end; keep chains together
    # Identify documents that are part of chains and which are standalone
    document_types_with_chains = {"Procura", "Atto di nascita", "Atto di morte", "Certificato Negativo di Naturalizzazione"}
    useless_docs = [d for d in docs if d["document_type"] not in document_types_with_chains and 
                    not is_expected_supported_document(d)]
    
    # Shuffle only the useless/noise documents; keep primary+accessory chains in their natural order
    rng.shuffle(useless_docs)
    
    # Reconstruct docs with shuffled useless docs
    structured_docs = [d for d in docs if d["document_type"] in document_types_with_chains or 
                       is_expected_supported_document(d)]
    structured_docs.extend(useless_docs)
    
    return structured_docs, expected_extraction


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
            inject_lineage_incoherence=False,
            inject_marriage_claimants=False,
            inject_procura_weakness=False,
            drop_one_descendant_birth=False,
            selection_weight=1.35,
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
            inject_lineage_incoherence=False,
            inject_marriage_claimants=False,
            inject_procura_weakness=True,
            drop_one_descendant_birth=False,
            selection_weight=1.15,
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
            inject_lineage_incoherence=True,
            inject_marriage_claimants=False,
            inject_procura_weakness=False,
            drop_one_descendant_birth=True,
            selection_weight=1.00,
        ),
        ScenarioConfig(
            include_indice=True,
            include_avo_death=True,
            death_required=True,
            include_useless_docs=True,
            include_useless_apostilles=True,
            include_irrelevant_cert_chains=True,
            descendants_with_married_name=True,
            all_docs_in_single_pdf=False,
            max_docs_per_pdf=6,
            inject_lineage_incoherence=True,
            inject_marriage_claimants=True,
            inject_procura_weakness=True,
            drop_one_descendant_birth=False,
            selection_weight=0.85,
        ),
        ScenarioConfig(
            include_indice=True,
            include_avo_death=False,
            death_required=False,
            include_useless_docs=True,
            include_useless_apostilles=True,
            include_irrelevant_cert_chains=True,
            descendants_with_married_name=False,
            all_docs_in_single_pdf=False,
            max_docs_per_pdf=7,
            inject_lineage_incoherence=False,
            inject_marriage_claimants=True,
            inject_procura_weakness=True,
            drop_one_descendant_birth=True,
            selection_weight=0.80,
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
        scenario = rng.choices(scenarios, weights=[s.selection_weight for s in scenarios], k=1)[0]
        render_profile = random_render_profile(rng)
        style_seed = rng.randint(0, 2**31 - 1)
        case_name = f"fascicolo_sintetico_{i:03d}"
        case_pdf_dir = fascicoli_root / case_name
        case_support_dir = support_root / case_name
        case_pdf_dir.mkdir(parents=True, exist_ok=True)
        case_support_dir.mkdir(parents=True, exist_ok=True)

        # Remove stale generated bundles from previous runs so extraction does
        # not mix old and new scenarios within the same case folder.
        for stale_pdf in case_pdf_dir.glob(f"{case_name}_bundle_*.pdf"):
            stale_pdf.unlink()

        mixed_docs, expected = build_case_documents(rng, scenario)

        chunks = chunk_documents(mixed_docs, scenario.all_docs_in_single_pdf, scenario.max_docs_per_pdf)

        pdf_files = []
        for j, chunk in enumerate(chunks, start=1):
            pdf_name = f"{case_name}_bundle_{j:02d}.pdf"
            pdf_path = case_pdf_dir / pdf_name
            render_pdf(pdf_path, title=case_name, docs=chunk, style_seed=style_seed + j, profile=render_profile)
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
                "inject_lineage_incoherence": scenario.inject_lineage_incoherence,
                "inject_marriage_claimants": scenario.inject_marriage_claimants,
                "inject_procura_weakness": scenario.inject_procura_weakness,
                "drop_one_descendant_birth": scenario.drop_one_descendant_birth,
                "selection_weight": scenario.selection_weight,
            },
            "render_profile": {
                "noise_scale": round(render_profile.noise_scale, 3),
                "artifact_scale": round(render_profile.artifact_scale, 3),
                "jitter_scale": round(render_profile.jitter_scale, 3),
                "watermark_prob": round(render_profile.watermark_prob, 3),
                "punch_hole_prob": round(render_profile.punch_hole_prob, 3),
                "stamp_prob": round(render_profile.stamp_prob, 3),
                "seal_prob": round(render_profile.seal_prob, 3),
                "style_seed": style_seed,
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
