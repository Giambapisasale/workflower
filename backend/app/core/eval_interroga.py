"""Misura di un tier sull'interrogazione: domanda → query (§3.4, gate T3 di M18).

Fratello di :mod:`app.core.eval_t3`, che misura il *function calling* sui
documenti. Qui il compito è un altro: data una domanda in italiano, il modello
deve produrre una query che risponda. E il modo di giudicarla non può essere il
confronto fra stringhe SQL, perché **due query diverse possono essere entrambe
giuste** — cambia un alias, l'ordine delle colonne, un ``JOIN`` scritto come
sottoquery, e il testo non combacia mentre la risposta sì.

Quindi si giudica per **equivalenza del risultato**: si esegue la query di
riferimento approvata dall'ufficio (il caso golden) e quella del candidato sugli
**stessi** dati, nello stesso istante, e si confrontano le righe. Le righe non
vengono conservate nel caso golden proprio per questo: invecchierebbero al primo
documento nuovo.

Cosa si conta e cosa no:

- un caso il cui riferimento oggi non è più eseguibile (una vista rinominata) o
  non restituisce **nessuna riga** è **degenere** e va escluso, non contato come
  successo: un riferimento vuoto lo pareggerebbe qualunque candidato muto;
- ``eseguibile`` misura se il candidato ha prodotto SQL che passa i guardrail e
  gira; ``risposta_uguale`` se ha risposto la stessa cosa, valori per posizione;
  ``risposta_compatibile`` se ha risposto la stessa cosa **sulle colonne che le due
  query hanno in comune**. Il gate si decide su quest'ultima (:data:`METRICA_GATE`)
  perché la stretta boccia anche chi ha ragione: sulle 120 domande del testbook 31
  differenze su 44 erano solo proiezioni diverse — sei colonne invece di nove, stesse
  righe. ``eseguibile`` dice *dove* si rompe, ``risposta_uguale`` quanto si discosta
  anche nella forma.
"""

from typing import Any

from app.core.dal import DAL
from app.core.gateway import Gateway, GatewayError
from app.core.golden import WORKFLOW_DOMANDA, CasoGolden, casi_domanda
from app.core.interroga import Interroga, InterrogaError, esegui_query
from app.core.logbook import ottieni_logger

# Soglia di equivalenza sotto cui l'interrogazione non è pronta per T3. Stessa
# severità del gate sui documenti (``eval_t3.SOGLIA_PRONTO``).
SOGLIA_PRONTO = 0.9

# I DOUBLE di DuckDB portano rumore oltre la sesta cifra: due somme identiche
# possono differire di 1e-10 secondo l'ordine di aggregazione. Non è una
# differenza di risposta, è aritmetica in virgola mobile.
DECIMALI = 6

METRICHE = ("eseguibile", "risposta_uguale", "risposta_compatibile")
# Su quale metrica si decide se instradare su T3. È la più larga delle due sulle
# risposte, e la ragione è misurata: sulle 120 domande del testbook 31 differenze
# su 44 erano solo proiezioni diverse. Un gate che le conta come errori boccia un
# modello che ha risposto giusto — e `risposta_uguale` resta nel report per vedere
# quanto il candidato si discosta anche nella forma.
METRICA_GATE = "risposta_compatibile"
FALLITO = {"eseguibile": 0, "risposta_uguale": 0, "risposta_compatibile": 0}

_log = ottieni_logger("eval_interroga")


def _valore(valore: Any) -> Any:
    """Il valore in una forma confrontabile fra due esecuzioni della stessa domanda."""
    if isinstance(valore, bool):
        return valore
    if isinstance(valore, int):
        return float(valore)  # 3 e 3.0 sono la stessa risposta
    if isinstance(valore, float):
        return round(valore, DECIMALI)
    return valore


def normalizza(righe: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """Le righe in forma canonica: valori per posizione, insieme di righe ordinato.

    I **nomi** delle colonne si ignorano: ``SUM(totale) AS speso`` e
    ``SUM(totale) AS totale_speso`` sono la stessa risposta scritta in due modi.
    L'**ordine** delle colonne invece conta — è parte di ciò che il modello ha
    deciso di rispondere, e confondere "previsto" con "consuntivo" non è un
    dettaglio cosmetico. L'ordine delle *righe* non conta: senza ``ORDER BY`` non
    è garantito nemmeno fra due esecuzioni della stessa query.
    """
    canoniche = [tuple(_valore(v) for v in riga.values()) for riga in righe]
    return sorted(canoniche, key=repr)


def risposte_equivalenti(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    """Vero se le due query hanno risposto la stessa cosa (vedi :func:`normalizza`)."""
    return normalizza(a) == normalizza(b)


def _proietta(righe: list[dict[str, Any]], colonne: set[str]) -> list[tuple[Any, ...]]:
    canoniche = [
        tuple(_valore(v) for k, v in sorted(riga.items()) if k.lower() in colonne)
        for riga in righe
    ]
    return sorted(canoniche, key=repr)


def risposte_compatibili(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    """Vero se le due query dicono la stessa cosa **sulle colonne che hanno in comune**.

    :func:`risposte_equivalenti` confronta i valori per posizione, quindi conta come
    "diversa" anche una query che filtra e raggruppa identicamente ma seleziona sei
    colonne dove il riferimento ne seleziona nove. Misurato sulle 120 domande del
    testbook: di 44 risposte "diverse", **31 erano solo proiezioni diverse** — la
    metrica stretta da sola bocciava un candidato che aveva risposto bene.

    Qui si tengono le colonne che le due query chiamano allo stesso modo e si
    confrontano quelle. Se non c'è nessun nome in comune il confronto non conclude
    niente e si ricade sulla metrica stretta: meglio un no prudente di un sì dedotto
    dal nulla.

    Il prezzo della larghezza, da tenere in mente leggendo il report: un candidato
    che risponde **a metà** della domanda passa. Se il riferimento espone
    ``previsto`` e ``consuntivo`` e il candidato solo ``previsto``, le colonne in
    comune sono una e combaciano. Non è distinguibile da fuori dal caso legittimo
    (una lista con meno colonne), quindi si accetta e si guarda l'altro numero:
    ``risposta_uguale`` molto più bassa di ``risposta_compatibile`` significa che il
    candidato risponde in una forma sistematicamente diversa da quella approvata.
    """
    if risposte_equivalenti(a, b):
        return True
    if not a or not b:
        return False
    comuni = {k.lower() for k in a[0]} & {k.lower() for k in b[0]}
    if not comuni:
        return False
    return _proietta(a, comuni) == _proietta(b, comuni)


class EvalInterroga:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.gateway = gateway
        self.interroga = Interroga(dal, gateway)

    # ------------------------------------------------------------------ casi

    def casi(self) -> list[CasoGolden]:
        return casi_domanda(self.dal.data_dir)

    def _riferimento(self, caso: CasoGolden) -> list[dict[str, Any]] | None:
        """Le righe della query approvata, eseguita adesso. ``None`` se degenere.

        Degenere significa: non gira più (il catalogo delle viste è cambiato sotto
        il caso) oppure non trova niente. In entrambi i casi non c'è nulla contro
        cui confrontare un candidato, e far finta che ci sia produrrebbe un
        "pronto per T3" regalato.
        """
        sql = caso.sql_riferimento
        if not sql:
            return None
        try:
            righe = esegui_query(self.dal.data_dir, sql)
        except InterrogaError as exc:
            _log.warning("riferimento di %s non più eseguibile: %s", caso.id, exc)
            return None
        if not righe:
            _log.warning("riferimento di %s non restituisce righe: caso degenere", caso.id)
            return None
        return righe

    # --------------------------------------------------------------- la misura

    def valuta(
        self,
        *,
        candidato: str = "T3",
        riferimento: str = "T1",
        soglia: float = SOGLIA_PRONTO,
    ) -> dict[str, Any]:
        """Rigioca i casi-domanda sui due tier e produce il confronto."""
        casi = self.casi()
        attesi: list[tuple[CasoGolden, list[dict[str, Any]]]] = []
        degeneri = 0
        for caso in casi:
            righe = self._riferimento(caso)
            if righe is None:
                degeneri += 1
                continue
            attesi.append((caso, righe))

        dettaglio = []
        for caso, righe_attese in attesi:
            esito_c = self._prova(caso, righe_attese, candidato)
            esito_r = self._prova(caso, righe_attese, riferimento)
            dettaglio.append(
                {
                    "golden_id": caso.id,
                    "domanda": caso.domanda,
                    "candidato": esito_c,
                    "riferimento": esito_r,
                }
            )

        n = len(attesi)
        cand = _quote(dettaglio, "candidato", n)
        rif = _quote(dettaglio, "riferimento", n)
        regressione = cand[METRICA_GATE] < rif[METRICA_GATE]
        return {
            "casi": n,
            # Dichiarati, non taciuti: se metà dei casi è degenere, il verdetto
            # copre metà di quello che sembra.
            "casi_totali": len(casi),
            "degeneri": degeneri,
            "candidato": cand,
            "riferimento": rif,
            "regressione": regressione,
            "pronto_per_t3": bool(n and cand[METRICA_GATE] >= soglia and not regressione),
            "dettaglio": dettaglio,
        }

    def _prova(
        self, caso: CasoGolden, righe_attese: list[dict[str, Any]], tier: str
    ) -> dict[str, Any]:
        """Fa rispondere un tier alla domanda e confronta le righe con l'atteso.

        Non solleva mai: una misura che muore a metà non serve a nessuno. Il
        motivo del fallimento resta però nell'esito, perché "non ha prodotto SQL
        valido" e "ha risposto un'altra cosa" sono due problemi diversi.
        """
        try:
            sql = self.interroga.genera_sql(caso.domanda or "", tier=tier)
        except (GatewayError, InterrogaError) as exc:
            return {**FALLITO, "errore": str(exc)}
        except Exception as exc:  # provider, rete, quota…
            _log.warning("caso %s non rigiocabile su %s: %s", caso.id, tier, exc)
            return {**FALLITO, "errore": str(exc)}
        try:
            righe = esegui_query(self.dal.data_dir, sql)
        except InterrogaError as exc:
            return {**FALLITO, "sql": sql, "errore": str(exc)}
        return {
            "eseguibile": 1,
            "risposta_uguale": int(risposte_equivalenti(righe_attese, righe)),
            "risposta_compatibile": int(risposte_compatibili(righe_attese, righe)),
            "sql": sql,
            "righe": len(righe),
        }


def unisci(documenti: dict[str, Any], interrogazione: dict[str, Any]) -> dict[str, Any]:
    """Un solo report: aggiunge l'interrogazione al verdetto sui documenti.

    ``pronti`` e ``regressioni`` restano l'unico posto dove guardare per decidere
    cosa instradare su T3, altrimenti l'interrogazione sarebbe pronta o regredita
    in un angolo che nessuno legge. Le metriche però **non** si mescolano con
    quelle dei documenti (``tool``/``args``): misurano cose diverse e una media
    fra le due non significherebbe niente.
    """
    unito = {**documenti, "interrogazione": interrogazione}
    if interrogazione.get("pronto_per_t3"):
        unito["pronti"] = [*documenti.get("pronti", []), WORKFLOW_DOMANDA]
    if interrogazione.get("regressione"):
        unito["regressioni"] = [*documenti.get("regressioni", []), WORKFLOW_DOMANDA]
    return unito


def _quote(dettaglio: list[dict[str, Any]], chi: str, totale: int) -> dict[str, float]:
    if not totale:
        return dict.fromkeys(METRICHE, 0.0)
    return {
        metrica: round(sum(d[chi][metrica] for d in dettaglio) / totale, 4)
        for metrica in METRICHE
    }
