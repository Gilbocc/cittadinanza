import copy
from datetime import datetime
import re
import unicodedata


class LinkedDataBuilder:
    def __init__(self, raw_docs):
        self.docs = copy.deepcopy(raw_docs)
        self.people_registry = {}
        self.person_nodes_by_id = {}
        self.role_index = {}
        self.virtual_translations = []
        self.translation_links_by_original = {}
        self.apostille_links_by_doc = {}
        self.asseverazione_links_by_doc = {}
        self.docs_by_id = {}
        self.subject_doc_index = {}

        self._prepare_analysis_fields()
        self._build_people_registry()
        self._assign_document_ids()
        self.index = self.index_documents()
        self._build_role_index()
        self._build_document_links()

    def _parse_flexible_date(self, value):
        if value in (None, "", "-", "NULL"):
            return None
        if isinstance(value, datetime):
            return value
        raw_s = str(value).strip()
        for fmt in ("%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw_s, fmt)
            except Exception:
                continue
        return None

    def _format_date(self, value):
        if value in (None, "", "-", "NULL"):
            return "NULL"
        parsed = self._parse_flexible_date(value)
        if parsed is not None:
            return parsed.strftime("%d.%m.%Y")
        return str(value).replace("-", ".")

    def _normalize_answer(self, value, mode):
        normalized = self.normalize(str(value)) if value is not None else ""
        yes = {"ok", "si", "yes", "true"}
        no = {"ko", "no", "false"}
        if mode == "OK_KO":
            if normalized in yes:
                return "OK"
            if normalized in no:
                return "KO"
            return "NULL"
        if mode == "SI_NO":
            if normalized in yes:
                return "SI"
            if normalized in no:
                return "NO"
            return "NULL"
        if mode == "OK_NO":
            if normalized in yes:
                return "OK"
            if normalized in no:
                return "NO"
            return "NULL"
        return value

    def _format_ruolo(self, value):
        if value in (None, "", "-", "NULL"):
            return "NULL"
        match = re.search(r"(\d+)\D+(\d{4})", str(value))
        if not match:
            return str(value)
        number, year = match.groups()
        return f"{int(number)}-{year}"

    def _prepare_analysis_fields(self):
        date_keys = {
            "data_iscrizione",
            "data_comparsa_avvocatura",
            "data_visibilita_pm",
            "data_ricorso",
            "data_procura",
            "data_nascita",
            "data_decesso",
            "data",
        }
        answer_modes = {
            "proveniente_dal_brasile": "OK_KO",
            "comparsa_avvocatura": "SI_NO",
            "visibilita_pm": "SI_NO",
            "interventi": "SI_NO",
            "coerenza_linea_discendenza": "OK_KO",
            "minorenne": "SI_NO",
            "firma_presente": "OK_KO",
            "tribunale_brescia_indicato": "OK_NO",
            "rilasciata_in_italia": "OK_NO",
            "scritta_in_italiano": "OK_NO",
            "timbro_diocesi": "OK_KO",
            "formula_negativa_presente": "OK_KO",
        }

        def walk(node):
            if isinstance(node, dict):
                nome = node.get("nome")
                cognome = node.get("cognome")
                if nome is not None or cognome is not None:
                    node["full_name"] = f"{str(nome or '').strip()} {str(cognome or '').strip()}".strip() or "NULL"

                for key in list(node.keys()):
                    value = node.get(key)
                    if key in answer_modes:
                        node[key] = self._normalize_answer(value, answer_modes[key])
                    if key == "tipo":
                        node["tipo_norm"] = self.normalize(str(value)) if value is not None else ""
                    if key in date_keys:
                        parsed = self._parse_flexible_date(value)
                        node[f"{key}_fmt"] = self._format_date(value)
                        node[f"{key}_ord"] = parsed.toordinal() if parsed is not None else None
                    if key == "numero_anno_ruolo":
                        node["numero_anno_ruolo_fmt"] = self._format_ruolo(value)

                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(self.docs)

    def build(self):
        return {
            "docs": self.docs,
            "index": self.index,
            "people_registry": self.people_registry,
            "person_nodes_by_id": self.person_nodes_by_id,
            "role_index": self.role_index,
            "virtual_translations": self.virtual_translations,
            "translation_links_by_original": self.translation_links_by_original,
            "apostille_links_by_doc": self.apostille_links_by_doc,
            "asseverazione_links_by_doc": self.asseverazione_links_by_doc,
            "docs_by_id": self.docs_by_id,
            "subject_doc_index": self.subject_doc_index,
        }

    def normalize(self, text):
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        return text.strip().lower()

    def _levenshtein_distance(self, a, b):
        if not a or not b:
            return max(len(a or ""), len(b or ""))
        if a == b:
            return 0
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i - 1] == b[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[m][n]

    def _is_typo_variant(self, a, b, max_distance=1):
        return self._levenshtein_distance(a, b) <= max_distance

    def _split_name_tokens(self, text):
        if not text:
            return set()
        normalized = self.normalize(str(text))
        particles = {"de", "da", "do", "das", "dos", "del", "della", "di", "du", "la", "le"}
        return {
            token
            for token in re.split(r"[^a-z0-9]+", normalized)
            if token and len(token) > 1 and token not in particles
        }

    def _ordered_name_tokens(self, text):
        normalized = self.normalize(str(text or ""))
        particles = {"de", "da", "do", "das", "dos", "del", "della", "di", "du", "la", "le"}
        return [
            token
            for token in re.split(r"[^a-z0-9]+", normalized)
            if token and len(token) > 1 and token not in particles
        ]

    def _field_match(self, a, b):
        a_norm = self.normalize(a or "")
        b_norm = self.normalize(b or "")
        a_compact = " ".join(re.split(r"[^a-z0-9]+", a_norm)).strip()
        b_compact = " ".join(re.split(r"[^a-z0-9]+", b_norm)).strip()
        if not a_norm or not b_norm:
            return False
        if a_norm == b_norm or a_compact == b_compact:
            return True
        compact_pairs = ((a_compact, b_compact), (b_compact, a_compact))
        for shorter, longer in compact_pairs:
            if shorter and shorter in longer and (" " in shorter or len(shorter) >= 4):
                return True
        a_tokens = self._split_name_tokens(a)
        b_tokens = self._split_name_tokens(b)
        if a_tokens and b_tokens:
            shared_tokens = a_tokens.intersection(b_tokens)
            if len(shared_tokens) >= 2:
                return True
            if len(shared_tokens) == 1:
                shared = next(iter(shared_tokens))
                if min(len(a_tokens), len(b_tokens)) == 1 and len(shared) >= 4:
                    return True
            similar_pairs = 0
            for a_tok in a_tokens:
                for b_tok in b_tokens:
                    if a_tok != b_tok and self._is_typo_variant(a_tok, b_tok, max_distance=1):
                        similar_pairs += 1
            if similar_pairs >= 2:
                return True
            if similar_pairs == 1 and min(len(a_tokens), len(b_tokens)) == 1:
                longest = max(max((len(t) for t in a_tokens), default=0), max((len(t) for t in b_tokens), default=0))
                if longest >= 4:
                    return True
            if similar_pairs == 1 and len(shared_tokens) == 1:
                shared = next(iter(shared_tokens))
                if len(shared) >= 4:
                    shorter_tokens = a_tokens if len(a_tokens) <= len(b_tokens) else b_tokens
                    accounted_tokens = shared_tokens.copy()
                    for a_tok in a_tokens:
                        for b_tok in b_tokens:
                            if a_tok != b_tok and self._is_typo_variant(a_tok, b_tok, max_distance=1):
                                accounted_tokens.add(a_tok)
                                accounted_tokens.add(b_tok)
                    if shorter_tokens.issubset(accounted_tokens):
                        return True
        return False

    def _strict_field_match(self, a, b):
        a_norm = self.normalize(a or "")
        b_norm = self.normalize(b or "")
        if not a_norm or not b_norm:
            return False
        a_compact = " ".join(re.split(r"[^a-z0-9]+", a_norm)).strip()
        b_compact = " ".join(re.split(r"[^a-z0-9]+", b_norm)).strip()
        if a_norm == b_norm or a_compact == b_compact:
            return True
        a_tokens = self._split_name_tokens(a)
        b_tokens = self._split_name_tokens(b)
        if not a_tokens or not b_tokens:
            return False
        shorter = a_tokens if len(a_tokens) <= len(b_tokens) else b_tokens
        longer = b_tokens if shorter is a_tokens else a_tokens
        return shorter.issubset(longer)

    def _strict_name_match(self, a, b):
        if self._strict_field_match(a, b):
            return True

        a_tokens = self._split_name_tokens(a)
        b_tokens = self._split_name_tokens(b)
        if not a_tokens or not b_tokens:
            return False

        shorter = a_tokens if len(a_tokens) <= len(b_tokens) else b_tokens
        longer = b_tokens if shorter is a_tokens else a_tokens

        # Controlled tolerance for OCR/typo drift in given names (e.g. Teodolinda/Theodolinda).
        matched_count = 0
        for token in shorter:
            if token in longer:
                matched_count += 1
                continue
            typo_match = any(
                self._is_typo_variant(token, candidate, max_distance=1)
                and min(len(token), len(candidate)) >= 6
                for candidate in longer
            )
            if typo_match:
                matched_count += 1
                continue
            return False

        return matched_count == len(shorter)

    def _strict_surname_match(self, a, b):
        return self._strict_field_match(a, b)

    def _canonical_identity(self, person):
        if not person:
            return None
        return {"nome": person.get("nome", ""), "cognome": person.get("cognome", "")}

    def _person_signature(self, person):
        if not person:
            return ""
        nome = self.normalize(person.get("nome", ""))
        cognome = self.normalize(person.get("cognome", ""))
        return f"{nome}|{cognome}"

    def _collect_people_nodes(self, node, out):
        if isinstance(node, dict):
            if "nome" in node or "cognome" in node:
                out.append(node)
            for value in node.values():
                self._collect_people_nodes(value, out)
        elif isinstance(node, list):
            for item in node:
                self._collect_people_nodes(item, out)

    def _node_person_id(self, person):
        if not isinstance(person, dict):
            return None
        return person.get("person_id") or person.get("__person_id")

    def _set_node_person_id(self, person, person_id):
        if not isinstance(person, dict) or not person_id:
            return
        person["__person_id"] = person_id
        person["person_id"] = person_id

    def _merge_person_records(self, registry_by_pid, people_mentions, target_pid, source_pid):
        if not target_pid or not source_pid or target_pid == source_pid:
            return False
        target = registry_by_pid.get(target_pid)
        source = registry_by_pid.get(source_pid)
        if target is None or source is None:
            return False

        existing_signatures = {self._person_signature(alias) for alias in target["aliases"]}
        for alias in source["aliases"]:
            signature = self._person_signature(alias)
            if signature and signature not in existing_signatures:
                target["aliases"].append(alias)
                existing_signatures.add(signature)

        for person in people_mentions:
            if self._node_person_id(person) == source_pid:
                self._set_node_person_id(person, target_pid)

        del registry_by_pid[source_pid]
        return True

    def _explicit_pseudonym_nodes(self):
        pseudonyms = []

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "pseudonimi" and isinstance(value, list):
                        for pseudo in value:
                            if isinstance(pseudo, dict):
                                pseudonyms.append(pseudo)
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for doc in self.docs:
            walk(doc)

        return pseudonyms

    def _reconcile_explicit_aliases(self, people_mentions, registry_by_pid):
        explicit_aliases = self._explicit_pseudonym_nodes()
        changed = True
        while changed:
            changed = False
            for alias in explicit_aliases:
                alias_pid = self._node_person_id(alias)
                if not alias_pid or alias_pid not in registry_by_pid:
                    continue
                for candidate in people_mentions:
                    candidate_pid = self._node_person_id(candidate)
                    if not candidate_pid or candidate_pid == alias_pid or candidate_pid not in registry_by_pid:
                        continue
                    if self._registry_person_match(alias, candidate):
                        if self._merge_person_records(registry_by_pid, people_mentions, alias_pid, candidate_pid):
                            changed = True

    def _refresh_person_nodes(self, people_mentions):
        self.person_nodes_by_id = {}
        for person in people_mentions:
            pid = self._node_person_id(person)
            if not pid:
                continue
            current = self.person_nodes_by_id.get(pid)
            if current is None or len(person.keys()) > len(current.keys()):
                self.person_nodes_by_id[pid] = person

    def _registry_person_match(self, person_a, person_b):
        if not person_a or not person_b:
            return False
        a_nome = self._identity_value(person_a.get("nome"))
        b_nome = self._identity_value(person_b.get("nome"))
        a_cognome = self._identity_value(person_a.get("cognome"))
        b_cognome = self._identity_value(person_b.get("cognome"))
        has_nome = bool(a_nome and b_nome)
        has_cognome = bool(a_cognome and b_cognome)
        if has_nome and has_cognome:
            return self._strict_name_match(a_nome, b_nome) and self._strict_surname_match(a_cognome, b_cognome)
        if has_cognome:
            return self._strict_surname_match(a_cognome, b_cognome)
        if has_nome:
            return self._strict_name_match(a_nome, b_nome)
        return False

    def _identity_value(self, value):
        text = (str(value) if value is not None else "").strip()
        return "" if self.normalize(text) in {"", "null", "-"} else text

    def _surname_token_overlap(self, person_a, person_b):
        a_tokens = self._split_name_tokens(self._identity_value((person_a or {}).get("cognome")))
        b_tokens = self._split_name_tokens(self._identity_value((person_b or {}).get("cognome")))
        return len(a_tokens.intersection(b_tokens))

    def _primary_name_token_match(self, person_a, person_b):
        a_tokens = self._ordered_name_tokens(self._identity_value((person_a or {}).get("nome")))
        b_tokens = self._ordered_name_tokens(self._identity_value((person_b or {}).get("nome")))
        if not a_tokens or not b_tokens:
            return False
        a_primary = a_tokens[0]
        b_primary = b_tokens[0]
        if a_primary == b_primary:
            return True
        return self._is_typo_variant(a_primary, b_primary, max_distance=1) and min(len(a_primary), len(b_primary)) >= 6

    def _reconcile_ricorso_role_aliases(self, people_mentions, registry_by_pid):
        ricorso = next((d for d in self.docs if d.get("document_type") == "Ricorso"), None)
        if not ricorso:
            return

        schema = ricorso.get("schema", {})
        lineage = schema.get("linea_discendenza", [])
        ricorrenti = schema.get("ricorrenti_maggiorenni", []) + schema.get("ricorrenti_minorenni", [])

        changed = True
        while changed:
            changed = False
            for ric in ricorrenti:
                ric_pid = self._node_person_id(ric)
                if not ric_pid or ric_pid not in registry_by_pid:
                    continue
                for lin in lineage:
                    lin_pid = self._node_person_id(lin)
                    if not lin_pid or lin_pid == ric_pid or lin_pid not in registry_by_pid:
                        continue

                    if not self._primary_name_token_match(ric, lin):
                        continue
                    if self._surname_token_overlap(ric, lin) < 1:
                        continue

                    if self._merge_person_records(registry_by_pid, people_mentions, lin_pid, ric_pid):
                        changed = True
                        break
                if changed:
                    break

    def _build_people_registry(self):
        people_mentions = []
        for doc in self.docs:
            self._collect_people_nodes(doc, people_mentions)

        registry = []
        for person in people_mentions:
            signature = self._person_signature(person)
            if not signature or signature == "|":
                continue
            matched = None
            for rec in registry:
                if any(self._registry_person_match(person, alias) for alias in rec["aliases"]):
                    matched = rec
                    break
            if matched is None:
                person_id = f"P-{len(registry) + 1:04d}"
                matched = {"person_id": person_id, "aliases": [self._canonical_identity(person)]}
                registry.append(matched)
            else:
                existing_signatures = {self._person_signature(alias) for alias in matched["aliases"]}
                canonical = self._canonical_identity(person)
                if self._person_signature(canonical) not in existing_signatures:
                    matched["aliases"].append(canonical)
            self._set_node_person_id(person, matched["person_id"])

        # Propagate person_id through person-level pseudonym relationships
        # (e.g. linea_discendenza_pseudonimi entries that have pseudonimi on the person node)
        for person in people_mentions:
            main_pid = self._node_person_id(person)
            if not main_pid:
                continue
            for pseudo in (person.get("pseudonimi", []) if isinstance(person, dict) else []):
                if isinstance(pseudo, dict):
                    self._set_node_person_id(pseudo, main_pid)

        # Propagate person_id through schema-level pseudonimi
        # (e.g. CNN schema has soggetto + pseudonimi as siblings)
        for doc in self.docs:
            schema = doc.get("schema", {})
            soggetto = schema.get("soggetto")
            doc_pseudonimi = schema.get("pseudonimi", [])
            if isinstance(soggetto, dict) and isinstance(doc_pseudonimi, list):
                main_pid = self._node_person_id(soggetto)
                if main_pid:
                    for pseudo in doc_pseudonimi:
                        if isinstance(pseudo, dict):
                            self._set_node_person_id(pseudo, main_pid)

        registry_by_pid = {rec["person_id"]: rec for rec in registry}
        self._reconcile_explicit_aliases(people_mentions, registry_by_pid)
        self._reconcile_ricorso_role_aliases(people_mentions, registry_by_pid)
        self._refresh_person_nodes(people_mentions)
        self.people_registry = registry_by_pid

    def _unique_pids(self, people):
        seen = set()
        ordered = []
        for person in people:
            if not isinstance(person, dict):
                continue
            pid = person.get("person_id") or person.get("__person_id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            ordered.append(pid)
        return ordered

    def _build_role_index(self):
        ricorso = self.index.get("ricorso")
        cnn = self.index.get("naturalization")

        lineage_people = []
        ricorrenti_people = []

        if ricorso:
            schema = ricorso.get("schema", {})
            lineage_people = schema.get("linea_discendenza", [])
            ricorrenti_people = schema.get("ricorrenti_maggiorenni", []) + schema.get("ricorrenti_minorenni", [])

        lineage_ids = self._unique_pids(lineage_people)
        ricorrenti_ids = self._unique_pids(ricorrenti_people)

        avo_pid = None
        if cnn and isinstance(cnn.get("schema", {}).get("soggetto"), dict):
            avo_pid = cnn["schema"]["soggetto"].get("person_id") or cnn["schema"]["soggetto"].get("__person_id")
        if avo_pid is None and lineage_people:
            first = lineage_people[0]
            if isinstance(first, dict):
                avo_pid = first.get("person_id") or first.get("__person_id")

        ricorrenti_set = set(ricorrenti_ids)
        discendenti_ids = [pid for pid in lineage_ids[1:] if pid not in ricorrenti_set]

        self.role_index = {
            "avo_person_id": avo_pid,
            "lineage_person_ids": lineage_ids,
            "ricorrenti_person_ids": ricorrenti_ids,
            "discendenti_person_ids": discendenti_ids,
        }

    def _assign_document_ids(self):
        for i, doc in enumerate(self.docs, 1):
            if "__doc_id" not in doc:
                doc["__doc_id"] = f"DOC-{i:04d}"

    def index_documents(self):
        index = {
            "indice": None,
            "ricorso": None,
            "procure": [],
            "birth_docs": [],
            "death_docs": [],
            "naturalization": None,
            "apostilles": [],
            "translations": [],
            "asseverazioni": [],
        }
        for d in self.docs:
            t = d["document_type"]
            if t == "IndiceProcedimento.html":
                index["indice"] = d
            elif t == "Ricorso":
                index["ricorso"] = d
            elif t == "Procura":
                index["procure"].append(d)
            elif t == "Atto di nascita":
                index["birth_docs"].append(d)
            elif t == "Atto di morte":
                index["death_docs"].append(d)
            elif t == "Certificato Negativo di Naturalizzazione":
                index["naturalization"] = d
            elif t == "Apostille":
                index["apostilles"].append(d)
            elif t == "Traduzione":
                index["translations"].append(d)
            elif t == "Asseverazione":
                index["asseverazioni"].append(d)
        return index

    def _all_translations(self):
        return self.index["translations"] + self.virtual_translations

    def _name_surname_match(self, person_a, person_b):
        if not person_a or not person_b:
            return False
        full_a = f"{person_a.get('nome', '')} {person_a.get('cognome', '')}".strip()
        full_b = f"{person_b.get('nome', '')} {person_b.get('cognome', '')}".strip()
        return self._field_match(full_a, full_b)

    def _identity_variants(self, person):
        canonical = self._canonical_identity(person)
        if not canonical:
            return []
        variants = [canonical]
        for pseudo in person.get("pseudonimi", []) if isinstance(person, dict) else []:
            variants.append(self._canonical_identity(pseudo))
        return [v for v in variants if v and (v.get("nome") or v.get("cognome"))]

    def people_match(self, person_a, person_b):
        if person_a and person_b:
            pid_a = person_a.get("person_id") or person_a.get("__person_id")
            pid_b = person_b.get("person_id") or person_b.get("__person_id")
            if pid_a and pid_b and pid_a == pid_b:
                return True
        for left in self._identity_variants(person_a):
            for right in self._identity_variants(person_b):
                if self._registry_person_match(left, right):
                    return True
        return False

    def _get_known_pseudonyms(self, person):
        pseudonyms = []
        if not person:
            return pseudonyms
        cnn = self.index.get("naturalization")
        if cnn and self.people_match(cnn.get("schema", {}).get("soggetto", {}), person):
            for pseudo in cnn.get("schema", {}).get("pseudonimi", []):
                if pseudo and (pseudo.get("nome") or pseudo.get("cognome")):
                    pseudonyms.append(pseudo)
        ricorso = self.index.get("ricorso")
        if ricorso:
            for lineage_person in ricorso.get("schema", {}).get("linea_discendenza_pseudonimi", []):
                if self.people_match(lineage_person, person):
                    for pseudo in lineage_person.get("pseudonimi", []):
                        if pseudo and (pseudo.get("nome") or pseudo.get("cognome")):
                            pseudonyms.append(pseudo)
                    break
        return pseudonyms

    def person_in_list(self, person, people):
        for candidate in people:
            if self.people_match(person, candidate):
                return True
            for pseudo in self._get_known_pseudonyms(candidate):
                if self.people_match(person, pseudo):
                    return True
        for pseudo in self._get_known_pseudonyms(person):
            for candidate in people:
                if self.people_match(pseudo, candidate):
                    return True
        return False

    def _subject_signature(self, subjects):
        normalized = []
        for s in subjects or []:
            if not isinstance(s, dict):
                continue
            pid = s.get("person_id") or s.get("__person_id")
            if pid:
                normalized.append(pid)
            else:
                normalized.append(self._person_signature(s))
        return tuple(sorted(v for v in normalized if v))

    def _doc_subjects(self, doc):
        schema = doc.get("schema", {}) if isinstance(doc, dict) else {}
        if doc.get("document_type") == "Traduzione":
            return schema.get("oggetto", {}).get("soggetto", [])
        subject = schema.get("soggetto")
        if isinstance(subject, list):
            return subject
        if isinstance(subject, dict):
            return [subject]
        return []

    def _subject_overlap_count(self, subjects_a, subjects_b):
        if not subjects_a or not subjects_b:
            return 0
        overlap = 0
        for s in subjects_a:
            s_pid = (s.get("person_id") or s.get("__person_id")) if isinstance(s, dict) else None
            matched = False
            for candidate in subjects_b:
                c_pid = (candidate.get("person_id") or candidate.get("__person_id")) if isinstance(candidate, dict) else None
                if s_pid and c_pid:
                    if s_pid == c_pid:
                        matched = True
                        break
                elif self.people_match(s, candidate):
                    matched = True
                    break
            if matched:
                overlap += 1
        return overlap

    def _choose_best_doc_match(self, subjects, candidates):
        best_doc = None
        best_score = 0
        for candidate in candidates:
            score = self._subject_overlap_count(subjects, self._doc_subjects(candidate))
            if score > best_score:
                best_score = score
                best_doc = candidate
        return best_doc if best_score > 0 else None

    def _person_lookup_keys(self, person):
        if not isinstance(person, dict):
            return []
        pid = person.get("person_id") or person.get("__person_id")
        if pid:
            return [("pid", pid)]
        return []

    def _register_translation_link(self, original_doc, translation_doc):
        original_id = original_doc.get("__doc_id") if original_doc else None
        if not original_id:
            return
        translation_doc["__linked_original_doc_id"] = original_id
        self.translation_links_by_original.setdefault(original_id, []).append(translation_doc)

    def _docs_of_type(self, doc_type):
        if doc_type == "IndiceProcedimento.html":
            return [self.index["indice"]] if self.index.get("indice") else []
        if doc_type == "Ricorso":
            return [self.index["ricorso"]] if self.index.get("ricorso") else []
        if doc_type == "Procura":
            return self.index["procure"]
        if doc_type == "Atto di nascita":
            return self.index["birth_docs"]
        if doc_type == "Atto di morte":
            return self.index["death_docs"]
        if doc_type == "Certificato Negativo di Naturalizzazione":
            return [self.index["naturalization"]] if self.index.get("naturalization") else []
        if doc_type == "Traduzione":
            return self._all_translations()
        if doc_type == "Apostille":
            return self.index["apostilles"]
        if doc_type == "Asseverazione":
            return self.index["asseverazioni"]
        return [d for d in self.docs if d.get("document_type") == doc_type]

    def _normalize_document_reference_type(self, value):
        normalized = self.normalize(str(value or ""))
        if normalized in {"", "null", "-"}:
            return None
        if "naturalizz" in normalized:
            return "Certificato Negativo di Naturalizzazione"
        if "procura" in normalized:
            return "Procura"
        if "nascita" in normalized or "nascimento" in normalized:
            return "Atto di nascita"
        if "morte" in normalized or "obito" in normalized or "obito" in normalized:
            return "Atto di morte"
        if "traduz" in normalized or "traduzione" in normalized:
            return "Traduzione"
        return value

    def _find_candidate_original_docs(self, doc_type, source_doc=None):
        doc_type = self._normalize_document_reference_type(doc_type) or doc_type
        source_doc = self._normalize_document_reference_type(source_doc) or source_doc
        if doc_type == "Traduzione":
            translations = self._all_translations()
            if source_doc is None:
                return translations
            return [
                t for t in translations
                if self._normalize_document_reference_type(
                    t.get("schema", {}).get("oggetto", {}).get("document_type")
                ) == source_doc
            ]
        return self._docs_of_type(doc_type)

    def _infer_translation_location(self, source_doc, subjects):
        source_type = self._normalize_document_reference_type(source_doc.get("document_type"))
        for a in self.index.get("asseverazioni", []):
            obj = a.get("schema", {}).get("oggetto", {})
            if self._normalize_document_reference_type(obj.get("document_type")) != "Traduzione":
                continue
            if self._normalize_document_reference_type(obj.get("documento_originale")) != source_type:
                continue
            if any(self.person_in_list(s, subjects) for s in obj.get("soggetto", [])):
                return "Italia"
        for a in self.index.get("apostilles", []):
            obj = a.get("schema", {}).get("oggetto", {})
            if self._normalize_document_reference_type(obj.get("document_type")) != "Traduzione":
                continue
            if self._normalize_document_reference_type(obj.get("documento_originale")) != source_type:
                continue
            if any(self.person_in_list(s, subjects) for s in obj.get("soggetto", [])):
                return "Estero"
        return "NULL"

    def _link_procura_variants_as_translations(self):
        originals = []
        italian_variants = []
        for p in self.index.get("procure", []):
            status = p.get("schema", {}).get("scritta_in_italiano", "NULL")
            if status == "NO":
                originals.append(p)
            elif status == "OK":
                italian_variants.append(p)

        for original in originals:
            orig_schema = original.get("schema", {})
            orig_subjects = orig_schema.get("soggetto", [])
            signature = self._subject_signature(orig_subjects)
            orig_date = orig_schema.get("data_procura")

            best = None
            for candidate in italian_variants:
                cand_schema = candidate.get("schema", {})
                if self._subject_signature(cand_schema.get("soggetto", [])) != signature:
                    continue
                if cand_schema.get("data_procura") == orig_date:
                    best = candidate
                    break
                if best is None:
                    best = candidate
            if best is None:
                continue

            translation_doc = {
                "document_type": "Traduzione",
                "schema": {
                    "oggetto": {"document_type": "Procura", "soggetto": orig_subjects},
                    "sede_traduttore": self._infer_translation_location(original, orig_subjects),
                },
                "source_pages": best.get("source_pages", {}),
                "__doc_id": f"VIRT-TR-{best.get('__doc_id', 'UNKNOWN')}",
                "__virtual": True,
                "__linked_original_doc_id": original.get("__doc_id"),
                "__derived_from_doc_id": best.get("__doc_id"),
            }
            self.virtual_translations.append(translation_doc)
            self._register_translation_link(original, translation_doc)

    def _link_explicit_translations(self):
        for translation in self.index["translations"]:
            obj = translation.get("schema", {}).get("oggetto", {})
            doc_type = self._normalize_document_reference_type(obj.get("document_type"))
            subjects = obj.get("soggetto", [])
            if not doc_type:
                continue
            best = self._choose_best_doc_match(subjects, self._docs_of_type(doc_type))
            if best is not None:
                self._register_translation_link(best, translation)

    def _linked_translation_for_original(self, original_doc, source_doc_type):
        source_doc_type = self._normalize_document_reference_type(source_doc_type) or source_doc_type
        for translation in self.translation_links_by_original.get(original_doc.get("__doc_id"), []):
            obj_type = self._normalize_document_reference_type(
                translation.get("schema", {}).get("oggetto", {}).get("document_type")
            )
            if obj_type == source_doc_type:
                return translation
        return None

    def _link_inferred_translations_from_certificates(self):
        for index_key, sede in (("apostilles", "Estero"), ("asseverazioni", "Italia")):
            for cert_doc in self.index.get(index_key, []):
                obj = cert_doc.get("schema", {}).get("oggetto", {})
                target_type = self._normalize_document_reference_type(obj.get("document_type"))
                source_doc_type = self._normalize_document_reference_type(obj.get("documento_originale"))
                subjects = obj.get("soggetto", [])
                if target_type != "Traduzione" or not source_doc_type or not subjects:
                    continue
                candidates = self._docs_of_type(source_doc_type)
                best = self._choose_best_doc_match(subjects, candidates)
                if best is None:
                    continue
                if self._linked_translation_for_original(best, source_doc_type):
                    continue
                translation_doc = {
                    "document_type": "Traduzione",
                    "schema": {
                        "oggetto": {"document_type": source_doc_type, "soggetto": subjects},
                        "sede_traduttore": sede,
                    },
                    "source_pages": cert_doc.get("source_pages", {}),
                    "__doc_id": f"VIRT-CERT-TR-{cert_doc.get('__doc_id', 'UNKNOWN')}",
                    "__virtual": True,
                    "__linked_original_doc_id": best.get("__doc_id"),
                    "__derived_from_doc_id": cert_doc.get("__doc_id"),
                }
                self.virtual_translations.append(translation_doc)
                self._register_translation_link(best, translation_doc)

    def _link_certificates(self, index_key):
        cert_docs = self.index.get(index_key, [])
        target_map = self.apostille_links_by_doc if index_key == "apostilles" else self.asseverazione_links_by_doc

        for cert_doc in cert_docs:
            obj = cert_doc.get("schema", {}).get("oggetto", {})
            target_type = self._normalize_document_reference_type(obj.get("document_type"))
            source_doc_type = self._normalize_document_reference_type(obj.get("documento_originale"))
            subjects = obj.get("soggetto", [])
            if not target_type:
                continue

            candidates = self._find_candidate_original_docs(target_type, source_doc=source_doc_type)
            best = self._choose_best_doc_match(subjects, candidates)
            if best is None:
                continue
            linked_id = best.get("__doc_id")
            if not linked_id:
                continue
            cert_doc["__linked_doc_id"] = linked_id
            target_map.setdefault(linked_id, []).append(cert_doc)

    def _build_docs_by_id_index(self):
        self.docs_by_id = {}
        for doc in self.docs + self.virtual_translations:
            doc_id = doc.get("__doc_id")
            if doc_id:
                self.docs_by_id[doc_id] = doc

    def _register_doc_subjects(self, doc, logical_doc_type=None):
        doc_id = doc.get("__doc_id")
        if not doc_id:
            return
        doc_type = logical_doc_type or doc.get("document_type")
        for subject in self._doc_subjects(doc):
            for kind, value in self._person_lookup_keys(subject):
                self.subject_doc_index.setdefault((doc_type, kind, value), set()).add(doc_id)

    def _build_subject_doc_index(self):
        self._build_docs_by_id_index()
        for index_key, doc_type in [
            ("procure", "Procura"),
            ("birth_docs", "Atto di nascita"),
            ("death_docs", "Atto di morte"),
        ]:
            for doc in self.index.get(index_key, []):
                self._register_doc_subjects(doc, doc_type)
        if self.index.get("naturalization"):
            self._register_doc_subjects(self.index["naturalization"], "Certificato Negativo di Naturalizzazione")
        for doc in self._all_translations():
            self._register_doc_subjects(doc, "Traduzione")

    def _build_document_links(self):
        self.virtual_translations = []
        self.translation_links_by_original = {}
        self.apostille_links_by_doc = {}
        self.asseverazione_links_by_doc = {}
        self.docs_by_id = {}
        self.subject_doc_index = {}

        self._link_procura_variants_as_translations()
        self._link_explicit_translations()
        self._link_inferred_translations_from_certificates()
        self._link_certificates("apostilles")
        self._link_certificates("asseverazioni")
        self._build_subject_doc_index()


def build_linked_data(raw_docs):
    return LinkedDataBuilder(raw_docs).build()
