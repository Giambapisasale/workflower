"""Dati d'esempio per ``make seed``: 3 cantieri, 8 fornitori, 5 fatture validate.

Gli importi rispettano sempre totale = imponibile + IVA (regola del workflow M2);
FT-2026-0004 è la fattura di un professionista con ritenuta d'acconto in calce.
"""

from typing import Any

CANTIERI: list[dict[str, Any]] = [
    {
        "id": "CNT-001",
        "dati": {
            "nome": "Residenza Le Palme",
            "indirizzo": "Via delle Palme 12",
            "comune": "Catania",
            "provincia": "CT",
            "committente": "Immobiliare Mediterranea S.r.l.",
            "budget": 1850000.0,
            "data_inizio": "2026-01-12",
            "data_fine_prevista": "2027-06-30",
            "capocantiere": "Salvo Torrisi",
        },
    },
    {
        "id": "CNT-002",
        "dati": {
            "nome": "Ristrutturazione Scuola Manzoni",
            "indirizzo": "Via Alessandro Manzoni 3",
            "comune": "Acireale",
            "provincia": "CT",
            "committente": "Comune di Acireale",
            "budget": 640000.0,
            "data_inizio": "2026-03-02",
            "data_fine_prevista": "2026-12-20",
            "capocantiere": "Giuseppe Leotta",
        },
    },
    {
        "id": "CNT-003",
        "dati": {
            "nome": "Capannone logistico Etna Sud",
            "indirizzo": "Zona Industriale, Blocco Palma I",
            "comune": "Misterbianco",
            "provincia": "CT",
            "committente": "LogiSud S.p.A.",
            "budget": 2300000.0,
            "data_inizio": "2026-02-16",
            "data_fine_prevista": "2027-02-28",
            "capocantiere": "Marco Finocchiaro",
        },
    },
]

FORNITORI: list[dict[str, Any]] = [
    {
        "id": "FRN-001",
        "dati": {
            "ragione_sociale": "Calcestruzzi Etna S.p.A.",
            "partita_iva": "04811230871",
            "categoria": "calcestruzzi",
            "comune": "Catania",
            "indirizzo": "Contrada Torre Allegra 8",
            "pec": "calcestruzzietna@pec.it",
            "telefono": "095 7481122",
        },
    },
    {
        "id": "FRN-002",
        "dati": {
            "ragione_sociale": "Edil Sud S.r.l.",
            "partita_iva": "03502180872",
            "categoria": "materiali edili",
            "comune": "Misterbianco",
            "indirizzo": "Via Garibaldi 210",
            "pec": "edilsud@pec.it",
            "telefono": "095 3921540",
        },
    },
    {
        "id": "FRN-003",
        "dati": {
            "ragione_sociale": "Ferramenta Russo & Figli S.n.c.",
            "partita_iva": "02918440873",
            "categoria": "ferramenta",
            "comune": "Acireale",
            "indirizzo": "Corso Umberto 45",
            "pec": "ferramentarusso@pec.it",
            "telefono": "095 6042218",
        },
    },
    {
        "id": "FRN-004",
        "dati": {
            "ragione_sociale": "Impianti Elettrici Marino S.r.l.",
            "partita_iva": "04102650878",
            "categoria": "impianti elettrici",
            "comune": "Catania",
            "indirizzo": "Via Etnea 388",
            "pec": "impiantimarino@pec.it",
            "telefono": "095 5511903",
        },
    },
    {
        "id": "FRN-005",
        "dati": {
            "ragione_sociale": "Termoidraulica La Rosa S.r.l.",
            "partita_iva": "03775210875",
            "categoria": "impianti idraulici",
            "comune": "San Giovanni la Punta",
            "indirizzo": "Via della Regione 27",
            "pec": "termolarosa@pec.it",
            "telefono": "095 7412286",
        },
    },
    {
        "id": "FRN-006",
        "dati": {
            "ragione_sociale": "Sicilia Noleggi S.r.l.",
            "partita_iva": "04455670879",
            "categoria": "noleggio mezzi",
            "comune": "Belpasso",
            "indirizzo": "SS 121 km 8,400",
            "pec": "sicilianoleggi@pec.it",
            "telefono": "095 9134070",
        },
    },
    {
        "id": "FRN-007",
        "dati": {
            "ragione_sociale": "Studio Tecnico Ing. Bianchi",
            "partita_iva": "02644330877",
            "categoria": "servizi di ingegneria",
            "comune": "Catania",
            "indirizzo": "Piazza Verga 6",
            "pec": "ing.bianchi@pec.it",
            "telefono": "095 4470315",
        },
    },
    {
        "id": "FRN-008",
        "dati": {
            "ragione_sociale": "Movimento Terra Grasso S.r.l.",
            "partita_iva": "03288910870",
            "categoria": "scavi e movimento terra",
            "comune": "Paternò",
            "indirizzo": "Via Vittorio Emanuele 152",
            "pec": "mtgrasso@pec.it",
            "telefono": "095 6231448",
        },
    },
]

FATTURE: list[dict[str, Any]] = [
    {
        "id": "FT-2026-0001",
        "dati": {
            "fornitore_id": "FRN-001",
            "cantiere_id": "CNT-001",
            "numero": "126/2026",
            "data": "2026-02-10",
            "imponibile": 8330.00,
            "iva": 1832.60,
            "totale": 10162.60,
            "ritenuta_acconto": None,
            "righe": [
                {
                    "descrizione": "Calcestruzzo C25/30 XC2 pompato",
                    "quantita": 85,
                    "unita_misura": "m3",
                    "importo": 8330.00,
                    "voce_computo_id": "VC1-02",
                }
            ],
        },
    },
    {
        "id": "FT-2026-0002",
        "dati": {
            "fornitore_id": "FRN-002",
            "cantiere_id": "CNT-002",
            "numero": "88/E",
            "data": "2026-03-18",
            "imponibile": 5718.00,
            "iva": 571.80,
            "totale": 6289.80,
            "ritenuta_acconto": None,
            "righe": [
                {
                    "descrizione": "Blocchi Poroton P800 25x30x19",
                    "quantita": 420,
                    "unita_misura": "pz",
                    "importo": 5250.00,
                    "voce_computo_id": "VC2-02",
                },
                {
                    "descrizione": "Malta premiscelata M10",
                    "quantita": 60,
                    "unita_misura": "sacco",
                    "importo": 468.00,
                    "voce_computo_id": "VC2-02",
                },
            ],
        },
    },
    {
        "id": "FT-2026-0003",
        "dati": {
            "fornitore_id": "FRN-006",
            "cantiere_id": "CNT-003",
            "numero": "N-2026-214",
            "data": "2026-04-07",
            "imponibile": 6840.00,
            "iva": 1504.80,
            "totale": 8344.80,
            "ritenuta_acconto": None,
            "righe": [
                {
                    "descrizione": "Nolo escavatore cingolato 20 t con operatore",
                    "quantita": 72,
                    "unita_misura": "h",
                    "importo": 6840.00,
                    "voce_computo_id": None,
                }
            ],
        },
    },
    {
        "id": "FT-2026-0004",
        "dati": {
            "fornitore_id": "FRN-007",
            "cantiere_id": "CNT-001",
            "numero": "07/2026",
            "data": "2026-05-12",
            "imponibile": 4000.00,
            "iva": 880.00,
            "totale": 4880.00,
            "ritenuta_acconto": 800.00,
            "righe": [
                {
                    "descrizione": "Direzione lavori strutture — acconto",
                    "quantita": None,
                    "unita_misura": None,
                    "importo": 4000.00,
                    "voce_computo_id": "VC1-06",
                }
            ],
        },
    },
    {
        "id": "FT-2026-0005",
        "dati": {
            "fornitore_id": "FRN-004",
            "cantiere_id": "CNT-002",
            "numero": "205/26",
            "data": "2026-06-25",
            "imponibile": 2362.00,
            "iva": 519.64,
            "totale": 2881.64,
            "ritenuta_acconto": None,
            "righe": [
                {
                    "descrizione": "Cavo FG16OR16 3G2,5 mmq",
                    "quantita": 500,
                    "unita_misura": "m",
                    "importo": 710.00,
                    "voce_computo_id": "VC2-04",
                },
                {
                    "descrizione": "Quadro elettrico di cantiere ASC",
                    "quantita": 1,
                    "unita_misura": "pz",
                    "importo": 980.00,
                    "voce_computo_id": "VC2-04",
                },
                {
                    "descrizione": "Manodopera elettricista",
                    "quantita": 24,
                    "unita_misura": "h",
                    "importo": 672.00,
                    "voce_computo_id": "VC2-04",
                },
            ],
        },
    },
]

DDT: list[dict[str, Any]] = [
    {
        "id": "DDT-2026-0001",
        "dati": {
            "fornitore_id": "FRN-002",
            "cantiere_id": "CNT-002",
            "numero": "445/T",
            "data": "2026-03-16",
            "causale": "Vendita",
            "riferimento_ordine": "ODA-2026-071",
            "righe": [
                {
                    "descrizione": "Blocchi Poroton P800 25x30x19",
                    "quantita": 420,
                    "unita_misura": "pz",
                    "voce_computo_id": None,
                },
                {
                    "descrizione": "Malta premiscelata M10",
                    "quantita": 60,
                    "unita_misura": "sacco",
                    "voce_computo_id": None,
                },
            ],
        },
    },
    {
        "id": "DDT-2026-0002",
        "dati": {
            "fornitore_id": "FRN-001",
            "cantiere_id": "CNT-001",
            "numero": "1120/26",
            "data": "2026-02-09",
            "causale": "Vendita",
            "riferimento_ordine": None,
            "righe": [
                {
                    "descrizione": "Calcestruzzo C25/30 XC2",
                    "quantita": 85,
                    "unita_misura": "m3",
                    "voce_computo_id": None,
                }
            ],
        },
    },
]

SAL: list[dict[str, Any]] = [
    {
        "id": "SAL-2026-0001",
        "dati": {
            "cantiere_id": "CNT-001",
            "numero": "3",
            "data": "2026-06-30",
            "importo_lavori": 1720000.00,
            "importo_progressivo": 561000.00,
            "percentuale_avanzamento": 32.6,
        },
    },
    {
        "id": "SAL-2026-0002",
        "dati": {
            "cantiere_id": "CNT-003",
            "numero": "2",
            "data": "2026-05-31",
            "importo_lavori": 1980000.00,
            "importo_progressivo": 445000.00,
            "percentuale_avanzamento": 22.5,
        },
    },
]

def _ora(nominativo: str, mansione: str, ore: float, costo: float) -> dict[str, Any]:
    """Una riga di rapportino, per tenere il seed compatto e leggibile."""
    return {"nominativo": nominativo, "mansione": mansione, "ore": ore, "costo_orario": costo}


RAPPORTINI: list[dict[str, Any]] = [
    {
        "id": "RAP-2026-0001",
        "dati": {
            "cantiere_id": "CNT-001",
            "data": "2026-07-14",
            "righe": [
                _ora("Salvo Torrisi", "Capocantiere", 8, 32.0),
                _ora("Mario Rossi", "Muratore", 8, 26.5),
                _ora("Antonio Greco", "Manovale", 8, 22.0),
            ],
        },
    },
    {
        "id": "RAP-2026-0002",
        "dati": {
            "cantiere_id": "CNT-002",
            "data": "2026-07-15",
            "righe": [
                _ora("Giuseppe Leotta", "Capocantiere", 8, 30.0),
                _ora("Squadra edile", "Muratura", 16, 24.0),
            ],
        },
    },
]

def _voce(
    id: str, codice: str, descrizione: str, um: str | None, quantita: float,
    prezzo: float, categoria: str,
) -> dict[str, Any]:
    """Una voce di computo; l'importo previsto è quantità × prezzo unitario."""
    return {
        "id": id,
        "codice": codice,
        "descrizione": descrizione,
        "unita_misura": um,
        "quantita": quantita,
        "prezzo_unitario": prezzo,
        "importo": round(quantita * prezzo, 2),
        "categoria": categoria,
    }


COMPUTI: list[dict[str, Any]] = [
    {
        "id": "CMP-001",
        "dati": {
            "cantiere_id": "CNT-001",
            "descrizione": "Computo metrico estimativo — Residenza Le Palme",
            "voci": [
                _voce("VC1-01", "A.01", "Scavo di sbancamento e splateamento",
                      "m3", 1200, 8.50, "scavi"),
                _voce("VC1-02", "B.01", "Calcestruzzo strutturale C25/30 in opera",
                      "m3", 320, 128.00, "strutture"),
                _voce("VC1-03", "B.02", "Acciaio per c.a. B450C",
                      "kg", 28000, 1.35, "strutture"),
                _voce("VC1-04", "C.01", "Muratura di tamponamento in blocchi",
                      "m2", 850, 42.00, "murature"),
                _voce("VC1-05", "D.01", "Impianto elettrico civile",
                      "a corpo", 1, 68000.00, "impianti"),
                _voce("VC1-06", "E.01", "Direzione lavori e coordinamento sicurezza",
                      "a corpo", 1, 45000.00, "tecnici"),
            ],
        },
    },
    {
        "id": "CMP-002",
        "dati": {
            "cantiere_id": "CNT-002",
            "descrizione": "Computo metrico estimativo — Scuola Manzoni",
            "voci": [
                _voce("VC2-01", "A.01", "Demolizioni e rimozioni",
                      "a corpo", 1, 42000.00, "demolizioni"),
                _voce("VC2-02", "C.01", "Murature e tramezzature interne",
                      "m2", 620, 38.00, "murature"),
                _voce("VC2-03", "F.01", "Intonaci e finiture",
                      "m2", 1100, 22.00, "finiture"),
                _voce("VC2-04", "D.01", "Impianti elettrici e speciali",
                      "a corpo", 1, 95000.00, "impianti"),
            ],
        },
    },
]

# Utenti demo (data/config/utenti.json): i capocantiere del seed + l'ufficio.
# I PIN sono dimostrativi e finiscono nel repo dati solo come hash PBKDF2.
UTENTI: list[dict[str, Any]] = [
    {
        "username": "salvo",
        "nome": "Salvo Torrisi",
        "ruolo": "operatore",
        "cantieri": ["CNT-001"],
        "pin": "1111",
    },
    {
        "username": "giuseppe",
        "nome": "Giuseppe Leotta",
        "ruolo": "operatore",
        "cantieri": ["CNT-002"],
        "pin": "2222",
    },
    {
        "username": "marco",
        "nome": "Marco Finocchiaro",
        "ruolo": "operatore",
        "cantieri": ["CNT-003"],
        "pin": "3333",
    },
    {
        "username": "giovanna",
        "nome": "Giovanna Russo",
        "ruolo": "admin",
        "cantieri": [],
        "pin": "9999",
    },
]
