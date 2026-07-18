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
                    "voce_computo_id": None,
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
                    "voce_computo_id": None,
                },
                {
                    "descrizione": "Malta premiscelata M10",
                    "quantita": 60,
                    "unita_misura": "sacco",
                    "importo": 468.00,
                    "voce_computo_id": None,
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
                    "voce_computo_id": None,
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
                    "voce_computo_id": None,
                },
                {
                    "descrizione": "Quadro elettrico di cantiere ASC",
                    "quantita": 1,
                    "unita_misura": "pz",
                    "importo": 980.00,
                    "voce_computo_id": None,
                },
                {
                    "descrizione": "Manodopera elettricista",
                    "quantita": 24,
                    "unita_misura": "h",
                    "importo": 672.00,
                    "voce_computo_id": None,
                },
            ],
        },
    },
]
