"""Generatore di uno scenario reale: un mese di attività su 10 cantieri.

Popola un repo dati *da zero* (schemi + viste + git, nessun dato d'esempio) con
un mese di documenti come li produrrebbe un'impresa edile da 100 dipendenti — 88
operai di varie mansioni distribuiti sui cantieri e 12 impiegati d'ufficio — e
ritorna gli **aggregati attesi**, calcolati in Python dagli stessi dati generati.
I test confrontano poi ciò che la piattaforma riporta (viste, cruscotto, registro,
report, scostamenti) con questi attesi indipendenti.

Deterministico (PRNG con seme fisso): stessa esecuzione, stessi numeri. Le
scritture passano tutte dal DAL — schema validato, un commit per mutazione — così
lo scenario è anche un test dell'invariante "ogni mutazione = commit" su scala.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.auth import hash_pin
from app.core.dal import DAL
from app.models.envelope import Envelope, Meta
from app.seed import init_data_repo

ANNO, MESE = 2026, 6
N_CANTIERI = 10
N_OPERAI = 88
N_IMPIEGATI = 12  # 88 + 12 = 100 dipendenti

# Mansione operaio → costo orario (deterministico: rende calcolabile il costo).
COSTO_MANSIONE = {
    "capocantiere": 35.0, "geometra": 30.0, "gruista": 28.0, "elettricista": 27.0,
    "idraulico": 27.0, "carpentiere": 26.0, "ferraiolo": 25.0, "muratore": 24.0,
    "autista": 24.0, "manovale": 20.0,
}
MANSIONI_OPERAIE = [
    "muratore", "muratore", "manovale", "manovale", "carpentiere", "ferraiolo",
    "gruista", "elettricista", "idraulico", "autista",
]
NOMI = [
    "Salvatore", "Giuseppe", "Antonio", "Francesco", "Rosario", "Carmelo", "Alfio",
    "Sebastiano", "Orazio", "Vincenzo", "Angelo", "Mario", "Luca", "Davide", "Marco",
    "Gaetano", "Nunzio", "Santo", "Emanuele", "Riccardo", "Giovanni", "Paolo",
]
COGNOMI = [
    "Russo", "Torrisi", "Leotta", "Grasso", "Caruso", "Privitera", "Pappalardo",
    "Finocchiaro", "Musumeci", "Scuderi", "Rizzo", "Cavallaro", "Distefano",
    "Costa", "Longo", "Messina", "Sciuto", "Puglisi", "Zappalà", "Barbagallo",
]
UFFICI = [
    "Direzione", "Contabilità", "Contabilità", "Ufficio acquisti", "Ufficio acquisti",
    "Ufficio tecnico", "Ufficio tecnico", "Geometra", "Geometra", "Segreteria",
    "Risorse umane", "Sicurezza",
]
CATEGORIE_FORN = ["calcestruzzi", "ferramenta", "noleggi", "elettrico", "idraulico",
                  "professionista", "movimento terra", "prefabbricati"]
UNITA = ["mc", "kg", "mq", "ml", "cad", "t"]
VOCI_TIPO = [
    ("scavi", "Scavo di sbancamento"), ("strutture", "Getto fondazioni"),
    ("strutture", "Pilastri in c.a."), ("murature", "Muratura in laterizio"),
    ("finiture", "Intonaco civile"), ("finiture", "Pavimenti"),
    ("impianti", "Impianto elettrico"), ("impianti", "Impianto idrico"),
]


@dataclass
class Scenario:
    cantieri: list[str]
    operai: set[str] = field(default_factory=set)
    impiegati: list[str] = field(default_factory=list)
    mansioni: set[str] = field(default_factory=set)
    operatori: dict[str, str] = field(default_factory=dict)   # username → cantiere
    admin: list[str] = field(default_factory=list)
    pin: dict[str, str] = field(default_factory=dict)
    n_fatture: int = 0
    n_ddt: int = 0
    n_sal: int = 0
    n_rapportini: int = 0
    n_pozzetti: int = 0
    totale_fatture: float = 0.0
    speso: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    ore: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    costo_mano: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    consuntivo: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    pozzetti_stato: dict[str, dict[str, int]] = field(default_factory=dict)


def _giorni_lavorativi(anno: int, mese: int) -> list[dt.date]:
    giorni, giorno = [], dt.date(anno, mese, 1)
    while giorno.month == mese:
        if giorno.weekday() < 5:
            giorni.append(giorno)
        giorno += dt.timedelta(days=1)
    return giorni


def _nomi_unici(rng: random.Random, quanti: int) -> list[str]:
    tutti = [f"{n} {c}" for c in COGNOMI for n in NOMI]
    rng.shuffle(tutti)
    return tutti[:quanti]


def costruisci_mese(data_dir: Path, seme: int = 20260601) -> Scenario:  # noqa: PLR0915
    """Costruisce lo scenario e ritorna gli aggregati attesi."""
    rng = random.Random(seme)
    init_data_repo(data_dir)
    dal = DAL(data_dir)
    meta = Meta(validato_da="sim")

    def crea(tipo: str, entity_id: str, dati: dict[str, Any]) -> None:
        dal.create(
            Envelope(id=entity_id, tipo=tipo, stato="validato", dati=dati, meta=meta),
            run_id="sim",
        )

    cantieri = [f"CNT-{i:03d}" for i in range(1, N_CANTIERI + 1)]
    sc = Scenario(cantieri=cantieri)

    # --- cantieri
    for i, cid in enumerate(cantieri, start=1):
        crea("cantiere", cid, {
            "nome": f"Cantiere {i:02d}", "indirizzo": f"Via dei Lavori {i}",
            "comune": "Catania", "committente": f"Committente {i} S.r.l.",
            "budget": float(500_000 + i * 120_000), "data_inizio": "2026-01-15",
        })

    # --- fornitori
    fornitori = [f"FRN-{i:03d}" for i in range(1, 19)]
    for i, fid in enumerate(fornitori):
        crea("fornitore", fid, {
            "ragione_sociale": f"Fornitore {i + 1} S.r.l.",
            "partita_iva": f"{10000000000 + i:011d}",
            "categoria": CATEGORIE_FORN[i % len(CATEGORIE_FORN)],
        })
    professionisti = {fornitori[5], fornitori[11]}  # emettono parcelle con ritenuta

    # --- anagrafiche di dominio (M20)
    for i in range(1, 21):
        crea("materiale", f"MAT-{i:03d}", {
            "descrizione": f"Materiale {i}", "unita_misura": rng.choice(UNITA),
            "prezzo_unitario": round(rng.uniform(0.5, 200), 2),
        })
    for i in range(1, 13):
        crea("mezzo", f"MEZ-{i:03d}", {
            "descrizione": f"Mezzo {i}", "tipo": rng.choice(["escavatore", "gru", "autocarro"]),
            "costo_orario": round(rng.uniform(30, 80), 2),
        })
    lavorazioni = [f"LAV-{i:03d}" for i in range(1, 11)]
    for i, lid in enumerate(lavorazioni):
        cat, desc = VOCI_TIPO[i % len(VOCI_TIPO)]
        crea("lavorazione", lid, {
            "codice": f"L{i + 1:02d}", "descrizione": desc,
            "unita_misura": "mq", "categoria": cat,
        })

    # --- computi (uno per cantiere) → voci referenziabili dallo scostamento
    voci_per_cantiere: dict[str, list[str]] = {}
    for c_idx, cid in enumerate(cantieri, start=1):
        voci = []
        for v_idx, (cat, desc) in enumerate(VOCI_TIPO, start=1):
            vid = f"VC{c_idx}-{v_idx:02d}"
            q = float(rng.randint(50, 500))
            pu = round(rng.uniform(20, 300), 2)
            voci.append({
                "id": vid, "codice": f"{c_idx}.{v_idx}", "descrizione": desc,
                "unita_misura": "mq", "quantita": q, "prezzo_unitario": pu,
                "importo": round(q * pu, 2), "categoria": cat,
            })
        voci_per_cantiere[cid] = [v["id"] for v in voci]
        crea("computo", f"CMP-{c_idx:03d}", {
            "cantiere_id": cid, "descrizione": f"Computo cantiere {c_idx}", "voci": voci,
        })

    # --- forza lavoro: 88 operai (10 capicantiere + 78) su 10 cantieri
    nomi = _nomi_unici(rng, N_OPERAI)
    operai: list[dict[str, str]] = []
    for j, nome in enumerate(nomi):
        cid = cantieri[j % N_CANTIERI]
        # un capocantiere per cantiere (i primi 10), poi mansioni operaie assortite
        mansione = "capocantiere" if j < N_CANTIERI else MANSIONI_OPERAIE[j % len(MANSIONI_OPERAIE)]
        operai.append({"nome": nome, "mansione": mansione, "cantiere": cid})
        sc.operai.add(nome)
        sc.mansioni.add(mansione)
    crew: dict[str, list[dict[str, str]]] = defaultdict(list)
    for o in operai:
        crew[o["cantiere"]].append(o)

    # --- utenti: 10 capicantiere (operatori) + 12 impiegati d'ufficio (admin)
    for i, cid in enumerate(cantieri, start=1):
        u = f"capo{i:02d}"
        sc.operatori[u] = cid
        sc.pin[u] = f"{1000 + i}"
    for i, ruolo in enumerate(UFFICI, start=1):
        u = f"ufficio{i:02d}"
        sc.admin.append(u)
        sc.impiegati.append(f"{ruolo} {i}")
        sc.pin[u] = f"{2000 + i}"
    _scrivi_utenti(dal, sc)

    giorni = _giorni_lavorativi(ANNO, MESE)

    # --- rapportini: uno per cantiere per giorno lavorativo (il 1° giorno = tutta la squadra)
    for cid in cantieri:
        squadra = crew[cid]
        for d_idx, giorno in enumerate(giorni):
            presenti = squadra if d_idx == 0 else [o for o in squadra if rng.random() < 0.85]
            if not presenti:
                continue
            righe = []
            for o in presenti:
                ore = round(rng.choice([7.5, 8.0, 8.0, 8.5, 9.0]), 1)
                costo = COSTO_MANSIONE[o["mansione"]]
                righe.append({"nominativo": o["nome"], "mansione": o["mansione"],
                              "ore": ore, "costo_orario": costo})
                sc.ore[cid] += ore
                sc.costo_mano[cid] += ore * costo
            dal.crea_progressivo("rapportino", {
                "cantiere_id": cid, "data": giorno.isoformat(), "righe": righe,
            }, stato="validato", meta=meta)
            sc.n_rapportini += 1

    # --- DDT: ~2/settimana per cantiere
    for cid in cantieri:
        for _ in range(8):
            giorno = rng.choice(giorni)
            n_righe = rng.randint(1, 3)
            righe = [{
                "descrizione": f"Consegna materiale {rng.randint(1, 20)}",
                "quantita": float(rng.randint(1, 50)), "unita_misura": rng.choice(UNITA),
                "voce_computo_id": None,
            } for _ in range(n_righe)]
            dal.crea_progressivo("ddt", {
                "fornitore_id": rng.choice(fornitori), "cantiere_id": cid,
                "numero": f"DDT{rng.randint(1000, 9999)}", "data": giorno.isoformat(),
                "causale": "consegna materiali", "riferimento_ordine": None, "righe": righe,
            }, stato="validato", meta=meta)
            sc.n_ddt += 1

    # --- fatture: ~5 per cantiere; una riga per fattura collegata a una voce di computo
    for cid in cantieri:
        for _ in range(5):
            giorno = rng.choice(giorni)
            fid = rng.choice(fornitori)
            imponibile = round(rng.uniform(600, 9000), 2)
            iva = round(imponibile * 0.22, 2)
            totale = round(imponibile + iva, 2)
            ritenuta = round(imponibile * 0.20, 2) if fid in professionisti else None
            voce = rng.choice(voci_per_cantiere[cid])
            importo_collegato = round(rng.uniform(200, 5000), 2)
            righe = [{
                "descrizione": "Lavorazione a misura", "quantita": None,
                "unita_misura": None, "importo": importo_collegato, "voce_computo_id": voce,
            }]
            for _ in range(rng.randint(0, 2)):
                righe.append({
                    "descrizione": "Voce non computata", "quantita": None,
                    "unita_misura": None, "importo": round(rng.uniform(50, 800), 2),
                    "voce_computo_id": None,
                })
            dal.crea_progressivo("fattura", {
                "fornitore_id": fid, "cantiere_id": cid,
                "numero": f"{rng.randint(1, 999)}/2026", "data": giorno.isoformat(),
                "imponibile": imponibile, "iva": iva, "totale": totale,
                "ritenuta_acconto": ritenuta, "righe": righe,
            }, stato="validato", meta=meta)
            sc.n_fatture += 1
            sc.totale_fatture = round(sc.totale_fatture + totale, 2)
            sc.speso[cid] = round(sc.speso[cid] + totale, 2)
            sc.consuntivo[cid] = round(sc.consuntivo[cid] + importo_collegato, 2)

    # --- SAL: due per cantiere, avanzamento crescente
    for c_idx, cid in enumerate(cantieri, start=1):
        for n, (giorno, perc) in enumerate(
            [(giorni[len(giorni) // 2], 30.0), (giorni[-1], 55.0)], start=1
        ):
            lavori = float(400_000 + c_idx * 50_000)
            dal.crea_progressivo("sal", {
                "cantiere_id": cid, "numero": str(n), "data": giorno.isoformat(),
                "importo_lavori": lavori, "importo_progressivo": round(lavori * perc / 100, 2),
                "percentuale_avanzamento": perc,
            }, stato="validato", meta=meta)
            sc.n_sal += 1

    # --- pozzetti: ~4 per cantiere, stati misti
    stati = ["previsto", "installato", "collaudato"]
    for cid in cantieri:
        conteggio = {"previsto": 0, "installato": 0, "collaudato": 0}
        for k in range(4):
            stato = stati[k % 3]
            conteggio[stato] += 1
            dal.crea_progressivo("pozzetto", {
                "cantiere_id": cid, "codice": f"PZ-{k + 1}", "tipo": "ispezione",
                "stato": stato,
            }, stato="validato", meta=meta)
            sc.n_pozzetti += 1
        sc.pozzetti_stato[cid] = conteggio

    # --- cronoprogramma: uno per cantiere
    for cid in cantieri:
        voci = [
            {"lavorazione_id": lavorazioni[0], "descrizione": "Scavi",
             "inizio_previsto": "2026-02-01", "fine_prevista": "2026-04-30"},
            {"lavorazione_id": lavorazioni[1], "descrizione": "Strutture",
             "inizio_previsto": "2026-05-01", "fine_prevista": "2026-07-15"},
            {"lavorazione_id": lavorazioni[4], "descrizione": "Finiture",
             "inizio_previsto": "2026-07-16", "fine_prevista": "2027-01-31"},
        ]
        dal.crea_progressivo("cronoprogramma", {"cantiere_id": cid, "voci": voci},
                             stato="validato", meta=meta)

    # --- scadenze: ~2 per cantiere
    for cid in cantieri:
        for k in range(2):
            dal.crea_progressivo("scadenza", {
                "descrizione": f"Adempimento {k + 1}", "data_scadenza": "2026-09-30",
                "tipo": "permesso", "cantiere_id": cid, "stato": "aperta",
            }, stato="validato", meta=meta)

    return sc


def _scrivi_utenti(dal: DAL, sc: Scenario) -> None:
    """Scrive config/utenti.json con capicantiere (operatori) e ufficio (admin)."""
    record = []
    for u, cid in sc.operatori.items():
        record.append({"username": u, "nome": f"Capocantiere {cid}", "ruolo": "operatore",
                       "cantieri": [cid], "pin_pbkdf2": hash_pin(u, sc.pin[u])})
    for u in sc.admin:
        record.append({"username": u, "nome": u, "ruolo": "admin", "cantieri": [],
                       "pin_pbkdf2": hash_pin(u, sc.pin[u])})
    percorso = dal.data_dir / "config" / "utenti.json"
    percorso.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dal.commit_paths([percorso], "sim: utenti dello scenario")
