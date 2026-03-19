import json
import sys
import unittest

from analysis import DocumentValidator

TEST_CASE_1 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Alessandro","cognome":"Manzoni","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Ludovico","cognome":"Ariosto"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"25-06-2024"}}
]""")

TEST_CASE_2 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Giuseppe","cognome":"Verdi"}],"numero_ricorrenti":2,"ricorrenti_maggiorenni":[{"nome":"Alessandro","cognome":"Manzoni","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[{"nome":"Marco","cognome":"Manzoni","nazionalita":"Brasiliana","rappresentato_da":[{"nome":"Anna","cognome":"Ricci"}]}],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Ludovico","cognome":"Ariosto"},{"nome":"Alessandro","cognome":"Manzoni"},{"nome":"Marco","cognome":"Manzoni"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"25-06-2024"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Alessandro","cognome":"Manzoni","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento di cittadinanza italiana","avvocati":[{"nome":"Giuseppe","cognome":"Verdi"}],"tribunale_brescia_indicato":"SI","data_procura":"15-03-2024","rilasciata_in_italia":"OK","scritta_in_italiano":"OK"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Marco","cognome":"Manzoni","minorenne":"SI","rappresentanti_legali":[{"nome":"Anna","cognome":"Ricci"}],"firma_presente":"NO"}],"oggetto":"riconoscimento di cittadinanza italiana","avvocati":[{"nome":"Giuseppe","cognome":"Verdi"}],"tribunale_brescia_indicato":"SI","data_procura":"16-03-2024","rilasciata_in_italia":"OK","scritta_in_italiano":"OK"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Ludovico","cognome":"Ariosto"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Brescia","provincia":"brescia","padre":{"nome":"Dante","cognome":"Alighieri"},"madre":{"nome":"Beatrice","cognome":"Portinari"},"data_nascita":"25-05-1890","area_nascita":"B","stato":"Italia"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Alessandro","cognome":"Manzoni"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"San Paolo","provincia":"altro","padre":{"nome":"Ludovico","cognome":"Ariosto"},"madre":{"nome":"Caterina","cognome":"dei Medici"},"data_nascita":"08-04-1945","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Marco","cognome":"Manzoni"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Rio de Janeiro","provincia":"altro","padre":{"nome":"Alessandro","cognome":"Manzoni"},"madre":{"nome":"Rosalba","cognome":"Carriera"},"data_nascita":"10-07-1970","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Alessandro","cognome":"Manzoni"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Marco","cognome":"Manzoni"}]}}}
]""")

TEST_CASE_3 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Giuseppe","cognome":"Verdi"}],"numero_ricorrenti":2,"ricorrenti_maggiorenni":[{"nome":"Paolo","cognome":"Rossini","nazionalita":"Brasiliana"},{"nome":"Maria","cognome":"Rossini","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Antonio","cognome":"Rossini"},{"nome":"Paolo","cognome":"Rossini"},{"nome":"Maria","cognome":"Rossini"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"10-05-2024"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Paolo","cognome":"Rossini","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento di cittadinanza italiana","avvocati":[{"nome":"Giuseppe","cognome":"Verdi"}],"tribunale_brescia_indicato":"KO","tribunale_indicato":"Salvador","data_procura":"20-02-2024","rilasciata_in_italia":"NO","scritta_in_italiano":"NO"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Maria","cognome":"Rossini","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento di cittadinanza italiana","avvocati":[{"nome":"Giuseppe","cognome":"Verdi"}],"tribunale_brescia_indicato":"NO","tribunale_indicato":"Sao Paulo","data_procura":"22-02-2024","rilasciata_in_italia":"NO","scritta_in_italiano":"NO"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Paolo","cognome":"Rossini"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Maria","cognome":"Rossini"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Paolo","cognome":"Rossini"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Maria","cognome":"Rossini"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Procura","soggetto":[{"nome":"Paolo","cognome":"Rossini"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Procura","soggetto":[{"nome":"Maria","cognome":"Rossini"}]}}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Antonio","cognome":"Rossini"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Bergamo","provincia":"bergamo","padre":{"nome":"Giovanni","cognome":"Rossini"},"madre":{"nome":"Francesca","cognome":"Tasso"},"data_nascita":"12-08-1895","area_nascita":"B","stato":"Italia"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Paolo","cognome":"Rossini"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Brasilia","provincia":"altro","padre":{"nome":"Antonio","cognome":"Rossini"},"madre":{"nome":"Elena","cognome":"Palmieri"},"data_nascita":"03-11-1930","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Maria","cognome":"Rossini"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Rio de Janeiro","provincia":"altro","padre":{"nome":"Antonio","cognome":"Rossini"},"madre":{"nome":"Elena","cognome":"Palmieri"},"data_nascita":"15-06-1935","area_nascita":"E","stato":"Brasile"}}
]""")

TEST_CASE_4 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Francesca","cognome":"Bello"}],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Vittoria","cognome":"Bruno","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Isabella","cognome":"Conti"},{"nome":"Vittoria","cognome":"Bruno"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"03-07-2024"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Vittoria","cognome":"Bruno","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento di cittadinanza italiana","avvocati":[{"nome":"Francesca","cognome":"Bello"}],"tribunale_brescia_indicato":"SI","data_procura":"18-04-2024","rilasciata_in_italia":"OK","scritta_in_italiano":"OK"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Vittoria","cognome":"Bruno"}]}}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Isabella","cognome":"Conti"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Cremona","provincia":"cremona","padre":{"nome":"Giacomo","cognome":"Conti"},"madre":{"nome":"Margherita","cognome":"Sforza"},"data_nascita":"17-03-1900","area_nascita":"B","stato":"Italia"}},
    {"document_type":"Atto di morte","schema":{"soggetto":{"nome":"Isabella","cognome":"Conti"},"data_decesso":"22-11-1985"}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Atto di morte","soggetto":[{"nome":"Isabella","cognome":"Conti"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Atto di morte","soggetto":[{"nome":"Isabella","cognome":"Conti"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Atto di morte","soggetto":[{"nome":"Isabella","cognome":"Conti"}]}}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Isabella","cognome":"Conti"},"pseudonimi":[],"formula_negativa_presente":"OK","data_nascita":"17-03-1900"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Isabella","cognome":"Conti"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Isabella","cognome":"Conti"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","documento_originale":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Isabella","cognome":"Conti"}]}}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Vittoria","cognome":"Bruno"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Sao Paulo","provincia":"altro","padre":{"nome":"Giuseppe","cognome":"Bruno"},"madre":{"nome":"Isabella","cognome":"Conti"},"data_nascita":"09-09-1955","area_nascita":"E","stato":"Brasile"}}
]""")

TEST_CASE_5 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Gerolamo","cognome":"Fortuna","nazionalita":"Italiana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Carlo","cognome":"Fortuna"},{"nome":"Gerolamo","cognome":"Fortuna"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"NO","data_ricorso":"12-06-2024"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Carlo","cognome":"Fortuna"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Mantova","provincia":"mantova","padre":{"nome":"Pietro","cognome":"Fortuna"},"madre":{"nome":"Lucia","cognome":"Mazzucchi"},"data_nascita":"08-02-1850","area_nascita":"B","stato":"Italia"}},
    {"document_type":"Atto di morte","schema":{"soggetto":{"nome":"Carlo","cognome":"Fortuna"},"data_decesso":"15-07-1920"}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Carlo","cognome":"Fortuna"},"pseudonimi":[{"nome":"Charles","cognome":"Fortune"}],"formula_negativa_presente":"OK","data_nascita":"08-02-1850"}}
]""")

TEST_CASE_6 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Giuseppe","cognome":"Verdi"}],"numero_ricorrenti":2,"ricorrenti_maggiorenni":[{"nome":"Francesca","cognome":"Rossi","nazionalita":"Italiana"},{"nome":"Marco","cognome":"Bianchi","nazionalita":"Italiana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[{"nome":"Marco","cognome":"Bianchi"}],"linea_discendenza":[{"nome":"Ludovico","cognome":"Ariosto"},{"nome":"Francesca","cognome":"Rossi"},{"nome":"Marco","cognome":"Bianchi"}],"coerenza_linea_discendenza":"NO","proveniente_dal_brasile":"SI","data_ricorso":"25-06-2024"}}
]""")

TEST_CASE_7 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Laura","cognome":"Neri"}],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Diego","cognome":"Moretti","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Roberto","cognome":"Moretti"},{"nome":"Diego","cognome":"Moretti"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"19-05-2024"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Diego","cognome":"Moretti","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento di cittadinanza italiana","avvocati":[{"nome":"Laura","cognome":"Neri"}],"tribunale_brescia_indicato":"KO","tribunale_indicato":"Bahia","data_procura":"01-03-2024","rilasciata_in_italia":"NO","scritta_in_italiano":"NO"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Diego","cognome":"Moretti"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Diego","cognome":"Moretti"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Roberto","cognome":"Moretti"},"tipo":"parrocchiale","timbro_diocesi":"OK","comune_nascita":"Brescia","provincia":"brescia","padre":{"nome":"Fernando","cognome":"Moretti"},"madre":{"nome":"Adriana","cognome":"Grosoli"},"data_nascita":"14-07-1888","area_nascita":"B","stato":"Italia"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Diego","cognome":"Moretti"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Salvador","provincia":"altro","padre":{"nome":"Roberto","cognome":"Moretti"},"madre":{"nome":"Joana","cognome":"Silva"},"data_nascita":"27-12-1950","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Roberto","cognome":"Moretti"},"pseudonimi":[],"formula_negativa_presente":"OK","data_nascita":"14-07-1888"}}
]""")

TEST_CASE_8 = json.loads("""[
    {"document_type":"IndiceProcedimento.html","schema":{"numero_anno_ruolo":"RG 100/2025","data_iscrizione":"10-01-2025","iscrizione_post_28_02_2023":"OK","iscrizione_pre_27_03_2025":"OK","comparsa_avvocatura":"SI","data_comparsa_avvocatura":"15-01-2025","visibilita_pm":"SI","data_visibilita_pm":"20-01-2025","interventi":"SI","numero_interventi":1,"intervenuti":[{"nome":"Mario","cognome":"Rossi","data":"25-01-2025"}]}},
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Luca","cognome":"Neri"}],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Giulia","cognome":"Bianchi","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Carlo","cognome":"Bianchi"},{"nome":"Giulia","cognome":"Bianchi"}],"racconto_linea_discendenza":"Linea ricostruita dai certificati allegati.","riassunto_linea_discendenza":"Carlo Bianchi -> Giulia Bianchi","coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"05-02-2025"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Giulia","cognome":"Bianchi","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento cittadinanza italiana","avvocati":[{"nome":"Luca","cognome":"Neri"}],"tribunale_brescia_indicato":"SI","tribunale_indicato":"-","data_procura":"10-02-2025","rilasciata_in_italia":"NO","scritta_in_italiano":"NO"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Carlo","cognome":"Bianchi"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Bergamo","provincia":"bergamo","padre":{"nome":"Paolo","cognome":"Bianchi"},"madre":{"nome":"Anna","cognome":"Verdi"},"data_nascita":"12-03-1899","area_nascita":"B","stato":"Italia"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Giulia","cognome":"Bianchi"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Sao Paulo","provincia":"altro","padre":{"nome":"Carlo","cognome":"Bianchi"},"madre":{"nome":"Maria","cognome":"Costa"},"data_nascita":"11-08-1960","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Atto di morte","schema":{"soggetto":{"nome":"Carlo","cognome":"Bianchi"},"data_decesso":"01-05-1978"}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Carlo","cognome":"Bianchi"},"pseudonimi":[{"nome":"Carlos","cognome":"Bianchi"}],"formula_negativa_presente":"OK","data_nascita":"12-03-1899"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Giulia","cognome":"Bianchi"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Giulia","cognome":"Bianchi"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Atto di morte","soggetto":[{"nome":"Carlo","cognome":"Bianchi"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Carlo","cognome":"Bianchi"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Giulia","cognome":"Bianchi"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Giulia","cognome":"Bianchi"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Atto di morte","soggetto":[{"nome":"Carlo","cognome":"Bianchi"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Carlo","cognome":"Bianchi"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Procura","soggetto":[{"nome":"Giulia","cognome":"Bianchi"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Atto di morte","soggetto":[{"nome":"Carlo","cognome":"Bianchi"}]}}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Atto di nascita","soggetto":[{"nome":"Giulia","cognome":"Bianchi"}]}}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Carlo","cognome":"Bianchi"}]}}}
]""")

TEST_CASE_9 = json.loads("""[
    {"document_type":"IndiceProcedimento.html","schema":{"numero_anno_ruolo":"RG 220/2025","data_iscrizione":"14-02-2025","iscrizione_post_28_02_2023":"OK","iscrizione_pre_27_03_2025":"OK","comparsa_avvocatura":"NO","data_comparsa_avvocatura":"-","visibilita_pm":"NO","data_visibilita_pm":"-","interventi":"NO","numero_interventi":0,"intervenuti":[]}},
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Elena","cognome":"Moro"}],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Fabio","cognome":"Leoni","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Pietro","cognome":"Leoni"},{"nome":"Fabio","cognome":"Leoni"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"20-02-2025"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Fabio","cognome":"Leoni","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento cittadinanza italiana","avvocati":[{"nome":"Elena","cognome":"Moro"}],"tribunale_brescia_indicato":"SI","data_procura":"25-02-2025","rilasciata_in_italia":"NO","scritta_in_italiano":"NO"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Procura","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]}}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Pietro","cognome":"Leoni"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Brescia","provincia":"brescia","padre":{"nome":"Lorenzo","cognome":"Leoni"},"madre":{"nome":"Teresa","cognome":"Ferri"},"data_nascita":"08-09-1901","area_nascita":"A","stato":"Italia"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Fabio","cognome":"Leoni"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Rio de Janeiro","provincia":"altro","padre":{"nome":"Pietro","cognome":"Leoni"},"madre":{"nome":"Carla","cognome":"Silva"},"data_nascita":"10-10-1968","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Atto di nascita","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]}}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Pietro","cognome":"Leoni"},"pseudonimi":[],"formula_negativa_presente":"OK","data_nascita":"08-09-1901"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Pietro","cognome":"Leoni"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Pietro","cognome":"Leoni"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Pietro","cognome":"Leoni"}]}}}
]""")

TEST_CASE_10 = json.loads("""[
    {"document_type":"IndiceProcedimento.html","schema":{"numero_anno_ruolo":"RG 301/2025","data_iscrizione":"01-03-2025","iscrizione_post_28_02_2023":"OK","iscrizione_pre_27_03_2025":"KO","comparsa_avvocatura":"SI","data_comparsa_avvocatura":"05-03-2025","visibilita_pm":"SI","data_visibilita_pm":"06-03-2025","interventi":"SI","numero_interventi":2,"intervenuti":[{"nome":"Chiara","cognome":"Gallo","data":"07-03-2025"},{"nome":"Paolo","cognome":"Gallo","data":"08-03-2025"}]}},
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Sara","cognome":"Blu"}],"numero_ricorrenti":2,"ricorrenti_maggiorenni":[{"nome":"Paolo","cognome":"Gallo","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[{"nome":"Lia","cognome":"Gallo","nazionalita":"Brasiliana","rappresentato_da":[{"nome":"Paolo","cognome":"Gallo"}]}],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Enrico","cognome":"Gallo"},{"nome":"Paolo","cognome":"Gallo"},{"nome":"Lia","cognome":"Gallo"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"10-03-2025"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Paolo","cognome":"Gallo","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento cittadinanza italiana","avvocati":[{"nome":"Sara","cognome":"Blu"}],"tribunale_brescia_indicato":"SI","data_procura":"12-03-2025","rilasciata_in_italia":"NO","scritta_in_italiano":"NO"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Lia","cognome":"Gallo","minorenne":"SI","rappresentanti_legali":[{"nome":"Paolo","cognome":"Gallo"}],"firma_presente":"NO"}],"oggetto":"riconoscimento cittadinanza italiana","avvocati":[{"nome":"Sara","cognome":"Blu"}],"tribunale_brescia_indicato":"SI","data_procura":"12-03-2025","rilasciata_in_italia":"NO","scritta_in_italiano":"NO"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Paolo","cognome":"Gallo"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Lia","cognome":"Gallo"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Paolo","cognome":"Gallo"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Lia","cognome":"Gallo"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Procura","soggetto":[{"nome":"Paolo","cognome":"Gallo"}]}}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Procura","soggetto":[{"nome":"Lia","cognome":"Gallo"}]}}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Enrico","cognome":"Gallo"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Cremona","provincia":"cremona","padre":{"nome":"Mario","cognome":"Gallo"},"madre":{"nome":"Giulia","cognome":"Riva"},"data_nascita":"20-04-1902","area_nascita":"A","stato":"Italia"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Paolo","cognome":"Gallo"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Brasilia","provincia":"altro","padre":{"nome":"Enrico","cognome":"Gallo"},"madre":{"nome":"Lucia","cognome":"Nunes"},"data_nascita":"14-01-1965","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Lia","cognome":"Gallo"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Brasilia","provincia":"altro","padre":{"nome":"Paolo","cognome":"Gallo"},"madre":{"nome":"Marina","cognome":"Souza"},"data_nascita":"18-06-2009","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Paolo","cognome":"Gallo"}]}}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Lia","cognome":"Gallo"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Paolo","cognome":"Gallo"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Lia","cognome":"Gallo"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Atto di nascita","soggetto":[{"nome":"Paolo","cognome":"Gallo"}]}}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Atto di nascita","soggetto":[{"nome":"Lia","cognome":"Gallo"}]}}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Enrico","cognome":"Gallo"},"pseudonimi":[{"nome":"Henrique","cognome":"Gallo"}],"formula_negativa_presente":"OK","data_nascita":"20-04-1902"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Enrico","cognome":"Gallo"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Enrico","cognome":"Gallo"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Enrico","cognome":"Gallo"}]}}}
]""")

TEST_CASE_11 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Luca","cognome":"Seri"}],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Gianni","cognome":"Verdi","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Pietro","cognome":"Verdi"},{"nome":"Mario","cognome":"Verdi"},{"nome":"Gianni","cognome":"Verdi"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"21-02-2025"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Gianni","cognome":"Verdi","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento cittadinanza italiana","avvocati":[{"nome":"Luca","cognome":"Seri"}],"tribunale_brescia_indicato":"SI","data_procura":"10-02-2025","rilasciata_in_italia":"OK","scritta_in_italiano":"OK"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Pietro","cognome":"Verdi"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Brescia","provincia":"brescia","padre":{"nome":"Luigi","cognome":"Verdi"},"madre":{"nome":"Anna","cognome":"Bianchi"},"data_nascita":"10-10-1900","area_nascita":"A","stato":"Italia"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Gianni","cognome":"Verdi"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Sao Paulo","provincia":"altro","padre":{"nome":"Mario","cognome":"Verdi"},"madre":{"nome":"Carla","cognome":"Rossi"},"data_nascita":"09-09-1970","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Pietro","cognome":"Verdi"},"pseudonimi":[],"formula_negativa_presente":"OK","data_nascita":"10-10-1900"}}
]""")

TEST_CASE_12 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Laura","cognome":"Neri"}],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Diego","cognome":"Moretti","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Roberto","cognome":"Moretti"},{"nome":"Diego","cognome":"Moretti"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"19-05-2024"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Diego","cognome":"Moretti","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento di cittadinanza italiana","avvocati":[{"nome":"Laura","cognome":"Neri"}],"tribunale_brescia_indicato":"KO","tribunale_indicato":"Bahia","data_procura":"01-03-2024","rilasciata_in_italia":"NO","scritta_in_italiano":"NO"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Diego","cognome":"Moretti"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Diego","cognome":"Moretti"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Roberto","cognome":"Moretti"},"tipo":"parrocchiale","timbro_diocesi":"OK","comune_nascita":"Brescia","provincia":"brescia","padre":{"nome":"Fernando","cognome":"Moretti"},"madre":{"nome":"Adriana","cognome":"Grosoli"},"data_nascita":"14-07-1888","area_nascita":"B","stato":"Italia"}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Roberto","cognome":"Moretti"},"pseudonimi":[],"formula_negativa_presente":"OK","data_nascita":"14-07-1888"}}
]""")

TEST_CASE_13 = json.loads("""[
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Elena","cognome":"Moro"}],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Fabio","cognome":"Leoni","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Pietro","cognome":"Leoni"},{"nome":"Fabio","cognome":"Leoni"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"20-02-2025"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Fabio","cognome":"Leoni","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento cittadinanza italiana","avvocati":[{"nome":"Elena","cognome":"Moro"}],"tribunale_brescia_indicato":"SI","data_procura":"10-02-2025","rilasciata_in_italia":"NO","scritta_in_italiano":"NO"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Procura","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Procura","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]}}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Pietro","cognome":"Leoni"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Brescia","provincia":"brescia","padre":{"nome":"Lorenzo","cognome":"Leoni"},"madre":{"nome":"Teresa","cognome":"Ferri"},"data_nascita":"08-09-1901","area_nascita":"A","stato":"Italia"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Fabio","cognome":"Leoni"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Rio de Janeiro","provincia":"altro","padre":{"nome":"Pietro","cognome":"Leoni"},"madre":{"nome":"Carla","cognome":"Silva"},"data_nascita":"10-10-1968","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]},"sede_traduttore":"Estero"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Atto di nascita","soggetto":[{"nome":"Fabio","cognome":"Leoni"}]}}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Pietro","cognome":"Leoni"},"pseudonimi":[],"formula_negativa_presente":"OK","data_nascita":"08-09-1901"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Pietro","cognome":"Leoni"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Pietro","cognome":"Leoni"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Pietro","cognome":"Leoni"}]}}}
]""")

TEST_CASE_14 = json.loads("""[
    {"document_type":"IndiceProcedimento.html","schema":{"numero_anno_ruolo":"RG 415/2025","data_iscrizione":"15-02-2025","iscrizione_post_28_02_2023":"OK","iscrizione_pre_27_03_2025":"OK","comparsa_avvocatura":"NO","data_comparsa_avvocatura":"-","visibilita_pm":"NO","data_visibilita_pm":"-","interventi":"NO","numero_interventi":0,"intervenuti":[]}},
    {"document_type":"Ricorso","schema":{"avvocati":[{"nome":"Marta","cognome":"Bassi"}],"numero_ricorrenti":1,"ricorrenti_maggiorenni":[{"nome":"Luca","cognome":"Gatti","nazionalita":"Brasiliana"}],"ricorrenti_minorenni":[],"ricorrenti_per_matrimonio":[],"linea_discendenza":[{"nome":"Carlo","cognome":"Gatti"},{"nome":"Luca","cognome":"Gatti"}],"coerenza_linea_discendenza":"SI","proveniente_dal_brasile":"SI","data_ricorso":"20-02-2025"}},
    {"document_type":"Procura","schema":{"soggetto":[{"nome":"Luca","cognome":"Gatti","minorenne":"NO","rappresentanti_legali":[],"firma_presente":"OK"}],"oggetto":"riconoscimento cittadinanza italiana","avvocati":[{"nome":"Marta","cognome":"Bassi"}],"tribunale_brescia_indicato":"SI","data_procura":"10-02-2025","rilasciata_in_italia":"OK","scritta_in_italiano":"OK"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Carlo","cognome":"Gatti"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Brescia","provincia":"brescia","padre":{"nome":"Giovanni","cognome":"Gatti"},"madre":{"nome":"Anna","cognome":"Riva"},"data_nascita":"05-03-1902","area_nascita":"A","stato":"Italia"}},
    {"document_type":"Atto di nascita","schema":{"soggetto":{"nome":"Luca","cognome":"Gatti"},"tipo":"anagrafico","timbro_diocesi":"NO","comune_nascita":"Sao Paulo","provincia":"altro","padre":{"nome":"Carlo","cognome":"Gatti"},"madre":{"nome":"Maria","cognome":"Silva"},"data_nascita":"11-07-1975","area_nascita":"E","stato":"Brasile"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Luca","cognome":"Gatti"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Atto di nascita","soggetto":[{"nome":"Luca","cognome":"Gatti"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Atto di nascita","soggetto":[{"nome":"Luca","cognome":"Gatti"}]}}},
    {"document_type":"Certificato Negativo di Naturalizzazione","schema":{"soggetto":{"nome":"Carlo","cognome":"Gatti"},"pseudonimi":[],"formula_negativa_presente":"OK","data_nascita":"05-03-1902"}},
    {"document_type":"Apostille","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Carlo","cognome":"Gatti"}]}}},
    {"document_type":"Traduzione","schema":{"oggetto":{"document_type":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Carlo","cognome":"Gatti"}]},"sede_traduttore":"Italia"}},
    {"document_type":"Asseverazione","schema":{"oggetto":{"document_type":"Traduzione","documento_originale":"Certificato Negativo di Naturalizzazione","soggetto":[{"nome":"Carlo","cognome":"Gatti"}]}}}
]""")

SCENARIOS = {
    "test_case_1": TEST_CASE_1,
    "test_case_2": TEST_CASE_2,
    "test_case_3": TEST_CASE_3,
    "test_case_4": TEST_CASE_4,
    "test_case_5": TEST_CASE_5,
    "test_case_6": TEST_CASE_6,
    "test_case_7": TEST_CASE_7,
    "test_case_8": TEST_CASE_8,
    "test_case_9": TEST_CASE_9,
    "test_case_10": TEST_CASE_10,
    "test_case_11": TEST_CASE_11,
    "test_case_12": TEST_CASE_12,
    "test_case_13": TEST_CASE_13,
    "test_case_14": TEST_CASE_14,
}


def run_validator(test_data):
    return DocumentValidator(test_data).run()


def print_complete_results(scenario, indent=2):
    if isinstance(scenario, str):
        if scenario not in SCENARIOS:
            available = ", ".join(sorted(SCENARIOS))
            raise KeyError(f"Unknown scenario '{scenario}'. Available scenarios: {available}")
        test_data = SCENARIOS[scenario]
    else:
        test_data = scenario

    report = run_validator(test_data)
    print(json.dumps(report, indent=indent, ensure_ascii=False))
    return report


class DocumentValidatorTests(unittest.TestCase):
    def test_missing_sections_use_checklist_shape(self):
        report = run_validator(TEST_CASE_1)

        self.assertEqual(report["1"]["1"], "OK")
        self.assertEqual(report["2"], {
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
            "G": "NULL",
        })
        self.assertEqual(report["5"], {
            "A": "NULL",
            "Ai": "NULL",
            "C": "NULL",
            "D": "NULL",
            "E": "NULL",
            "F": "NULL",
        })
        self.assertEqual(report["6"], {
            "A": "NULL",
            "Ai": "NULL",
            "Aii": "NULL",
            "Aiii": "NULL",
            "C": "NULL",
            "D": "NULL",
            "Di": "NULL",
            "Dii": "NULL",
            "Diii": "NULL",
            "E": "NULL",
            "F": "NULL",
            "Fi": "NULL",
            "Fii": "NULL",
        })
        self.assertEqual(report["7"], {
            "A": "NULL",
            "B": "NULL",
            "C": "NULL",
            "D": "NULL",
            "E": "NULL",
            "Ei": "NULL",
            "Eii": "NULL",
        })

    def test_minor_procura_uses_representatives_and_flags_missing_signature(self):
        report = run_validator(TEST_CASE_2)

        self.assertEqual(report["4"]["4/2"]["Ai"], "Anna Ricci")
        self.assertTrue(report["4"]["4/2"]["B"].startswith("KO;"))
        self.assertIn("4/2B", report["10"])

    def test_foreign_procure_translation_chain(self):
        report = run_validator(TEST_CASE_3)

        self.assertEqual(report["4"]["4/1"]["E"], "NO")
        self.assertEqual(report["4"]["4/1"]["Hi"], "OK")
        self.assertEqual(report["4"]["4/1"]["Ii"], "OK")
        self.assertEqual(report["4"]["4/1"]["Iii"], "NO")
        self.assertEqual(report["4"]["4/1"]["Iiii"], "OK")

    def test_cnn_italian_translation_uses_asseverazione_slot(self):
        report = run_validator(TEST_CASE_4)

        self.assertEqual(report["7"]["E"], "OK")
        self.assertEqual(report["7"]["Ei"], "NULL")
        self.assertEqual(report["7"]["Eii"], "KO")
        self.assertIn("7Eii", report["10"])

    def test_historical_birth_before_1861_triggers_death_checks(self):
        report = run_validator(TEST_CASE_5)

        self.assertEqual(report["1"]["1"], "KO")
        self.assertEqual(report["6"]["A"], "NO")
        self.assertEqual(report["6"]["Ai"], "NO")
        self.assertEqual(report["6"]["C"], "15.07.1920")
        self.assertEqual(report["6"]["D"], "OK")

    def test_matrimony_and_lineage_generate_distinct_kos(self):
        report = run_validator(TEST_CASE_6)

        self.assertTrue(report["3"]["F"].startswith("KO;"))
        self.assertTrue(report["3"]["G"].startswith("KO;"))
        self.assertIn("3F", report["10"])
        self.assertIn("3G", report["10"])

    def test_missing_translation_apostille_is_tracked(self):
        report = run_validator(TEST_CASE_7)

        self.assertEqual(report["4"]["4/1"]["Hi"], "OK")
        self.assertEqual(report["4"]["4/1"]["Iiii"], "KO")
        self.assertIn("4/1Iiii", report["10"])

    def test_full_dossier_formats_index_and_translation_paths(self):
        report = run_validator(TEST_CASE_8)

        self.assertEqual(report["2"]["A"], "10.01.2025")
        self.assertEqual(report["2"]["G"], "0100-2025")
        self.assertEqual(report["4"]["4/1"]["Iiii"], "OK")
        self.assertEqual(report["8"]["8/1"]["Dii"], "OK")

    def test_procura_translation_in_italy_uses_iiv(self):
        report = run_validator(TEST_CASE_9)

        self.assertEqual(report["4"]["4/1"]["Iii"], "OK")
        self.assertEqual(report["4"]["4/1"]["Iiv"], "OK")
        self.assertEqual(report["7"]["Eii"], "OK")

    def test_index_ko_and_minor_signature_are_tracked(self):
        report = run_validator(TEST_CASE_10)

        self.assertEqual(report["2"]["C"], "KO")
        self.assertIn("2C", report["10"])
        self.assertTrue(report["4"]["4/2"]["B"].startswith("KO;"))
        self.assertEqual(report["4"]["4/2"]["Ai"], "Paolo Gallo")

    def test_section_0_separates_descendants_from_ricorrenti(self):
        report = run_validator(TEST_CASE_11)

        self.assertEqual(report["0"]["G"], "KO")
        self.assertEqual(report["0"]["Gi"], "Mario Verdi")
        self.assertEqual(report["0"]["H"], "OK")
        self.assertEqual(report["0"]["Hi"], "NULL")
        self.assertIn("0G", report["10"])
        self.assertNotIn("0H", report["10"])

    def test_section_5_parrocchiale_birth_uses_diocesi_check(self):
        report = run_validator(TEST_CASE_7)

        self.assertEqual(report["5"]["A"], "NO")
        self.assertEqual(report["5"]["Ai"], "OK")

    def test_section_8_missing_birth_still_creates_entry(self):
        report = run_validator(TEST_CASE_12)

        self.assertEqual(report["0"]["H"], "KO")
        self.assertEqual(report["8"]["8/1"]["A"], "Diego Moretti")
        self.assertEqual(report["8"]["8/1"]["B"], "KO")
        self.assertEqual(report["8"]["8/1"]["C"], "KO")
        self.assertEqual(report["8"]["8/1"]["D"], "KO")
        self.assertIn("8/1B", report["10"])

    def test_procura_date_earlier_than_ricorso_is_ok(self):
        report = run_validator(TEST_CASE_13)

        self.assertEqual(report["4"]["4/1"]["G"], "OK")
        self.assertNotIn("4/1G", report["10"])

    def test_golden_scenario_has_no_kos(self):
        report = run_validator(TEST_CASE_14)

        self.assertIn("10", report)
        self.assertEqual(report["10"], None)
        self.assertEqual(report["11"], None)


if __name__ == "__main__":
    #if len(sys.argv) >= 3 and sys.argv[1] == "--print":
    #    print_complete_results(sys.argv[2])
    #else:
    unittest.main()
    #print_complete_results("test_case_14")