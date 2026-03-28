#!/usr/bin/env python3
"""Evaluate pipeline outputs against synthetic ground truth.

For each case compares:
  - fascicoli/<case>/info.txt        vs  support/<case>/expected_extraction.json
  - fascicoli/<case>/controlli.txt   vs  support/<case>/expected_report.json

Usage:
  python3 evaluate_results.py
  python3 evaluate_results.py --base-dir res/synthetic_fascicoli
  python3 evaluate_results.py --case fascicolo_sintetico_000 fascicolo_sintetico_001
    python3 evaluate_results.py --report-only
    python3 evaluate_results.py --report-from-info
    python3 evaluate_results.py --missing-files-report
  python3 evaluate_results.py --json
"""

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Optional

from src.analysis import DocumentValidator


_DOC_MATCH_VALIDATOR = DocumentValidator([])


# ---------------------------------------------------------------------------
# Levenshtein distance (used for fuzzy name matching in document/section keys)
# ---------------------------------------------------------------------------

def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            dp[j] = prev[j - 1] if a[i - 1] == b[j - 1] else 1 + min(prev[j], dp[j - 1], prev[j - 1])
    return dp[n]


def _fuzzy_eq(a: str, b: str, threshold: float = 0.25) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    if a == b:
        return True
    dist = _edit_distance(a, b)
    return dist / max(len(a), len(b), 1) <= threshold


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r'(\d{2})[-./](\d{2})[-./](\d{4})')


def _norm(v) -> str:
    """Normalise a leaf value to an uppercase canonical string."""
    if v is None:
        return "NULL"
    s = str(v).strip().upper()
    # Unify date separators to dot  (DD-MM-YYYY → DD.MM.YYYY)
    s = _DATE_RE.sub(r'\1.\2.\3', s)
    return s


# ---------------------------------------------------------------------------
# Fields to skip during comparison
# ---------------------------------------------------------------------------

# Extraction schema fields that are pipeline-specific or free-text
_SKIP_SCHEMA_FIELDS = {
    "source_pages",
    "racconto_linea_discendenza",
    "riassunto_linea_discendenza",
    # Procura section D is a verbatim copy of foreign text — skip
    "oggetto",
}

# Report fields that contain a "OK/KO; <narrative>" value.
# We only compare the prefix token.
_NARRATIVE_PREFIX_RE = re.compile(r'^(OK|KO|SI|NO|NULL)\s*;', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Document matching helpers
# ---------------------------------------------------------------------------

def _person_key(person: dict) -> str:
    """Lower-case 'cognome nome' for a person dict."""
    if not isinstance(person, dict):
        return ""
    return f"{(person.get('cognome') or '').strip().lower()} {(person.get('nome') or '').strip().lower()}".strip()


def _doc_match_key(doc: dict) -> tuple:
    """Return a tuple used as the primary matching key for a document."""
    dt = doc.get("document_type", "")
    schema = doc.get("schema", {})

    # Singleton documents — unique per case
    if dt in ("IndiceProcedimento.html", "Ricorso"):
        return (dt,)

    soggetto = schema.get("soggetto")
    if isinstance(soggetto, dict):
        return (dt, _person_key(soggetto))
    if isinstance(soggetto, list) and soggetto:
        return (dt, _person_key(soggetto[0]))

    # Apostille / Traduzione / Asseverazione — keyed by what they certify
    oggetto = schema.get("oggetto")
    if isinstance(oggetto, dict):
        obj_type = oggetto.get("document_type", "")
        obj_sogg = oggetto.get("soggetto") or []
        obj_key = _person_key(obj_sogg[0]) if obj_sogg else ""
        return (dt, obj_type, obj_key)

    return (dt, "")


def _key_str(key: tuple) -> str:
    return " | ".join(str(x) for x in key[1:] if x)


def _people_match(person_a: dict | None, person_b: dict | None) -> bool:
    if not isinstance(person_a, dict) or not isinstance(person_b, dict):
        return False
    return _DOC_MATCH_VALIDATOR.people_match(person_a, person_b)


def _doc_primary_person(doc: dict) -> dict:
    schema = doc.get("schema", {})
    soggetto = schema.get("soggetto")
    if isinstance(soggetto, dict):
        return soggetto
    if isinstance(soggetto, list) and soggetto:
        first = soggetto[0]
        return first if isinstance(first, dict) else {}

    oggetto = schema.get("oggetto")
    if isinstance(oggetto, dict):
        obj_sogg = oggetto.get("soggetto") or []
        if obj_sogg and isinstance(obj_sogg[0], dict):
            return obj_sogg[0]
    return {}


def _docs_semantically_match(expected_doc: dict, actual_doc: dict) -> bool:
    edt = expected_doc.get("document_type", "")
    adt = actual_doc.get("document_type", "")
    if edt != adt:
        return False

    if edt in ("IndiceProcedimento.html", "Ricorso"):
        return True

    eschema = expected_doc.get("schema", {})
    aschema = actual_doc.get("schema", {})

    if edt in {"Atto di nascita", "Atto di morte", "Certificato Negativo di Naturalizzazione", "Procura"}:
        return _people_match(_doc_primary_person(expected_doc), _doc_primary_person(actual_doc))

    if edt in {"Apostille", "Traduzione", "Asseverazione"}:
        eobj = eschema.get("oggetto", {}) if isinstance(eschema.get("oggetto", {}), dict) else {}
        aobj = aschema.get("oggetto", {}) if isinstance(aschema.get("oggetto", {}), dict) else {}
        if eobj.get("document_type") != aobj.get("document_type"):
            return False
        if eobj.get("documento_originale") != aobj.get("documento_originale"):
            return False
        return _people_match(_doc_primary_person(expected_doc), _doc_primary_person(actual_doc))

    return False


def match_documents(expected_docs: list, actual_docs: list):
    """
    Greedily match expected docs to actual docs by primary key with fuzzy fallback.

    Returns:
        matched_pairs : list of (expected_doc, actual_doc)
        missing       : expected docs with no actual counterpart
        extra         : actual docs not matched to any expected doc
    """
    # index actual docs by key
    actual_by_key: dict[tuple, list] = {}
    for doc in actual_docs:
        actual_by_key.setdefault(_doc_match_key(doc), []).append(doc)

    matched = []
    missing = []
    used_ids: set[int] = set()

    for edoc in expected_docs:
        ek = _doc_match_key(edoc)
        candidates = [d for d in actual_by_key.get(ek, []) if id(d) not in used_ids]
        if candidates:
            adoc = candidates[0]
            used_ids.add(id(adoc))
            matched.append((edoc, adoc))
            continue

        # Semantic fallback aligned with DocumentValidator identity matching.
        semantic_candidates = [
            d for d in actual_docs
            if id(d) not in used_ids and _docs_semantically_match(edoc, d)
        ]
        if semantic_candidates:
            adoc = semantic_candidates[0]
            used_ids.add(id(adoc))
            matched.append((edoc, adoc))
            continue

        # Fuzzy fallback: same document_type, closest person key
        edt = edoc.get("document_type", "")
        ek_str = _key_str(ek)
        best: Optional[dict] = None
        best_score = 0.0
        for adoc in actual_docs:
            if id(adoc) in used_ids:
                continue
            if adoc.get("document_type") != edt:
                continue
            ak_str = _key_str(_doc_match_key(adoc))
            if not ek_str and not ak_str:
                score = 1.0
            elif not ek_str or not ak_str:
                score = 0.0
            else:
                dist = _edit_distance(ek_str, ak_str)
                score = 1.0 - dist / max(len(ek_str), len(ak_str))
            if score > best_score:
                best_score = score
                best = adoc

        if best is not None and best_score >= 0.60:
            used_ids.add(id(best))
            matched.append((edoc, best))
        else:
            missing.append(edoc)

    extra = [d for d in actual_docs if id(d) not in used_ids]
    return matched, missing, extra


# ---------------------------------------------------------------------------
# Schema (extraction) comparison
# ---------------------------------------------------------------------------

def compare_schemas(
    expected,
    actual,
    path: str = "",
    skip: set = _SKIP_SCHEMA_FIELDS,
) -> list:
    """
    Recursively compare two schema values.

    Returns list of (field_path, expected_str, actual_str) tuples for mismatches.
    """
    mismatches = []

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            actual = {}
        for key, eval_ in expected.items():
            if key in skip:
                continue
            field_path = f"{path}.{key}" if path else key
            aval = actual.get(key)
            mismatches.extend(compare_schemas(eval_, aval, field_path, skip))

    elif isinstance(expected, list):
        # Compare sorted JSON representations
        ev_str = _norm(json.dumps(sorted(str(x) for x in expected), ensure_ascii=False))
        av_str = (
            _norm(json.dumps(sorted(str(x) for x in actual), ensure_ascii=False))
            if isinstance(actual, list)
            else _norm(json.dumps(actual, ensure_ascii=False))
        )
        if ev_str != av_str:
            mismatches.append((path, json.dumps(expected, ensure_ascii=False), json.dumps(actual, ensure_ascii=False)))

    else:
        ev = _norm(expected)
        av = _norm(actual)
        if ev != av:
            # Allow fuzzy equality for plain name strings (tolerate typos)
            if (
                isinstance(expected, str)
                and re.fullmatch(r"[A-Za-zÀ-ÿ\s\-']+", expected.strip())
                and _fuzzy_eq(ev, av)
            ):
                pass  # considered equal
            else:
                mismatches.append((path, str(expected), str(actual) if actual is not None else "NULL"))

    return mismatches


def compare_extraction(expected_docs: list, actual_docs: list) -> dict:
    """
    Compare full extraction lists.

    Returns a dict with:
      matched_count, missing_docs, extra_docs, doc_mismatches
    """
    matched, missing, extra = match_documents(expected_docs, actual_docs)
    doc_mismatches = []
    for edoc, adoc in matched:
        mm = compare_schemas(edoc.get("schema", {}), adoc.get("schema", {}))
        if mm:
            doc_mismatches.append({
                "document_type": edoc.get("document_type"),
                "key": _key_str(_doc_match_key(edoc)),
                "mismatches": mm,
            })

    return {
        "matched_count": len(matched),
        "missing_docs": [
            {"document_type": d.get("document_type"), "key": _key_str(_doc_match_key(d))}
            for d in missing
        ],
        "extra_docs": [
            {"document_type": d.get("document_type"), "key": _key_str(_doc_match_key(d))}
            for d in extra
        ],
        "doc_mismatches": doc_mismatches,
    }


# ---------------------------------------------------------------------------
# Report (controlli) comparison
# ---------------------------------------------------------------------------

def _flatten_report(report: dict) -> dict:
    """
    Flatten report sections into a dict of {section_key: data}.

    Grouped sections like {"4": {"4/1": {...}, "4/2": {...}}} are unpacked.
    Sections "10" and "11" are excluded (handled separately).
    """
    flat = {}
    for sec_key, sec_val in report.items():
        if sec_key in ("10", "11"):
            continue
        if isinstance(sec_val, dict) and any("/" in str(k) for k in sec_val):
            for sub_key, sub_val in sec_val.items():
                flat[sub_key] = sub_val
        else:
            flat[sec_key] = sec_val
    return flat


def _match_report_sections(expected_flat: dict, actual_flat: dict) -> dict:
    """
    Match expected section keys to actual section keys.

    For numbered sub-sections (e.g. "4/1", "8/2"), match by the "A" field
    (person name) rather than by index.

    Returns {expected_key: (expected_data, actual_data_or_None)}.
    """
    matched = {}
    used: set[str] = set()

    for ekey, edata in expected_flat.items():
        if "/" not in ekey:
            # Direct lookup
            if ekey in actual_flat:
                matched[ekey] = (edata, actual_flat[ekey])
                used.add(ekey)
            else:
                matched[ekey] = (edata, None)
            continue

        # Numbered sub-section — match by person name in field "A"
        sec = ekey.split("/")[0]
        e_person = edata.get("A", "") if isinstance(edata, dict) else ""
        best_key: Optional[str] = None
        best_score = 0.0
        for akey, adata in actual_flat.items():
            if akey in used or "/" not in akey or akey.split("/")[0] != sec:
                continue
            a_person = adata.get("A", "") if isinstance(adata, dict) else ""
            dist = _edit_distance(e_person.lower(), a_person.lower())
            score = 1.0 - dist / max(len(e_person), len(a_person), 1)
            if score > best_score:
                best_score = score
                best_key = akey

        if best_key is not None and best_score >= 0.50:
            matched[ekey] = (edata, actual_flat[best_key])
            used.add(best_key)
        else:
            matched[ekey] = (edata, None)

    return matched


def _compare_report_section(expected_data, actual_data, prefix: str = "") -> list:
    """
    Compare two section dicts; return list of (path, expected_str, actual_str).

    For fields containing "OK/KO/SI/NO; <narrative>", only the prefix token
    is compared (the narrative is LLM-generated and may differ legitimately).
    Field "A" (person name anchor) is always skipped.
    """
    mismatches = []
    if not isinstance(expected_data, dict):
        ev = _norm(expected_data)
        av = _norm(actual_data)
        if ev != av and not _fuzzy_eq(ev, av):
            mismatches.append((prefix, str(expected_data), str(actual_data) if actual_data is not None else "NULL"))
        return mismatches

    if not isinstance(actual_data, dict):
        actual_data = {}

    for field, eval_ in expected_data.items():
        if field == "A":
            continue  # used for section matching, not field comparison
        field_path = f"{prefix}.{field}" if prefix else field
        aval = actual_data.get(field)

        if isinstance(eval_, str) and _NARRATIVE_PREFIX_RE.match(eval_):
            # Compare only the prefix token (OK/KO/SI/NO)
            ev_token = eval_.split(";")[0].strip().upper()
            av_token = (str(aval).split(";")[0].strip().upper()) if aval is not None else "NULL"
            if ev_token != av_token:
                mismatches.append((field_path, ev_token, av_token))
            continue

        if isinstance(eval_, dict):
            mismatches.extend(_compare_report_section(eval_, aval or {}, field_path))
        elif isinstance(eval_, list):
            ev_str = _norm(json.dumps(sorted(str(x) for x in eval_), ensure_ascii=False))
            av_str = _norm(json.dumps(sorted(str(x) for x in (aval or [])), ensure_ascii=False))
            if ev_str != av_str:
                mismatches.append((field_path, json.dumps(eval_), json.dumps(aval)))
        else:
            ev = _norm(eval_)
            av = _norm(aval)
            if ev != av:
                # Tolerate fuzzy name strings
                if (
                    isinstance(eval_, str)
                    and re.fullmatch(r"[A-Za-zÀ-ÿ\s\-',.:]+", eval_.strip())
                    and _fuzzy_eq(ev, av)
                ):
                    pass
                else:
                    mismatches.append((field_path, str(eval_), str(aval) if aval is not None else "NULL"))

    return mismatches


def compare_report(expected_report: dict, actual_report: dict) -> dict:
    """
    Compare two DocumentValidator.run() outputs.

    Returns:
        section_mismatches  : list of {section, mismatches[(path,ev,av)]}
        missing_sections    : sections in expected but absent in actual
        missing_ko_keys     : KO keys in expected["10"] but absent in actual["10"]
        extra_ko_keys       : KO keys in actual["10"] but absent in expected["10"]
    """
    e_flat = _flatten_report(expected_report)
    a_flat = _flatten_report(actual_report)

    section_map = _match_report_sections(e_flat, a_flat)

    section_mismatches = []
    missing_sections = []

    for sec_key, (edata, adata) in section_map.items():
        if adata is None:
            missing_sections.append(sec_key)
            continue
        mm = _compare_report_section(edata, adata, sec_key)
        if mm:
            section_mismatches.append({
                "section": sec_key,
                "mismatches": mm,
            })

    # Section "10": KO key sets
    e_ko = set(expected_report.get("10") or [])
    a_ko = set(actual_report.get("10") or [])
    missing_ko = sorted(e_ko - a_ko)
    extra_ko = sorted(a_ko - e_ko)

    return {
        "section_mismatches": section_mismatches,
        "missing_sections": missing_sections,
        "missing_ko_keys": missing_ko,
        "extra_ko_keys": extra_ko,
    }


def compare_report_warnings_only(expected_report: dict, actual_report: dict) -> dict:
    """Compare only section 11 warnings (keys + messages)."""
    e_warn = expected_report.get("11") or {}
    a_warn = actual_report.get("11") or {}

    if not isinstance(e_warn, dict):
        e_warn = {}
    if not isinstance(a_warn, dict):
        a_warn = {}

    mismatches = []
    all_keys = sorted(set(e_warn.keys()) | set(a_warn.keys()))
    for key in all_keys:
        ev = e_warn.get(key)
        av = a_warn.get(key)
        if _norm(ev) != _norm(av):
            mismatches.append((f"11.{key}", str(ev) if ev is not None else "NULL", str(av) if av is not None else "NULL"))

    section_mismatches = []
    if mismatches:
        section_mismatches.append({
            "section": "11",
            "mismatches": mismatches,
        })

    return {
        "section_mismatches": section_mismatches,
        "missing_sections": [],
        "missing_ko_keys": [],
        "extra_ko_keys": [],
    }


# ---------------------------------------------------------------------------
# Per-case evaluation
# ---------------------------------------------------------------------------

def evaluate_case(
    fascicoli_dir: Path,
    support_dir: Path,
    report_from_info: bool = False,
    report_only: bool = False,
) -> dict:
    """Load files and run both comparisons for one case."""
    result: dict = {"extraction": None, "report": None, "errors": []}

    info_path = fascicoli_dir / "info.txt"
    controlli_path = fascicoli_dir / "controlli.txt"
    expected_ext_path = support_dir / "expected_extraction.json"
    expected_rep_path = support_dir / "expected_report.json"
    actual_docs = None

    # --- Extraction ---
    if not report_only:
        if not info_path.exists():
            result["errors"].append(f"info.txt not found: {info_path}")
        if not expected_ext_path.exists():
            result["errors"].append(f"expected_extraction.json not found: {expected_ext_path}")
        if info_path.exists() and expected_ext_path.exists():
            try:
                actual_docs = json.loads(info_path.read_text(encoding="utf-8"))
                expected_docs = json.loads(expected_ext_path.read_text(encoding="utf-8"))
                result["extraction"] = compare_extraction(expected_docs, actual_docs)
            except Exception as exc:
                result["errors"].append(f"Extraction comparison failed: {exc}")

    # --- Report ---
    if not expected_rep_path.exists():
        result["errors"].append(f"expected_report.json not found: {expected_rep_path}")
    if not report_from_info and not controlli_path.exists():
        result["errors"].append(f"controlli.txt not found: {controlli_path}")

    if expected_rep_path.exists() and (report_from_info or controlli_path.exists()):
        try:
            if report_from_info:
                if actual_docs is None:
                    actual_docs = json.loads(info_path.read_text(encoding="utf-8"))
                actual_report = DocumentValidator(actual_docs).run()
            else:
                actual_report = json.loads(controlli_path.read_text(encoding="utf-8"))
            expected_report = json.loads(expected_rep_path.read_text(encoding="utf-8"))
            if report_only:
                result["report"] = compare_report_warnings_only(expected_report, actual_report)
            else:
                result["report"] = compare_report(expected_report, actual_report)
        except Exception as exc:
            result["errors"].append(f"Report comparison failed: {exc}")

    return result


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _ext_score(ext: Optional[dict]) -> Optional[dict]:
    if ext is None:
        return None
    return {
        "matched_docs": ext["matched_count"],
        "missing_docs": len(ext["missing_docs"]),
        "extra_docs": len(ext["extra_docs"]),
        "field_mismatches": sum(len(d["mismatches"]) for d in ext["doc_mismatches"]),
    }


def _rep_score(rep: Optional[dict]) -> Optional[dict]:
    if rep is None:
        return None
    return {
        "section_mismatches": sum(len(s["mismatches"]) for s in rep["section_mismatches"]),
        "missing_sections": len(rep["missing_sections"]),
        "missing_ko_keys": len(rep["missing_ko_keys"]),
        "extra_ko_keys": len(rep["extra_ko_keys"]),
    }


def _is_pass(ext_sc: Optional[dict], rep_sc: Optional[dict]) -> bool:
    if ext_sc is None or rep_sc is None:
        return False
    return (
        ext_sc["field_mismatches"] == 0
        and ext_sc["missing_docs"] == 0
        and ext_sc["extra_docs"] == 0
        and rep_sc["section_mismatches"] == 0
        and rep_sc["missing_sections"] == 0
        and rep_sc["missing_ko_keys"] == 0
        and rep_sc["extra_ko_keys"] == 0
    )


def _is_pass_report_only(rep_sc: Optional[dict]) -> bool:
    if rep_sc is None:
        return False
    return (
        rep_sc["section_mismatches"] == 0
        and rep_sc["missing_sections"] == 0
        and rep_sc["missing_ko_keys"] == 0
        and rep_sc["extra_ko_keys"] == 0
    )


# ---------------------------------------------------------------------------
# Human-readable output
# ---------------------------------------------------------------------------

def _print_case(case_name: str, result: dict, report_only: bool = False) -> bool:
    ext = result["extraction"]
    rep = result["report"]
    errors = result["errors"]
    es = _ext_score(ext)
    rs = _rep_score(rep)
    passed = not errors and (_is_pass_report_only(rs) if report_only else _is_pass(es, rs))
    status = "PASS" if passed else "FAIL"

    print(f"\n{'─' * 62}")
    print(f"  {case_name}  [{status}]")
    print(f"{'─' * 62}")

    if errors:
        print("  Errors:")
        for e in errors:
            print(f"    • {e}")

    if es is not None and not report_only:
        ext_ok = es["field_mismatches"] == 0 and es["missing_docs"] == 0 and es["extra_docs"] == 0
        print(f"\n  Extraction [{' OK ' if ext_ok else 'FAIL'}]  "
              f"(matched={es['matched_docs']}, missing={es['missing_docs']}, "
              f"extra={es['extra_docs']}, field_mismatches={es['field_mismatches']})")
        if ext and ext["missing_docs"]:
            for d in ext["missing_docs"]:
                print(f"    - MISSING  {d['document_type']}  {d['key']}")
        if ext and ext["extra_docs"]:
            for d in ext["extra_docs"]:
                print(f"    - EXTRA    {d['document_type']}  {d['key']}")
        if ext and ext["doc_mismatches"]:
            for dm in ext["doc_mismatches"]:
                print(f"    ~ {dm['document_type']}  {dm.get('key', '')}")
                for path, ev, av in dm["mismatches"]:
                    print(f"        [{path}]  expected={ev!r}  actual={av!r}")

    if rs is not None:
        rep_ok = (
            rs["section_mismatches"] == 0
            and rs["missing_sections"] == 0
            and rs["missing_ko_keys"] == 0
            and rs["extra_ko_keys"] == 0
        )
        print(f"\n  Report    [{' OK ' if rep_ok else 'FAIL'}]  "
              f"(section_mismatches={rs['section_mismatches']}, "
              f"missing_sections={rs['missing_sections']}, "
              f"missing_ko={rs['missing_ko_keys']}, extra_ko={rs['extra_ko_keys']})")
        if rep and rep["missing_sections"]:
            print(f"    - MISSING SECTIONS: {', '.join(rep['missing_sections'])}")
        if rep and rep["section_mismatches"]:
            for sm in rep["section_mismatches"]:
                print(f"    ~ Section {sm['section']}:")
                for path, ev, av in sm["mismatches"]:
                    print(f"        [{path}]  expected={ev!r}  actual={av!r}")
        if rep and rep["missing_ko_keys"]:
            print(f"    - MISSING KO KEYS: {', '.join(rep['missing_ko_keys'])}")
        if rep and rep["extra_ko_keys"]:
            print(f"    - EXTRA   KO KEYS: {', '.join(rep['extra_ko_keys'])}")

    return passed


def _build_missing_files_summary(all_results: dict) -> dict:
    """Aggregate missing/extra extracted documents across all evaluated cases."""
    missing_by_type = collections.Counter()
    extra_by_type = collections.Counter()
    missing_by_case = {}

    for case_name, result in all_results.items():
        ext = result.get("extraction")
        if not ext:
            continue

        missing_docs = ext.get("missing_docs", [])
        extra_docs = ext.get("extra_docs", [])

        if missing_docs:
            missing_by_case[case_name] = [
                {
                    "document_type": d.get("document_type"),
                    "key": d.get("key", ""),
                }
                for d in missing_docs
            ]

        for d in missing_docs:
            missing_by_type[d.get("document_type") or "UNKNOWN"] += 1
        for d in extra_docs:
            extra_by_type[d.get("document_type") or "UNKNOWN"] += 1

    return {
        "missing_by_type": dict(missing_by_type.most_common()),
        "extra_by_type": dict(extra_by_type.most_common()),
        "missing_by_case": missing_by_case,
    }


def _print_missing_files_summary(all_results: dict):
    """Human-readable summary focused on extracted missing files from info.txt."""
    summary = _build_missing_files_summary(all_results)
    missing_by_type = summary["missing_by_type"]
    extra_by_type = summary["extra_by_type"]
    missing_by_case = summary["missing_by_case"]

    print(f"\n{'═' * 62}")
    print("  Missing Files Report (from info extraction)")
    print(f"{'═' * 62}")

    if not missing_by_case:
        print("  No missing extracted documents detected.")
    else:
        print("  Missing by document type:")
        for doc_type, count in missing_by_type.items():
            print(f"    - {doc_type}: {count}")

        if extra_by_type:
            print("\n  Extra by document type:")
            for doc_type, count in extra_by_type.items():
                print(f"    - {doc_type}: {count}")

        print("\n  Missing details per case:")
        for case_name in sorted(missing_by_case):
            docs = missing_by_case[case_name]
            print(f"    - {case_name}: {len(docs)} missing")
            for d in docs:
                key = d["key"]
                suffix = f" | {key}" if key else ""
                print(f"        * {d['document_type']}{suffix}")

    print(f"{'═' * 62}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _discover_cases(base_dir: Path) -> list[str]:
    fascicoli_root = base_dir / "fascicoli"
    if not fascicoli_root.is_dir():
        return []
    return sorted(p.name for p in fascicoli_root.iterdir() if p.is_dir())


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate pipeline outputs (info.txt, controlli.txt) against synthetic ground truth."
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("res") / "synthetic_fascicoli",
        help="Root directory containing fascicoli/ and support/ sub-directories.",
    )
    parser.add_argument(
        "--case",
        nargs="+",
        metavar="CASE",
        help="One or more case names to evaluate (default: all cases found).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--report-from-info",
        action="store_true",
        help="Generate actual report from info.txt using DocumentValidator instead of reading controlli.txt.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only compare expected_report.json against actual report (skip extraction/info.txt comparison).",
    )
    parser.add_argument(
        "--missing-files-report",
        action="store_true",
        help="Print an extraction-focused report of missing/extra document files inferred from info.txt vs expected extraction.",
    )
    args = parser.parse_args(argv)

    base_dir: Path = args.base_dir
    cases = args.case or _discover_cases(base_dir)

    if not cases:
        print(f"No cases found in {base_dir / 'fascicoli'}", file=sys.stderr)
        sys.exit(1)

    all_results = {}
    for case_name in cases:
        fascicoli_dir = base_dir / "fascicoli" / case_name
        support_dir = base_dir / "support" / case_name
        all_results[case_name] = evaluate_case(
            fascicoli_dir,
            support_dir,
            report_from_info=args.report_from_info,
            report_only=args.report_only,
        )

    if args.json:
        # Produce JSON with full detail
        missing_summary = _build_missing_files_summary(all_results)
        output = {
            case: {
                "pass": (
                    not r["errors"]
                    and (
                        _is_pass_report_only(_rep_score(r["report"]))
                        if args.report_only
                        else _is_pass(_ext_score(r["extraction"]), _rep_score(r["report"]))
                    )
                ),
                "errors": r["errors"],
                "extraction": r["extraction"],
                "report": r["report"],
            }
            for case, r in all_results.items()
        }
        print(json.dumps({"cases": output, "missing_files_summary": missing_summary}, indent=2, ensure_ascii=False))
        passed_count = sum(1 for v in output.values() if v["pass"])
        sys.exit(0 if passed_count == len(cases) else 1)

    # Human-readable
    passed_cases = []
    failed_cases = []
    for case_name, result in all_results.items():
        ok = _print_case(case_name, result, report_only=args.report_only)
        (passed_cases if ok else failed_cases).append(case_name)

    total = len(cases)
    print(f"\n{'═' * 62}")
    print(f"  Summary: {len(passed_cases)}/{total} passed")
    if failed_cases:
        print(f"  Failed:  {', '.join(failed_cases)}")
    print(f"{'═' * 62}\n")

    if args.missing_files_report:
        _print_missing_files_summary(all_results)

    sys.exit(0 if not failed_cases else 1)


if __name__ == "__main__":
    main()
