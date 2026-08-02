"""L'azienda che usa il sistema: chi siamo, per riconoscerci sui documenti.

Serve a una domanda che finora nessuno poneva: la fattura che stiamo leggendo è
davvero **intestata a noi**? Un documento di un altro destinatario finito nel
mucchio oggi verrebbe registrato come tutti gli altri.

Dato, non codice né variabile d'ambiente: sta in ``data/config/azienda.json``
accanto a ``utenti.json`` e ``views.sql``, si modifica dalla UI dell'ufficio e
ogni modifica è un commit — quindi si sa sempre chi ha cambiato la partita IVA
e quando. Un repo dati creato prima che questa sezione esistesse semplicemente
non ha il file: :func:`leggi` risponde con i campi vuoti e nessuno si accorge
di niente finché l'ufficio non li compila.

Distinto da ``ERP_COMPANY``, che è il *nome* dell'azienda dentro ERPNext (una
coordinata d'integrazione, giustamente in env): qui c'è l'anagrafica che serve
a leggere i documenti, e vive con i dati.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

RELATIVO = "config/azienda.json"

CAMPI = ("denominazione", "indirizzo", "partita_iva")

MAX_LUNGHEZZA = 200

# Forme societarie: rumore per il confronto. «Costruzioni Aitho S.r.l.» e
# «COSTRUZIONI AITHO SRL» sono la stessa impresa, e la sigla è proprio il pezzo
# che ogni fornitore scrive a modo suo.
FORME_SOCIETARIE = frozenset(
    {"srl", "srls", "spa", "snc", "sas", "scarl", "scrl", "sc", "ss", "sapa"}
)

# Sotto questa somiglianza il destinatario si considera un'altra impresa.
SOGLIA_CORRISPONDENZA = 0.80

# Due parole sono "la stessa parola" sopra questa soglia: assorbe i refusi e gli
# scivoloni dell'OCR («Aiho» per «Aitho») senza confondere parole diverse
# («Etna» e «Aitho» si somigliano per 0,22).
SOGLIA_PAROLA = 0.85

_NON_ALFANUMERICI = re.compile(r"[^0-9a-zàèéìòù]+")


def parole_ragione_sociale(testo: str) -> list[str]:
    """Le parole che contano: minuscole, senza punteggiatura né forma societaria.

    «Costruzioni Aitho S.r.l.» e «COSTRUZIONI AITHO SRL» sono la stessa impresa,
    e la sigla è proprio il pezzo che ogni fornitore scrive a modo suo.
    """
    # I punti si tolgono **prima** di spezzare: senza, «s.r.l.» diventa tre
    # parole di una lettera che pesano nel confronto quanto il nome vero, e due
    # scritture della stessa impresa smettono di somigliarsi.
    senza_punti = (testo or "").lower().replace(".", "")
    parole = _NON_ALFANUMERICI.sub(" ", senza_punti).split()
    nocciolo = [p for p in parole if len(p) > 1 and p not in FORME_SOCIETARIE]
    return nocciolo or parole


def somiglianza(nostra: str, letta: str) -> float:
    """Quanto il nome **letto sul documento** copre il nostro, fra 0 e 1.

    Asimmetrica di proposito. Se tutte le nostre parole compaiono nel testo
    letto la risposta è 1: regge la riga intera d'intestazione («Spett.le
    Costruzioni Aitho S.r.l. — Viale Africa 31, Catania»), l'ordine invertito e
    i refusi. Al contrario, un nome che condivide con noi solo la parola
    generica — «Costruzioni Etna» — copre metà del nostro e resta sotto soglia:
    è il caso che questo controllo esiste per prendere, e un confronto fra
    stringhe intere lo lasciava passare.
    """
    nostre, lette = parole_ragione_sociale(nostra), parole_ragione_sociale(letta)
    if not nostre or not lette:
        return 0.0
    coperte = sum(
        1
        for parola in nostre
        if any(SequenceMatcher(None, parola, altra).ratio() >= SOGLIA_PAROLA for altra in lette)
    )
    if coperte == len(nostre):
        return 1.0
    return round(2 * coperte / (len(nostre) + len(lette)), 3)


class AziendaNonValida(ValueError):
    """Dati rifiutati: messaggio già scritto per l'ufficio, non per il log."""


@dataclass(frozen=True)
class Azienda:
    """L'anagrafica dell'azienda corrente. Campi vuoti = non ancora configurata."""

    denominazione: str = ""
    indirizzo: str = ""
    partita_iva: str = ""

    def configurata(self) -> bool:
        """Almeno la denominazione: è il minimo per riconoscersi su una fattura.

        Indirizzo e partita IVA aiutano, ma una fattura può riportare solo la
        ragione sociale — pretenderli tutti bloccherebbe chi ha solo quello.
        """
        return bool(self.denominazione.strip())

    def come_dizionario(self) -> dict[str, str]:
        return asdict(self)

    def riconosce(self, destinatario: str | None) -> bool:
        """Questo documento è intestato a noi?

        Prudente per scelta: se non siamo configurati, o se il destinatario non
        è stato letto, la risposta è **sì**. Un controllo che non si può fare
        non deve trasformarsi in un sospetto — manderebbe in revisione tutto,
        e una segnalazione che compare sempre non la guarda più nessuno.

        La partita IVA, quando c'è su entrambi i lati, decide da sola: è
        l'identificativo, e batte qualunque somiglianza di nome.
        """
        if not self.configurata() or not (destinatario or "").strip():
            return True
        cifre = re.sub(r"\D", "", self.partita_iva)
        if len(cifre) >= 8 and cifre in re.sub(r"\D", "", destinatario or ""):
            return True
        return somiglianza(self.denominazione, destinatario or "") >= SOGLIA_CORRISPONDENZA


def leggi(data_dir: Path) -> Azienda:
    """L'azienda configurata; campi vuoti se il file non c'è o è illeggibile.

    Non solleva mai: questa lettura sta sulla strada dell'ingestione, e
    un JSON corrotto deve degradare la verifica del destinatario, non fermare
    l'elaborazione dei documenti.
    """
    percorso = Path(data_dir) / RELATIVO
    try:
        corpo = json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Azienda()
    if not isinstance(corpo, dict):
        return Azienda()
    return Azienda(**{campo: str(corpo.get(campo) or "").strip() for campo in CAMPI})


def blocco_per_il_modello(azienda: Azienda) -> str | None:
    """Chi siamo, da mettere nel prompt di estrazione. ``None`` se non configurati.

    Il modello lo usa per due cose: trascrivere il destinatario e sapere che ha
    senso confrontarlo. Il giudizio finale però non è suo — lo rifà il runtime
    con un confronto deterministico, perché su «questa impresa è la stessa?» un
    modello è persuasivo anche quando sbaglia.
    """
    if not azienda.configurata():
        return None
    righe = [f"- Denominazione: {azienda.denominazione}"]
    if azienda.indirizzo:
        righe.append(f"- Indirizzo: {azienda.indirizzo}")
    if azienda.partita_iva:
        righe.append(f"- Partita IVA: {azienda.partita_iva}")
    return (
        "Sei l'addetto di questa impresa, che è la destinataria dei documenti:\n"
        + "\n".join(righe)
        + "\n\nI documenti che ricevi dovrebbero essere intestati a lei. "
        "Non correggere mai ciò che leggi per farlo combaciare: trascrivi il "
        "destinatario **come sta scritto**, anche quando è un'altra impresa."
    )


def valida(grezzo: dict[str, object]) -> Azienda:
    """Normalizza e controlla ciò che arriva dalla UI.

    Volutamente permissivo sulla partita IVA: si accettano le 11 cifre italiane
    ma anche un identificativo estero, perché il campo serve a confrontare, non
    a certificare. Rifiutare una forma legittima costerebbe più che accettarne
    una strana.
    """
    valori = {campo: str(grezzo.get(campo) or "").strip() for campo in CAMPI}
    for campo, valore in valori.items():
        if len(valore) > MAX_LUNGHEZZA:
            raise AziendaNonValida(f"il campo «{campo}» è troppo lungo")
    if not valori["denominazione"]:
        raise AziendaNonValida("la denominazione è obbligatoria")
    return Azienda(**valori)


def scrivi(data_dir: Path, azienda: Azienda) -> Path:
    """Scrive il file e ne restituisce il percorso (il commit lo fa chi chiama)."""
    percorso = Path(data_dir) / RELATIVO
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(
        json.dumps(azienda.come_dizionario(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return percorso
