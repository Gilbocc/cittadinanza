from datetime import datetime
import re
import unicodedata

class DocumentValidator:

    def __init__(self, docs):
        self.docs = docs
        self.index = self.index_documents()
        self.ko_list = []
        self.ko_reasons = {}

    # -------------------------------------------------
    # DOCUMENT INDEXING
    # -------------------------------------------------
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
            "asseverazioni": []
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

    # -------------------------------------------------
    # HELPERS
    # -------------------------------------------------
    def mark_ko(self, question, reason):
        if question not in self.ko_reasons:
            self.ko_list.append(question)
        self.ko_reasons[question] = reason

    def null_value(self, value="NULL"):
        return "NULL" if value in (None, "", "-", []) else value

    def format_date(self, value):
        if value in (None, "", "-", "NULL"):
            return "NULL"
        parsed = self.parse_flexible_date(value)
        if parsed is not None:
            return parsed.strftime("%d.%m.%Y")
        return str(value).replace("-", ".")

    def parse_flexible_date(self, value):
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

    def answer_ok_ko(self, value):
        normalized = self.normalize(str(value)) if value is not None else ""
        if normalized in {"ok", "si", "yes", "true"}:
            return "OK"
        if normalized in {"ko", "no", "false"}:
            return "KO"
        return "NULL"

    def answer_yes_no(self, value):
        normalized = self.normalize(str(value)) if value is not None else ""
        if normalized in {"si", "ok", "yes", "true"}:
            return "SI"
        if normalized in {"no", "ko", "false"}:
            return "NO"
        return "NULL"

    def answer_ok_no(self, value):
        normalized = self.normalize(str(value)) if value is not None else ""
        if normalized in {"ok", "si", "yes", "true"}:
            return "OK"
        if normalized in {"no", "ko", "false"}:
            return "NO"
        return "NULL"

    def full_name(self, person):
        if not person:
            return "NULL"
        return f"{person.get('nome', '').strip()} {person.get('cognome', '').strip()}".strip() or "NULL"

    def _levenshtein_distance(self, a, b):
        """Compute edit distance between strings (for typo tolerance)."""
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
        """Check if strings are similar enough to be typos (edit distance <= max_distance)."""
        return self._levenshtein_distance(a, b) <= max_distance

    def _split_name_tokens(self, text):
        """Split a name field into tokens, normalizing each."""
        if not text:
            return set()
        normalized = self.normalize(str(text))
        return set(token for token in re.split(r"[^a-z0-9]+", normalized) if token and len(token) > 1)

    def _field_match(self, a, b):
        """Match two name fields with resilience to multi-word names and misspellings."""
        a_norm = self.normalize(a or "")
        b_norm = self.normalize(b or "")
        a_compact = " ".join(re.split(r"[^a-z0-9]+", a_norm)).strip()
        b_compact = " ".join(re.split(r"[^a-z0-9]+", b_norm)).strip()
        
        if not a_norm or not b_norm:
            return False

        if a_norm == b_norm or a_compact == b_compact:
            return True
        
        # Exact substring match (preferred), but avoid collapsing short single-
        # token names such as "Ana" into "Ana Ana".
        compact_pairs = ((a_compact, b_compact), (b_compact, a_compact))
        for shorter, longer in compact_pairs:
            if shorter and shorter in longer:
                if " " in shorter or len(shorter) >= 4:
                    return True
        
        # Token overlap: check if any single-word tokens match (handles multi-word names spread across fields)
        a_tokens = self._split_name_tokens(a)
        b_tokens = self._split_name_tokens(b)
        
        if a_tokens and b_tokens:
            # Exact token overlap. Require stronger evidence than a single short
            # token so we do not collapse identities like "Ana" and "Ana Ana".
            shared_tokens = a_tokens.intersection(b_tokens)
            if len(shared_tokens) >= 2:
                return True
            if len(shared_tokens) == 1:
                shared = next(iter(shared_tokens))
                if min(len(a_tokens), len(b_tokens)) == 1 and len(shared) >= 4:
                    return True
            
            # Typo-tolerant token overlap with the same guardrails.
            similar_pairs = 0
            for a_tok in a_tokens:
                for b_tok in b_tokens:
                    if self._is_typo_variant(a_tok, b_tok, max_distance=1):
                        similar_pairs += 1
            if similar_pairs >= 2:
                return True
            if similar_pairs == 1 and min(len(a_tokens), len(b_tokens)) == 1:
                longest = max(max((len(t) for t in a_tokens), default=0), max((len(t) for t in b_tokens), default=0))
                if longest >= 4:
                    return True
        
        return False

    def _birth_subject_pool(self):
        return [doc.get("schema", {}).get("soggetto", {}) for doc in self.index.get("birth_docs", [])]

    def _same_name_mentions_in_birth_pool(self, person):
        target_name = person.get("nome", "") if person else ""
        return [candidate for candidate in self._birth_subject_pool() if self._field_match(target_name, candidate.get("nome", ""))]

    def _canonical_identity(self, person):
        if not person:
            return None
        return {
            "nome": person.get("nome", ""),
            "cognome": person.get("cognome", ""),
        }

    def _identity_variants(self, person):
        """Return canonical identity plus any pseudonyms declared on the person."""
        canonical = self._canonical_identity(person)
        if not canonical:
            return []

        variants = [canonical]
        for pseudo in person.get("pseudonimi", []) if isinstance(person, dict) else []:
            variants.append(self._canonical_identity(pseudo))

        cleaned = []
        for variant in variants:
            if not variant:
                continue
            if variant.get("nome") or variant.get("cognome"):
                cleaned.append(variant)
        return cleaned

    def _name_surname_match(self, person_a, person_b):
        """Match two identities requiring both name and surname, typo-tolerant."""
        if not person_a or not person_b:
            return False
        return self._field_match(person_a.get("nome", ""), person_b.get("nome", "")) and self._field_match(
            person_a.get("cognome", ""), person_b.get("cognome", "")
        )

    def _identity_or_pseudonym_match(self, person_a, person_b):
        for left in self._identity_variants(person_a):
            for right in self._identity_variants(person_b):
                if self._name_surname_match(left, right):
                    return True
        return False

    def people_match(self, person_a, person_b):
        return self._identity_or_pseudonym_match(person_a, person_b)

    def person_in_list(self, person, people):
        return any(self.people_match(person, candidate) for candidate in people)

    def unique_people(self, people):
        unique = []
        for person in people:
            if not self.person_in_list(person, unique):
                unique.append(person)
        return unique

    def get_descendants(self):
        lineage = self.get_lineage()[1:]
        ricorrenti = self.get_ricorrenti()
        return [person for person in lineage if not self.person_in_list(person, ricorrenti)]

    def find_birth_doc_for_person(self, person):
        for doc in self.index["birth_docs"]:
            if self.people_match(doc["schema"].get("soggetto", {}), person):
                return doc
        return None

    def find_procura_for_person(self, person):
        for procura in self.index["procure"]:
            for subject in procura["schema"].get("soggetto", []):
                if self.people_match(subject, person):
                    return procura, subject
        return None, None

    def get_representatives(self, person_data):
        return person_data.get("rappresentanti_legali", person_data.get("rappresentato_da", []))

    def lineage_summary(self):
        lineage = self.get_lineage()
        if not lineage:
            return "Linea di discendenza non disponibile"
        return " -> ".join(self.full_name(person) for person in lineage)

    def same_lawyer(self, ricorso_lawyers, procura_lawyers):
        for ricorso_lawyer in ricorso_lawyers:
            for procura_lawyer in procura_lawyers:
                if self.people_match(ricorso_lawyer, procura_lawyer):
                    return True
        return False

    def is_avo_death_required(self, avo_birth=None):
        avo_birth = avo_birth or self.find_avo_birth()
        if not avo_birth:
            return False
        birth_date = self.parse_date(avo_birth["schema"].get("data_nascita"))
        area = avo_birth["schema"].get("area_nascita")
        if not birth_date:
            return False

        checks = [birth_date > datetime(1861, 3, 17)]
        if area == "B":
            checks.append(birth_date >= datetime(1866, 10, 19))
        if area == "C":
            checks.append(birth_date >= datetime(1870, 9, 20))
        if area == "D":
            checks.append(birth_date > datetime(1920, 7, 16))
        return any(check is False for check in checks)

    def format_ruolo(self, value):
        if value in (None, "", "-", "NULL"):
            return "NULL"
        match = re.search(r"(\d+)\D+(\d{4})", str(value))
        if not match:
            return str(value)
        number, year = match.groups()
        return f"{number.zfill(4)}-{year}"

    def get_ricorrenti(self):
        ricorso = self.index.get("ricorso")
        if not ricorso:
            return []
        instr = ricorso["schema"]
        return instr.get("ricorrenti_maggiorenni", []) + instr.get("ricorrenti_minorenni", [])

    def get_lineage(self):
        ricorso = self.index.get("ricorso")
        if not ricorso:
            return []
        linea = ricorso["schema"].get("linea_discendenza", [])
        return linea

    # -------------------------------------------------
    # AVO BIRTH/DEATH IDENTIFICATION
    # -------------------------------------------------
    def get_avo_names(self):
        cnn = self.index.get("naturalization")
        if cnn:
            return [cnn["schema"]["soggetto"]] + cnn["schema"]["pseudonimi"]
        lineage = self.get_lineage()
        if lineage:
            return [lineage[0]]
        return []
    
    
    def find_avo_birth(self):
        avo_names = self.get_avo_names()
        for doc in self.index["birth_docs"]:
            s = doc["schema"]["soggetto"]
            for n in avo_names:
                if self.people_match(n, s):
                    return doc
        return None

    def find_avo_death(self):
        avo_names = self.get_avo_names()
        for doc in self.index["death_docs"]:
            s = doc["schema"]["soggetto"]
            for n in avo_names:
                if self.people_match(n, s):
                    return doc
        return None
    
    def parse_date(self, d): 
        try: return datetime.strptime(d,"%d-%m-%Y") 
        except: return None

    def normalize(self, text):
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        return text.strip().lower()

    # -------------------------------------------------
    # APOSTILLE / TRANSLATION / ASSEVERAZIONE HELPERS
    # -------------------------------------------------
    def find_translation(self, doc_type, soggetto):
        for t in self.index["translations"]:
            obj = t["schema"]["oggetto"]
            if obj["document_type"] == doc_type:
                for s in obj.get("soggetto", []):
                    if self.people_match(s, soggetto):
                        return t
        return None

    def has_apostille(self, doc_type, soggetto, source_doc=None):
        for a in self.index["apostilles"]:
            obj = a["schema"]["oggetto"]
            if obj["document_type"] == doc_type and (source_doc is None or source_doc == obj.get("documento_originale")):
                for s in obj.get("soggetto", []):
                    if self.people_match(s, soggetto):
                        return True
        return False

    def has_asseverazione(self, doc_type, soggetto, source_doc=None):
        for a in self.index["asseverazioni"]:
            obj = a["schema"]["oggetto"]
            if obj["document_type"] == doc_type and (source_doc is None or source_doc == obj.get("documento_originale")):
                for s in obj.get("soggetto", []):
                    if self.people_match(s, soggetto):
                        return True
        return False

    # -------------------------------------------------
    # SECTION 0: Basic document presence
    # -------------------------------------------------
    # 0. E' presente:
    # A) il file IndiceProcedimento.html? [OK/KO]
    # B) il ricorso? [OK/KO]
    # C) la procura in versione originale di ciascun ricorrente? (Rispondi in base al relativo "document_type") [OK/KO]
    # i. Se KO, quale procura in versione originale manca? [Indica nome e cognome/NULL]
    # D) l'atto di nascita dell'avo in versione originale? (Rispondi in base al relativo "document_type") [OK/KO]
    # E) l'atto di morte dell'avo in versione originale, se necessario ai sensi del blocco 6? (Rispondi in base al relativo "document_type") [OK/KO]
    # F) il certificato negativo di naturalizzazione in versione originale? (Rispondi in base al relativo "document_type") [OK/KO]
    # G) l'atto di nascita in versione originale di ciascun discendente? (Rispondi in base al relativo "document_type") [OK/KO]
    # i. Se KO, quale atto di nascita in versione originale manca? [Indica nome e cognome/NULL]
    # H) l'atto di nascita in versione originale di ciascun ricorrente? (Rispondi in base al relativo "document_type") [OK/KO]
    # i. Se KO, quale atto di nascita in versione originale manca? [Indica nome e cognome/NULL] 
    def section_0(self):
        results = {}
        discendenti = self.get_descendants()
        ricorrenti = self.get_ricorrenti()
        avo_birth = self.find_avo_birth()
        avo_death = self.find_avo_death()
        death_required = self.is_avo_death_required(avo_birth)
        birth_subjects = [b["schema"].get("soggetto", {}) for b in self.index["birth_docs"]]

        results["A"] = "OK" if self.index.get("indice") else "KO"
        if results["A"] == "KO": self.mark_ko("0A", "IndiceProcedimento.html mancante")

        results["B"] = "OK" if self.index.get("ricorso") else "KO"
        if results["B"] == "KO": self.mark_ko("0B", "Ricorso mancante")

        # Procure
        found_procure = [s for p in self.index["procure"] for s in p["schema"].get("soggetto", [])]
        missing_procure = [self.full_name(r) for r in ricorrenti if not self.person_in_list(r, found_procure)]
        results["C"] = "OK" if not missing_procure else "KO"
        results["Ci"] = ", ".join(missing_procure) if missing_procure else "NULL"
        if missing_procure: self.mark_ko("0C", f"Procure mancanti: {results['Ci']}")

        results["D"] = "OK" if avo_birth else "KO"
        if results["D"] == "KO": self.mark_ko("0D", "Atto di nascita avo mancante")

        results["E"] = "OK" if (not death_required or avo_death) else "KO"
        if results["E"] == "KO": self.mark_ko("0E", "Atto di morte avo richiesto ma mancante")

        results["F"] = "OK" if self.index.get("naturalization") else "KO"
        if results["F"] == "KO": self.mark_ko("0F", "Certificato Negativo di Naturalizzazione mancante")

        missing_desc_birth = [self.full_name(person) for person in discendenti if not self.person_in_list(person, birth_subjects)]
        results["G"] = "OK" if not missing_desc_birth else "KO"
        results["Gi"] = ", ".join(missing_desc_birth) if missing_desc_birth else "NULL"
        if missing_desc_birth:
            self.mark_ko("0G", f"Atti di nascita dei discendenti mancanti: {results['Gi']}")

        missing_ric_birth = [self.full_name(person) for person in ricorrenti if not self.person_in_list(person, birth_subjects)]
        results["H"] = "OK" if not missing_ric_birth else "KO"
        results["Hi"] = ", ".join(missing_ric_birth) if missing_ric_birth else "NULL"
        if missing_ric_birth:
            self.mark_ko("0H", f"Atti di nascita dei ricorrenti mancanti: {results['Hi']}")

        return results

    # -------------------------------------------------
    # SECTION 1: Provenienza ricorso
    # -------------------------------------------------
    # 1. Si tratta di un ricorso proveniente dal Brasile? (Lo puoi desumere dal testo del ricorso) [OK/KO]
    def section_1(self):
        doc = self.index.get("ricorso")
        if not doc:
            return {"1": "KO"}
        
        instr = doc["schema"]
        result = self.answer_ok_ko(instr.get("proveniente_dal_brasile", "NULL"))
        if result == "KO":
            self.mark_ko("1", "Il ricorso non risulta proveniente dal Brasile")
        return { "1" : result }

    # -------------------------------------------------
    # SECTION 2: IndiceProcedimento.html details
    # -------------------------------------------------
    # 2. Prendi il file INDICEPROCEDIMENTO.HTML:
    # A) Quando è stato iscritto il ricorso? (È la “data evento” indicata nella colonna a sinistra, in corrispondenza della “descrizione” “iscritto a ruolo generale”) [GG.MM.AAAA]
    # B) Il ricorso è stato iscritto dopo il 28.2.2023 incluso? [OK/KO]
    # C) Il ricorso è stato iscritto prima del 27.3.2025 escluso? [OK/KO]
    # D) È presente la comparsa di risposta dell’Avvocatura dello Stato? [SI/NO]
    # i. Se è presente la comparsa di risposta, quando si è costituita l’Avvocatura dello Stato? [GG.MM.AAAA/NULL]
    # E) È stata eseguita l'apertura di visibilità al Pubblico Ministero? [SI/NO]
    # i. Se è stata eseguita l’apertura di visibilità al Pubblico Ministero, quando è stata eseguita? [GG.MM.AAAA/NULL]
    # F) Vi sono stati interventi di terze parti oltre ai ricorrenti, all’Avvocatura dello Stato e al Pubblico Ministero? [SI/NO]
    # i. Se vi sono interventi, quanti sono gli atti di intervento? [Indica il numero in cifre/NULL]
    # ii. Se vi sono interventi, chi sono gli intervenuti? [Indica i loro nomi e cognomi/NULL]
    # iii. Se vi sono interventi, quando è intervenuto ciascuno? [GG.MM.AAAA]
    # G) Qual è l'anno e il numero di ruolo? [NNNN-AAAA]
    def section_2(self):
        indice = self.index.get("indice")
        if not indice:
            return {
                "A": "NULL",
                "B": "NULL",
                "C": "NULL",
                "D": "NULL",
                "Di": "NULL",
                "E": "NULL",
                "Ei": "NULL",
                "F": "NULL",
                "Fi": "NULL",
                "Fii": "NULL",
                "Fiii": "NULL",
                "G": "NULL"
            }
        
        instr = indice.get("schema", {})

        raw_data_iscrizione = instr.get("data_iscrizione", "NULL")
        iscrizione_dt = self.parse_flexible_date(raw_data_iscrizione)
        data_iscrizione = self.format_date(raw_data_iscrizione)

        if iscrizione_dt is None:
            # If an indice exists but the registration date is missing/unparseable,
            # the temporal checks cannot be satisfied and must fail.
            check_post_2023 = "KO"
            check_pre_2025 = "KO"
        else:
            # 2B: dopo il 28.02.2023 incluso
            check_post_2023 = "OK" if iscrizione_dt >= datetime(2023, 2, 28) else "KO"
            # 2C: prima del 27.03.2025 escluso
            check_pre_2025 = "OK" if iscrizione_dt < datetime(2025, 3, 27) else "KO"

        comparsa_avv = self.answer_yes_no(instr.get("comparsa_avvocatura", "NULL"))
        data_comparsa_avv = self.format_date(instr.get("data_comparsa_avvocatura", "NULL")) if comparsa_avv == "SI" else "NULL"
        visibilita_pm = self.answer_yes_no(instr.get("visibilita_pm", "NULL"))
        data_visibilita_pm = self.format_date(instr.get("data_visibilita_pm", "NULL")) if visibilita_pm == "SI" else "NULL"
        interventi_presenti = self.answer_yes_no(instr.get("interventi", "NULL"))
        num_interventi = str(instr.get("numero_interventi", 0)) if interventi_presenti == "SI" else "NULL"
        nomi_intervenuti = ", ".join(self.full_name(person) for person in instr.get("intervenuti", [])) if interventi_presenti == "SI" else "NULL"
        data_intervenuti = ", ".join(self.format_date(person.get("data")) for person in instr.get("intervenuti", [])) if interventi_presenti == "SI" else "NULL"
        ruolo = self.format_ruolo(instr.get("numero_anno_ruolo", "NULL"))

        if check_post_2023 == "KO": self.mark_ko("2B", "Il ricorso non risulta iscritto dopo il 28.02.2023 incluso")
        if check_pre_2025 == "KO": self.mark_ko("2C", "Il ricorso non risulta iscritto prima del 27.03.2025 escluso")

        return {
            "A": data_iscrizione,
            "B": check_post_2023,
            "C": check_pre_2025,
            "D": comparsa_avv,
            "Di": data_comparsa_avv,
            "E": visibilita_pm,
            "Ei": data_visibilita_pm,
            "F": interventi_presenti,
            "Fi": num_interventi,
            "Fii": nomi_intervenuti,
            "Fiii": data_intervenuti,
            "G": ruolo
        }

    # -------------------------------------------------
    # SECTION 3: Ricorso details
    # -------------------------------------------------
    # 3. Individua il RICORSO e rispondi a queste domande:
    # A) Chi è/sono l’avvocato/i? [Indica i loro nomi e cognomi]
    # B) Quanti sono i ricorrenti, ossia coloro che chiedono la cittadinanza italiana? [Indica il numero in cifre]
    # C) Quali sono i ricorrenti? [Indica i loro nomi e cognomi]
    # D) Di quale nazionalità è ciascun ricorrente? [Indica il nome e il cognome di ciascun ricorrente, seguito dalla relativa nazionalità]
    # E) Qualcuno dei ricorrenti è minorenne alla data in cui il ricorso è stato iscritto? [SI/NO]
    # i. Se SI, come si chiama ciascun ricorrente minorenne? [Indica i loro nomi e cognomi/NULL]
    # ii. Se SI, come si chiamano il genitore o i genitori che rappresentano ciascun ricorrente minorenne? [Indica il nome e il cognome di ciascun ricorrente minorenne, seguito da “rappresentato da” / NULL]
    # F) L’albero genealogico indicato nel ricorso è coerente, nel senso che la linea di discendenza esclusivamente retta dall’avo ai ricorrenti, per come descritta nel ricorso, è senza errori/omissioni? [OK/KO; fornisci una breve motivazione alla risposta indicando sinteticamente la linea di discendenza]
    # G) Tutti i ricorrenti avanzano la domanda per discendenza in linea retta dall’avo e non per matrimonio con uno dei discendenti/ricorrenti? [OK/KO; fornisci una breve motivazione alla risposta]
    # i. Se KO, chi chiede la cittadinanza per matrimonio? [Indica il nome e cognome di ciascuno di questi ricorrenti/NULL]
    def section_3(self):
        doc = self.index.get("ricorso")
        if not doc:
            return {"3": "Ricorso non trovato" }
        
        instr = doc["schema"]

        maggiorenni = instr.get("ricorrenti_maggiorenni", [])
        minorenni = instr.get("ricorrenti_minorenni", [])
        all_ricorrenti = maggiorenni + minorenni

        avvocati_list = [f"{a['nome']} {a['cognome']}" for a in instr.get("avvocati", [])]
        a_val = ", ".join(avvocati_list) if avvocati_list else "NULL"
        b_val = len(all_ricorrenti)
        c_val = ", ".join([self.full_name(r) for r in all_ricorrenti]) if all_ricorrenti else "NULL"
        d_val = ", ".join([f"{self.full_name(r)}: {r.get('nazionalita', 'NULL')}" for r in all_ricorrenti]) if all_ricorrenti else "NULL"
        e_val = "SI" if minorenni else "NO"
        e_i_val = ", ".join([self.full_name(r) for r in minorenni]) if minorenni else "NULL"
        e_ii_val = "; ".join([f"{self.full_name(r)} rappresentato da {', '.join([self.full_name(p) for p in r.get('rappresentato_da', [])])}" for r in minorenni]) if minorenni else "NULL"
        linea = self.answer_ok_ko(instr.get("coerenza_linea_discendenza", "NULL"))
        racconto_linea = instr.get("riassunto_linea_discendenza") or instr.get("racconto_linea_discendenza") or self.lineage_summary()
        f_val = f"{linea}; {racconto_linea}"
        per_matrimonio = instr.get("ricorrenti_per_matrimonio", [])
        if not per_matrimonio:
            g_val, g_i_val = "OK; Tutti i ricorrenti avanzano per discendenza in linea retta", "NULL"
        else:
            g_val = "KO; Ricorrenti per matrimonio presenti"
            g_i_val = ", ".join([self.full_name(r) for r in per_matrimonio])

        if linea == "KO":
            self.mark_ko("3F", "La linea di discendenza indicata nel ricorso non risulta coerente")
        if g_val.startswith("KO"):
            self.mark_ko("3G", f"Ricorrenti che chiedono la cittadinanza per matrimonio: {g_i_val}")

        return {
            "A": a_val,
            "B": b_val,
            "C": c_val,
            "D": d_val,
            "E": e_val,
            "Ei": e_i_val,
            "Eii": e_ii_val,
            "F": f_val,
            "G": g_val,
            "Gi": g_i_val
        }

    # -------------------------------------------------
    # SECTION 4: Procure details
    # -------------------------------------------------
    # 4. Ripeti le risposte di questa sezione n. 4 tante volte quanti sono i ricorrenti, anche se più ricorrenti hanno rilasciato una sola procura e anche se si tratta di ricorrenti minorenni. Chiama le sezioni 4/1, 4/2, 4/3, 4/4 e così via fino all’ultimo ricorrente. Individua la singola "PROCURA di [NOME COGNOME] - versione originale". Per ciascun ricorrente controlla quanto segue:
    # A) A quale ricorrente si riferisce la procura? [Indica nome e cognome]
    # i. Se il ricorrente è minorenne, chi lo rappresenta? [Indica nome e cognome/NULL]
    # B) Sull'originale della procura, è presente la firma del ricorrente (o del rappresentante del ricorrente minorenne)? [OK/KO. Fornisci una breve spiegazione di quale firma hai individuato]
    # C) La procura è stata conferita allo/agli stesso/i avvocato/i indicati nel ricorso? (È sufficiente l’indicazione anche di un solo avvocato) [OK/KO]
    # D) Qual è l’oggetto del giudizio indicato nella procura? [Copia l’oggetto del ricorso come risulta dalla procura nella versione originale; non modificare il testo e non riscrivere o tradurre; basta il passaggio contenente frasi come "delego a rappresentarmi nel giudizio per il riconoscimento della cittadinanza italiana"]
    # E) La procura indica che il giudizio sarà proposto dinanzi al Tribunale di Brescia? [OK/NO]
    # i. Se NO, quale Tribunale indica? [Copia il passaggio rilevante della procura nella versione originale; spesso sono presenti formule generiche tipo "Tribunale civile competente"]
    # F) Quando è stata rilasciata la procura? (Indica la data riportata sull'originale della procura) [GG.MM.AAAA]
    # G) La data della procura è anteriore alla data scritta in calce al ricorso? [OK/KO]
    # H) La procura è stata rilasciata in Italia? [OK/NO]
    # i. Se la procura è stata rilasciata all’estero, è presente l’apostille dell'originale della procura? [OK/KO/NULL]
    # I) La procura è scritta in italiano? [OK/NO]
    # i. Se la procura non è scritta in italiano, è presente la traduzione in italiano della procura? [OK/KO/NULL]
    # ii. Se è presente la traduzione in italiano della procura, è stata fatta in Italia? [OK/NO/NULL]
    # iii. Se la traduzione in italiano della procura è stata fatta all’estero, è presente l’apostille della traduzione della procura? [OK/KO/NULL]
    # iv. Se la traduzione in italiano della procura è stata fatta in Italia, è presente l’asseverazione della traduzione della procura? [OK/KO/NULL]
    def section_4(self):
        ricorso = self.index.get("ricorso")
        if not ricorso:
            return {"4": "Ricorso non trovato" }
        
        results = {}
        ricorrenti = self.get_ricorrenti()
        data_ricorso = self.parse_date(ricorso["schema"].get("data_ricorso", "-"))

        for i, ric in enumerate(ricorrenti, 1):
            sec_key = f"4/{i}"
            full_name = self.full_name(ric)
            procura, ric_data = self.find_procura_for_person(ric)
            ric_representatives = ", ".join(self.full_name(person) for person in ric.get("rappresentato_da", [])) or "NULL"
            if not procura:
                results[sec_key] = {
                    "A": full_name,
                    "Ai": ric_representatives if ric.get("rappresentato_da") else "NULL",
                    "B": "KO; Procura non trovata",
                    "C": "KO",
                    "D": "NULL",
                    "E": "NULL",
                    "Ei": "NULL",
                    "F": "NULL",
                    "G": "KO",
                    "H": "NULL",
                    "Hi": "NULL",
                    "I": "NULL",
                    "Ii": "NULL",
                    "Iii": "NULL",
                    "Iiii": "NULL",
                    "Iiv": "NULL"
                }
                self.mark_ko(f"{sec_key}B", f"Procura non trovata per {full_name}")
                self.mark_ko(f"{sec_key}C", f"Impossibile verificare gli avvocati per {full_name} per assenza della procura")
                self.mark_ko(f"{sec_key}G", f"Impossibile verificare l'anteriorità della procura per {full_name} per assenza della procura")
                continue
            instr = procura["schema"]
            data_procura = self.parse_date(instr.get("data_procura", "-"))
            is_minor = self.answer_yes_no(ric_data.get("minorenne", "NO")) == "SI"
            representatives = self.get_representatives(ric_data)
            representative_text = ", ".join(self.full_name(person) for person in representatives) if representatives else (ric_representatives if is_minor else "NULL")
            signature_status = self.answer_ok_ko(ric_data.get("firma_presente", "NULL"))
            if signature_status == "OK":
                signature_reason = f"firma del rappresentante legale {representative_text}" if is_minor else f"firma del ricorrente {full_name}"
            else:
                signature_reason = f"firma non individuata per {full_name}"
            lawyer_status = "OK" if self.same_lawyer(ricorso["schema"].get("avvocati", []), instr.get("avvocati", [])) else "KO"
            tribunal_status = self.answer_ok_no(instr.get("tribunale_brescia_indicato", "NULL"))
            procura_in_italia = self.answer_ok_no(instr.get("rilasciata_in_italia", "NULL"))
            procura_in_italiano = self.answer_ok_no(instr.get("scritta_in_italiano", "NULL"))
            results[sec_key] = {
                "A": full_name,
                "Ai": representative_text if is_minor else "NULL",
                "B": f"{signature_status}; {signature_reason}",
                "C": lawyer_status,
                "D": self.null_value(instr.get("oggetto", "NULL")),
                "E": tribunal_status,
                "Ei": self.null_value(instr.get("tribunale_indicato", "NULL")) if tribunal_status == "NO" else "NULL",
                "F": self.format_date(instr.get("data_procura", "NULL")),
                "G": "OK" if data_ricorso and data_procura and data_procura < data_ricorso else "KO",
                "H": procura_in_italia,
                "Hi": "NULL",
                "I": procura_in_italiano,
                "Ii": "NULL",
                "Iii": "NULL",
                "Iiii": "NULL",
                "Iiv": "NULL",
            }

            if signature_status == "KO":
                self.mark_ko(f"{sec_key}B", f"Firma mancante nella procura di {full_name}")
            if lawyer_status == "KO":
                self.mark_ko(f"{sec_key}C", f"Gli avvocati indicati nella procura di {full_name} non coincidono con quelli del ricorso")
            if results[sec_key]["G"] == "KO":
                self.mark_ko(f"{sec_key}G", f"La data della procura di {full_name} non è anteriore alla data del ricorso")
            
            if procura_in_italia == "NO":
                results[sec_key]["Hi"] = "OK" if self.has_apostille("Procura", ric_data) else "KO"
                if results[sec_key]["Hi"] == "KO":
                    self.mark_ko(f"{sec_key}Hi", f"Apostille mancante per la procura estera di {full_name}")

            if procura_in_italiano == "NO":
                translation = self.find_translation("Procura", ric_data)
                results[sec_key]["Ii"] = "OK" if translation else "KO"
                if results[sec_key]["Ii"] == "KO":
                    self.mark_ko(f"{sec_key}Ii", f"Traduzione italiana mancante per la procura di {full_name}")
                if translation:
                    sede = translation["schema"].get("sede_traduttore")
                    results[sec_key]["Iii"] = "OK" if sede == "Italia" else "NO"
                    if sede == "Estero":
                        results[sec_key]["Iiii"] = "OK" if self.has_apostille("Traduzione", ric_data, source_doc="Procura") else "KO"
                        if results[sec_key]["Iiii"] == "KO":
                            self.mark_ko(f"{sec_key}Iiii", f"Apostille mancante per la traduzione estera della procura di {full_name}")
                    elif sede == "Italia":
                        results[sec_key]["Iiv"] = "OK" if self.has_asseverazione("Traduzione", ric_data, source_doc="Procura") else "KO"
                        if results[sec_key]["Iiv"] == "KO":
                            self.mark_ko(f"{sec_key}Iiv", f"Asseverazione mancante per la traduzione italiana della procura di {full_name}")
        
        return results

    # -------------------------------------------------
    # SECTION 5: AVO birth certificate
    # -------------------------------------------------
    # 5. Individua l’ATTO DI NASCITA DELL’AVO - versione originale e rispondi a queste domande:
    # A) È un certificato anagrafico? [OK/NO]
    # i. Se è un certificato parrocchiale, è presente il timbro della Diocesi? [OK/KO/NULL]
    # C) In quale Comune è nato l’avo? [Indica il Comune]
    # D) Il Comune rientra nelle attuali province di Brescia, Bergamo, Cremona e Mantova? [OK/KO]
    # E) Come si chiamano i genitori dell’avo? [Indica il loro nome e cognome]
    # F) Quando è nato l’avo? [GG.MM.AAAA]
    def section_5(self):
        avo_birth = self.find_avo_birth()
        if not avo_birth:
            return {
                "A": "NULL",
                "Ai": "NULL",
                "C": "NULL",
                "D": "NULL",
                "E": "NULL",
                "F": "NULL"
            }
        instr = avo_birth["schema"]
        tipo = instr.get("tipo", "").lower()
        res = {}
        res["A"] = "OK" if "anagrafico" in tipo else "NO" if "parrocchiale" in tipo else "NULL"
        res["Ai"] = self.answer_ok_ko(instr.get("timbro_diocesi", "NULL")) if res["A"] == "NO" else "NULL"
        res["C"] = instr.get("comune_nascita", "-")
        province_competenti = ["brescia", "bergamo", "cremona", "mantova"]
        res["D"] = "OK" if any(instr.get("provincia", "-") in p for p in province_competenti) else "KO"
        padre = instr.get("padre", {})
        madre = instr.get("madre", {})
        res["E"] = f"Padre: {padre.get('nome','-')} {padre.get('cognome','-')}, Madre: {madre.get('nome','-')} {madre.get('cognome','-')}"
        res["F"] = self.format_date(instr.get("data_nascita", "NULL"))
        if res["D"] == "KO":
            self.mark_ko("5D", "Il comune di nascita dell'avo non rientra nelle province di competenza indicate")
        return res

    # -------------------------------------------------
    # SECTION 6: AVO historical birth/death checks
    # -------------------------------------------------
    # 6. A) L'avo è nato dopo il 17.3.1861 escluso? [OK/NO]
    # i. Se l’avo era nato nelle Province di Mantova parte orientale, Verona, Vicenza, Rovigo, Padova, Venezia, Treviso, Belluno salvo alcuni Comuni, Udine salvo alcuni Comuni, Pordenone, è nato dopo il 19.10.1866 incluso? [OK/NO/NULL]
    # ii. Se l’avo era nato nelle Province di Roma, Latina salvo la parte meridionale, Frosinone salvo la parte meridionale, Viterbo, è nato dopo il 20.9.1870 incluso? [OK/NO/NULL]
    # iii. Se l’avo era nato nelle Province di Trento, Bolzano, Trieste, Gorizia, alcuni Comuni di Belluno, alcuni Comuni di Udine, è nato dopo il 16.7.1920? [OK/NO/NULL]
    # B) Solo hai risposto NO ad almeno una delle quattro domande precedenti, individua l’"ATTO DI MORTE DELL’AVO - versione originale" (non ti confondere con gli atti di morte dei discendenti) e rispondi alle ulteriori domande di questo blocco 6, altrimenti rispondi NULL:
    # C) Quando è morto l’avo? [GG.MM.AAAA]
    # D) L'avo è morto dopo il 17.3.1861 incluso? [OK/KO]
    # i. Se l’avo era nato nelle Province di Mantova parte orientale, Verona, Vicenza, Rovigo, Padova, Venezia, Treviso, Belluno salvo alcuni Comuni, Udine salvo alcuni Comuni, Pordenone, è morto dopo il 19.10.1866 incluso? [OK/KO/NULL]
    # ii. Se l’avo era nato nelle Province di Roma, Latina salvo la parte meridionale, Frosinone salvo la parte meridionale, Viterbo, è morto dopo il 20.9.1870 incluso? [OK/KO/NULL]
    # iii. Se l’avo era nato nelle Province di Trento, Bolzano, Trieste, Gorizia, alcuni Comuni di Belluno, alcuni Comuni di Udine, è morto dopo il 16.7.1920? [OK/KO/NULL]
    # E) È presente l’apostille dell'atto di morte dell'avo? [OK/KO]
    # F) È presente la traduzione in italiano dell'atto di morte dell'avo? [OK/KO] Se la riposta è KO, rispondi NULL alle due domande successive.
    # i. Se la traduzione è stata fatta all’estero, è presente l’apostille della traduzione dell'atto di morte dell'avo? [OK/KO/NULL]
    # ii. Se la traduzione è stata fatta in Italia, è presente l’asseverazione della traduzione dell'atto di morte dell'avo? [OK/KO/NULL]
    def section_6(self):
        res = {
            "A":"NULL","Ai":"NULL","Aii":"NULL","Aiii":"NULL",
            "C":"NULL","D":"NULL","Di":"NULL","Dii":"NULL","Diii":"NULL",
            "E":"NULL","F":"NULL","Fi":"NULL","Fii":"NULL"
        }

        avo_birth = self.find_avo_birth()
        avo_death = self.find_avo_death()

        if not avo_birth:
            return res

        birth_date = self.parse_date(avo_birth["schema"].get("data_nascita"))
        area = avo_birth["schema"].get("area_nascita")

        if birth_date:
            res["A"] = "OK" if birth_date > datetime(1861,3,17) else "NO"
            res["Ai"] = "OK" if area=="B" and birth_date >= datetime(1866,10,19) else ("NULL" if area!="B" else "NO")
            res["Aii"] = "OK" if area=="C" and birth_date >= datetime(1870,9,20) else ("NULL" if area!="C" else "NO")
            res["Aiii"] = "OK" if area=="D" and birth_date > datetime(1920,7,16) else ("NULL" if area!="D" else "NO")
        else:
            return res

        if not self.is_avo_death_required(avo_birth) or not avo_death:
            return res

        death_date = self.parse_date(avo_death["schema"].get("data_decesso"))
        res["C"] = self.format_date(avo_death["schema"].get("data_decesso", "NULL"))

        if death_date:
            res["D"] = "OK" if death_date >= datetime(1861,3,17) else "KO"
            res["Di"] = "OK" if (area=="B" and death_date >= datetime(1866,10,19)) else ("NULL" if area!="B" else "KO")
            res["Dii"] = "OK" if (area=="C" and death_date >= datetime(1870,9,20)) else ("NULL" if area!="C" else "KO")
            res["Diii"] = "OK" if (area=="D" and death_date >= datetime(1920,7,16)) else ("NULL" if area!="D" else "KO")

            for key in ["D", "Di", "Dii", "Diii"]:
                if res[key] == "KO":
                    self.mark_ko(f"6{key}", f"La data di morte dell'avo non soddisfa il controllo {key}")

        res["E"] = "OK" if self.has_apostille("Atto di morte", avo_death["schema"].get("soggetto", {})) else "KO"
        if res["E"] == "KO":
            self.mark_ko("6E", "Apostille dell'atto di morte dell'avo mancante")

        translation = self.find_translation("Atto di morte", avo_death["schema"].get("soggetto", {}))
        res["F"] = "OK" if translation else "KO"
        if res["F"] == "KO":
            self.mark_ko("6F", "Traduzione italiana dell'atto di morte dell'avo mancante")
            return res

        sede = translation["schema"].get("sede_traduttore")
        if sede == "Estero":
            res["Fi"] = "OK" if self.has_apostille("Traduzione", avo_death["schema"].get("soggetto", {}), source_doc="Atto di morte") else "KO"
            if res["Fi"] == "KO":
                self.mark_ko("6Fi", "Apostille della traduzione estera dell'atto di morte dell'avo mancante")
        elif sede == "Italia":
            res["Fii"] = "OK" if self.has_asseverazione("Traduzione", avo_death["schema"].get("soggetto", {}), source_doc="Atto di morte") else "KO"
            if res["Fii"] == "KO":
                self.mark_ko("6Fii", "Asseverazione della traduzione italiana dell'atto di morte dell'avo mancante")

        return res

    # -------------------------------------------------
    # SECTION 7: Naturalization checks
    # -------------------------------------------------
    # 7. Individua il "CERTIFICATO NEGATIVO DI NATURALIZZAZIONE - versione originale" e rispondi a queste domande:
    # A) È presente la formula «não consta, até a presente data, registro de naturalização em nome de [avo], filho de [genitore dell’avo] e de [genitore dell’avo] … nascido em [anno di nascita dell’avo]»? [OK/KO]
    # B) Quali sono gli pseudonimi dell’avo? [Indica gli pseudonimi]
    # C) La data di nascita dell’avo riportata nel Certificato Negativo di Naturalizzazione coincide con quella dell’atto di nascita dell’avo? [OK/KO]
    # D) È presente l’apostille del Certificato Negativo di Naturalizzazione? [OK/KO]
    # E) È presente la traduzione in italiano del Certificato Negativo di Naturalizzazione? [OK/KO] Se la risposta è KO, rispondi NULL alle due domande successive.
    # i. Se la traduzione è stata fatta all’estero, è presente l’apostille della traduzione del Certificato Negativo di Naturalizzazione? [OK/KO/NULL]
    # ii. Se la traduzione è stata fatta in Italia, è presente l’asseverazione della traduzione del Certificato Negativo di Naturalizzazione? [OK/KO/NULL]
    def section_7(self):
        cnn = self.index.get("naturalization")
        if not cnn:
            return {
                "A": "NULL",
                "B": "NULL",
                "C": "NULL",
                "D": "NULL",
                "E": "NULL",
                "Ei": "NULL",
                "Eii": "NULL"
            }
        schema = cnn["schema"]
        
        res={}
        res["A"] = self.answer_ok_ko(schema.get("formula_negativa_presente", "NULL"))
        res["B"] = ', '.join([self.full_name(p) for p in schema.get('pseudonimi', [])]) or "NULL"
        
        avo_birth = self.find_avo_birth()
        birth_date = None
        if avo_birth:
            birth_date = self.parse_date(avo_birth["schema"].get("data_nascita"))
        cnn_birth_date = self.parse_date(schema.get("data_nascita", "-"))

        res["C"] = "OK" if birth_date and cnn_birth_date and birth_date == cnn_birth_date else "KO"

        res["D"] = "OK" if self.has_apostille("Certificato Negativo di Naturalizzazione", schema.get("soggetto", {})) else "KO"
        
        translation = self.find_translation("Certificato Negativo di Naturalizzazione", schema.get("soggetto", {}))
        res["E"] = "OK" if translation else "KO"
        res["Ei"] = "NULL"
        res["Eii"] = "NULL"
        if res["A"] == "KO":
            self.mark_ko("7A", "La formula negativa del certificato di naturalizzazione non è presente")
        if res["C"] == "KO":
            self.mark_ko("7C", "La data di nascita nel certificato di naturalizzazione non coincide con quella dell'atto di nascita dell'avo")
        if res["D"] == "KO":
            self.mark_ko("7D", "Apostille del certificato negativo di naturalizzazione mancante")
        if res["E"] == "KO":
            self.mark_ko("7E", "Traduzione italiana del certificato negativo di naturalizzazione mancante")
        if translation:
            sede = translation["schema"].get("sede_traduttore")
            if sede=="Estero":
                res["Ei"]="OK" if self.has_apostille("Traduzione", schema.get("soggetto", {}), source_doc="Certificato Negativo di Naturalizzazione") else "KO"
                if res["Ei"] =="KO": self.mark_ko("7Ei","Apostille CNN mancante")
            elif sede=="Italia":
                res["Eii"] = "OK" if self.has_asseverazione("Traduzione", schema.get("soggetto", {}), source_doc="Certificato Negativo di Naturalizzazione") else "KO"
                if res["Eii"] == "KO": self.mark_ko("7Eii","Asseverazione CNN mancante")
        
        return res

    # -------------------------------------------------
    # SECTION 8: Descendants’ birth docs
    # -------------------------------------------------
    # 8. Ripeti le risposte di questa sezione n. 8 tante volte quanti sono i discendenti e i ricorrenti. Chiama le sezioni 8/1, 8/2, 8/3, 8/4 e così via fino all’ultimo ricorrente. Individua il singolo "ATTO DI NASCITA di [NOME COGNOME] - versione originale". Per ciascun atto di nascita, rispondi a queste domande:
    # A) A quale discendente/ricorrente si riferisce? [Indica nome e cognome]
    # B) Uno dei due genitori indicati nell'atto di nascita è l’avo o un altro discendente/ricorrente? [OK/KO]
    # C) È presente l’apostille dell'originale dell'atto di nascita? [OK/KO]
    # D) È presente la traduzione in italiano dell'atto di nascita? [OK/KO] Se la risposta è KO, rispondi NULL alle due domande successive.
    # i. Se la traduzione è stata fatta all’estero, è presente l’apostille della traduzione dell'atto di nascita? [OK/KO/NULL]
    # ii. Se la traduzione è stata fatta in Italia, è presente l’asseverazione della traduzione dell'atto di nascita? [OK/KO/NULL]
    def section_8(self):
        results = {}
        lineage = self.get_lineage()
        targets = self.unique_people(lineage[1:] + self.get_ricorrenti())
        family_people = self.unique_people(lineage + self.get_ricorrenti())
        for i, person in enumerate(targets, 1):
            key = f"8/{i}"
            birth = self.find_birth_doc_for_person(person)
            nome = self.full_name(person)
            if not birth:
                results[key] = {
                    "A": nome,
                    "B": "KO",
                    "C": "KO",
                    "D": "KO",
                    "Di": "NULL",
                    "Dii": "NULL"
                }
                self.mark_ko(f"{key}B", f"Atto di nascita non trovato per {nome}")
                self.mark_ko(f"{key}C", f"Impossibile verificare l'apostille dell'atto di nascita di {nome} perché l'atto manca")
                self.mark_ko(f"{key}D", f"Impossibile verificare la traduzione dell'atto di nascita di {nome} perché l'atto manca")
                continue

            schema = birth["schema"]
            soggetto = schema["soggetto"]

            padre = schema.get("padre", {})
            madre = schema.get("madre", {})
            res_b = "OK" if self.person_in_list(padre, family_people) or self.person_in_list(madre, family_people) else "KO"
            if res_b == "KO": self.mark_ko(f"{key}B", f"Genitori non in linea discendenza per {nome}")

            res_c = "OK" if self.has_apostille("Atto di nascita", soggetto) else "KO"
            if res_c == "KO": self.mark_ko(f"{key}C", f"Apostille atto di nascita {nome} mancante")

            translation = self.find_translation("Atto di nascita", soggetto)
            res_d = "OK" if translation else "KO"
            if res_d == "KO": self.mark_ko(f"{key}D", f"Traduzione atto di nascita {nome} mancante")

            res_i, res_ii = "NULL", "NULL"
            if translation:
                sede = translation["schema"]["sede_traduttore"]
                if sede == "Estero":
                    res_i = "OK" if self.has_apostille("Traduzione", soggetto, source_doc="Atto di nascita") else "KO"
                    if res_i =="KO": self.mark_ko(f"{key}Di", f"Apostille atto di nascita {nome} mancante")
                else:
                    res_ii = "OK" if self.has_asseverazione("Traduzione", soggetto, source_doc="Atto di nascita") else "KO"
                    if res_ii =="KO": self.mark_ko(f"{key}Dii", f"Asseverazione atto di nascita {nome} mancante")

            results[key] = {
                "A": nome,
                "B": res_b,
                "C": res_c,
                "D": res_d,
                "Di": res_i,
                "Dii": res_ii
            }
        
        return results

    # -------------------------------------------------
    # RUN ALL
    # -------------------------------------------------
    def run(self):
        report = {}
        report["0"] = self.section_0()
        report["1"] = self.section_1()
        report["2"] = self.section_2()
        report["3"] = self.section_3()
        report["4"] = self.section_4()
        report["5"] = self.section_5()
        report["6"] = self.section_6()
        report["7"] = self.section_7()
        report["8"] = self.section_8()
        # 10. Quali domande hanno riportato la risposta KO? [Elenca le domande/NULL]
        report["10"] = self.ko_list if self.ko_list else None
        # 11. Fornisci una breve spiegazione del perché hai fornito ciascuna risposta KO (non ci interessano le risposte OK, SI, NO, NULL).
        report["11"] = self.ko_reasons if self.ko_reasons else None
        return report
