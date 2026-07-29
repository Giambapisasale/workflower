#!/usr/bin/env python3
"""Pone al prodotto tutte le domande del testbook e raccoglie cosa ne esce.

Serve a due cose, in quest'ordine (§3.6 → §3.7):

1. **Scoprire cosa si ripete.** Ogni domanda passa da ``POST /ask`` in modalità
   admin, quindi finisce in ``dataset/queries.jsonl`` con il suo fingerprint. Le
   query strutturalmente uguali si raggruppano da sole: quei gruppi sono i
   candidati a diventare viste ``v_*`` e tool ``t_*``. Non è un'ottimizzazione,
   è il passo che *cambia il compito* del modello locale — da "scrivi SQL su 27
   viste" a "scegli un tool e riempi i parametri".
2. **Preparare i casi golden.** Il report elenca domanda, query e righe trovate:
   l'ufficio lo rivede e approva le corrette con ``--approva``, che le fissa via
   ``POST /api/golden/domande``. Da lì in poi il gate T3 misura anche
   l'interrogazione (``GET /api/dataset/eval-t3``, campo ``interrogazione``).

Non è un test pytest: gira contro un backend **avviato**, con i tier LLM veri, e
costa token. Ogni domanda è una chiamata al modello.

Uso:
    python scripts/testbook_ask.py --token $ADMIN_TOKEN
    python scripts/testbook_ask.py --token ... --famiglia costi --limite 10
    python scripts/testbook_ask.py --token ... --approva esiti.json
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

for _flusso in (sys.stdout, sys.stderr):
    if hasattr(_flusso, "reconfigure"):
        _flusso.reconfigure(encoding="utf-8", errors="replace")

CATALOGO = Path(__file__).with_name("testbook_domande.json")
VERDE, ROSSO, GIALLO, GRIGIO, RESET = (
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[90m",
    "\033[0m",
)


def _chiama(
    base: str, percorso: str, token: str, corpo: dict[str, Any] | None = None
) -> tuple[int, Any]:
    """Una chiamata HTTP all'API. Ritorna ``(status, corpo)``, senza mai sollevare."""
    dati = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    richiesta = urllib.request.Request(
        f"{base.rstrip('/')}{percorso}",
        data=dati,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST" if dati else "GET",
    )
    try:
        with urllib.request.urlopen(richiesta, timeout=180) as risposta:
            return risposta.status, json.loads(risposta.read() or b"null")
    except urllib.error.HTTPError as exc:
        testo = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(testo)
        except json.JSONDecodeError:
            return exc.code, {"detail": testo}
    except Exception as exc:  # rete, timeout, backend spento
        return 0, {"detail": str(exc)}


def _domande(famiglia: str | None, difficolta: int | None, limite: int | None) -> list[dict]:
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    voci = catalogo["domande"]
    if famiglia:
        voci = [v for v in voci if v["famiglia"] == famiglia]
    if difficolta:
        voci = [v for v in voci if v["difficolta"] == difficolta]
    return voci[:limite] if limite else voci


def interroga(base: str, token: str, voci: list[dict]) -> list[dict[str, Any]]:
    """Pone ogni domanda e raccoglie l'esito, senza fermarsi ai fallimenti.

    Una domanda che il modello non sa tradurre è un dato utile — dice dove serve
    una vista consolidata — non un motivo per interrompere la raccolta.
    """
    esiti = []
    for i, voce in enumerate(voci, 1):
        stato, corpo = _chiama(
            base, "/api/ask", token, {"question": voce["domanda"], "mode": "admin"}
        )
        esito = {**voce, "stato": stato}
        if stato == 200:
            esito |= {
                "sql": corpo.get("sql"),
                "righe": len(corpo.get("rows") or []),
                "run_id": corpo.get("run_id"),
            }
            colore = VERDE if esito["righe"] else GIALLO
            nota = f"{esito['righe']} righe"
        else:
            esito |= {"errore": (corpo or {}).get("detail")}
            colore = ROSSO
            nota = str(esito["errore"])[:70]
        # flush esplicito: su pipe Python bufferizza a blocchi e una corsa da 120
        # domande resterebbe muta per venti minuti
        print(
            f"{colore}[{i:3}/{len(voci)}]{RESET} {voce['id']} {voce['domanda'][:58]:60} {nota}",
            flush=True,
        )
        esiti.append(esito)
    return esiti


def riepiloga(base: str, token: str, esiti: list[dict[str, Any]]) -> None:
    """Stampa cosa è andato e, soprattutto, quali query si ripetono."""
    ok = [e for e in esiti if e["stato"] == 200]
    vuote = [e for e in ok if not e["righe"]]
    print(f"\n{'=' * 72}")
    print(f"domande poste     {len(esiti)}")
    print(f"query prodotte    {len(ok)}")
    print(f"{GIALLO}senza righe       {len(vuote)}{RESET}", end="")
    print("  (o i dati non ci sono, o la query è sbagliata)")
    print(f"{ROSSO}rifiutate         {len(esiti) - len(ok)}{RESET}")

    stato, corpo = _chiama(base, "/api/dataset/queries", token)
    if stato != 200:
        return
    gruppi = [g for g in (corpo.get("gruppi") or []) if g["conteggio"] > 1]
    if not gruppi:
        print(f"\n{GRIGIO}nessun fingerprint ripetuto: niente da consolidare ancora{RESET}")
        return
    print("\nquery ricorrenti (candidate a vista v_* / tool t_*, §3.6):")
    for gruppo in gruppi[:15]:
        print(f"  {gruppo['conteggio']}×  {gruppo['esempio'][:96]}")


def approva(base: str, token: str, percorso: Path) -> None:
    """Fissa come casi golden le domande marcate ``"approvato": true`` nel file.

    Il file è quello scritto da questo script, rivisto a mano dall'ufficio: è lì
    che sta il giudizio umano, e non c'è modo di aggirarlo. Il server rifiuta
    comunque le query che non girano o che non trovano nessuna riga.
    """
    esiti = json.loads(percorso.read_text(encoding="utf-8"))
    scelti = [e for e in esiti if e.get("approvato") and e.get("sql")]
    if not scelti:
        print(f"{GIALLO}nessuna domanda marcata \"approvato\": true in {percorso}{RESET}")
        return
    creati = falliti = 0
    for esito in scelti:
        stato, corpo = _chiama(
            base,
            "/api/golden/domande",
            token,
            {"domanda": esito["domanda"], "sql": esito["sql"], "run_id": esito.get("run_id")},
        )
        if stato == 201:
            creati += 1
            print(f"{VERDE}[OK]{RESET}   {corpo['id']}  {esito['domanda'][:60]}")
        else:
            falliti += 1
            print(f"{ROSSO}[NO]{RESET}   {esito['id']}  {(corpo or {}).get('detail')}")
    print(f"\ncasi golden creati: {creati}, rifiutati: {falliti}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="URL del backend")
    parser.add_argument("--token", required=True, help="token di un utente admin")
    parser.add_argument("--famiglia", help="pone solo le domande di una famiglia")
    parser.add_argument("--difficolta", type=int, choices=(1, 2, 3))
    parser.add_argument("--limite", type=int, help="pone solo le prime N domande")
    parser.add_argument("--esiti", type=Path, default=Path("testbook-esiti.json"))
    parser.add_argument(
        "--approva",
        type=Path,
        metavar="FILE",
        help="non pone domande: crea i casi golden dal file di esiti rivisto",
    )
    argomenti = parser.parse_args()

    if argomenti.approva:
        approva(argomenti.base, argomenti.token, argomenti.approva)
        return 0

    voci = _domande(argomenti.famiglia, argomenti.difficolta, argomenti.limite)
    if not voci:
        print(f"{ROSSO}nessuna domanda con questi filtri{RESET}")
        return 1
    esiti = interroga(argomenti.base, argomenti.token, voci)
    riepiloga(argomenti.base, argomenti.token, esiti)
    # ``approvato: false`` di default: l'approvazione è un gesto umano, e un
    # default a true trasformerebbe una svista in un caso golden sbagliato.
    da_rivedere = [{**e, "approvato": False} for e in esiti]
    argomenti.esiti.write_text(
        json.dumps(da_rivedere, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nrivedi {argomenti.esiti}, metti \"approvato\": true dove la query è giusta, poi:")
    print(f"  python scripts/testbook_ask.py --token ... --approva {argomenti.esiti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
