"""Trasporto Docling finto per i test (nessun sidecar reale).

Gemello di ``fake_erp.FakeTrasporto``: sostituisce il trasporto iniettabile di
``DoclingClient`` (firma httpx-compatibile), registra le chiamate e risponde con
corpi predefiniti — così i test verificano il contratto (markdown, qualità,
troncamento, errori) senza GPU né container.

**Il finto deve rifiutare come il reale**: risponde con la stessa forma di
docling-serve (``{"document": {"md_content": …}, "status", "confidence"}``), e se
il test chiede un corpo malformato lo restituisce davvero malformato. Un doppio
compiacente non è una rete.
"""

from typing import Any

# Un Markdown verosimile: intestazione, **tabella vera** (con le pipe di bordo,
# come le scrive Docling) e totali in calce. Ricalca la fattura dello Studio
# Bianchi delle fixture — fornitore e cantiere esistono in anagrafica, così le
# ricerche fuzzy trovano davvero qualcosa e il test non misura il vuoto.
#
# Contiene la ritenuta d'acconto: è lo scenario M5, quello che `CLAUDE.md` dice
# che non deve mai rompersi, qui letto per la strada nuova.
MARKDOWN_FATTURA = """Studio Tecnico Ing. Bianchi

P.IVA 02644330877 - Piazza Verga 6, Catania

FATTURA N. 15/2026 del 08/07/2026

Spett.le Costruzioni Aitho S.r.l. - Viale Africa 31, Catania

Cantiere: Residenza Le Palme

| Descrizione                             | Quantita | Importo      |
|-----------------------------------------|----------|--------------|
| Direzione lavori strutture - II acconto | -        | EUR 4.000,00 |

Imponibile: EUR 4.000,00

IVA 22%: EUR 880,00

TOTALE: EUR 4.880,00

Ritenuta d'acconto 20%: EUR 800,00

Netto a pagare: EUR 4.080,00
"""


class RispostaFinta:
    """Minimo indispensabile che ``DoclingClient`` si aspetta da una risposta httpx."""

    def __init__(self, status_code: int = 200, corpo: Any | None = None) -> None:
        self.status_code = status_code
        self._corpo = corpo if corpo is not None else {}
        self.text = str(self._corpo)

    def json(self) -> Any:
        if self._corpo is Ellipsis:  # corpo non decodificabile, come un 502 in HTML
            raise ValueError("corpo non JSON")
        return self._corpo


# L'anteprima per la revisione: docling-serve restituisce una pagina autonoma,
# con il suo foglio di stile. Qui basta che sia HTML e contenga la tabella.
HTML_FATTURA = (
    "<!DOCTYPE html><html><head><title>fattura</title></head><body>"
    "<h1>Studio Tecnico Ing. Bianchi</h1>"
    "<table><tr><td>Direzione lavori strutture - II acconto</td><td>EUR 4.000,00</td></tr></table>"
    "</body></html>"
)


def corpo_ok(
    contenuto: str | None = None,
    *,
    formato: str = "md",
    qualita: str = "good",
    secondi: float = 0.13,
) -> dict[str, Any]:
    """La risposta di docling-serve a una conversione riuscita.

    Il campo valorizzato è **solo** quello del formato chiesto, come fa il server
    vero: chiedendo ``html`` la chiave ``md_content`` resta vuota. Un finto che
    riempisse tutto nasconderebbe un client che legge la chiave sbagliata.
    """
    predefinito = MARKDOWN_FATTURA if formato == "md" else HTML_FATTURA
    documento: dict[str, Any] = {
        "filename": "documento.pdf",
        "md_content": None,
        "json_content": None,
        "html_content": None,
    }
    documento[f"{formato}_content"] = contenuto if contenuto is not None else predefinito
    return {
        "document": documento,
        "status": "success",
        "errors": [],
        "processing_time": secondi,
        "confidence": {
            "parse_score": 1.0,
            "layout_score": 0.78,
            "mean_grade": qualita,
            "low_grade": qualita,
        },
    }


class FakeDocling:
    """Trasporto Docling iniettabile.

    - ``risposte``: coda di ``RispostaFinta`` restituite in ordine; esaurita la
      coda ritorna una conversione riuscita standard.
    - ``errore``: se valorizzato, ogni chiamata solleva quell'eccezione (simula un
      sidecar spento o irraggiungibile).
    - ``chiamate``: la lista delle chiamate ricevute, per le asserzioni.
    """

    def __init__(
        self,
        risposte: list[RispostaFinta] | None = None,
        errore: Exception | None = None,
    ) -> None:
        self.chiamate: list[dict[str, Any]] = []
        self._risposte = list(risposte or [])
        self._errore = errore

    def __call__(
        self,
        url: str,
        *,
        files: dict[str, Any],
        data: dict[str, str],
        timeout: float | None = None,
    ) -> RispostaFinta:
        nome, contenuto, _tipo = files["files"]
        self.chiamate.append(
            {
                "url": url,
                "nome": nome,
                # Si legge davvero il file, come farebbe httpx: se il chiamante
                # avesse già chiuso l'handle, il test lo scoprirebbe qui.
                "byte": len(contenuto.read()),
                "data": dict(data),
                "timeout": timeout,
            }
        )
        if self._errore is not None:
            raise self._errore
        if self._risposte:
            return self._risposte.pop(0)
        return RispostaFinta(200, corpo_ok(formato=data.get("to_formats", "md")))
