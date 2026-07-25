"""Trasporto ERP finto per i test (nessun ERPNext reale).

Speculare a ``fake_llm.FakeCompleter``: sostituisce il trasporto iniettabile di
``ErpClient`` (firma httpx-compatibile), registra le chiamate fatte e risponde con
corpi/stati predefiniti — così i test verificano header, payload, idempotenza e
gestione degli errori senza rete.
"""

from typing import Any


class RispostaFinta:
    """Minimo indispensabile che ``ErpClient`` si aspetta da una risposta httpx."""

    def __init__(self, status_code: int = 200, corpo: Any | None = None) -> None:
        self.status_code = status_code
        self._corpo = corpo if corpo is not None else {}
        self.text = str(self._corpo)

    def json(self) -> Any:
        return self._corpo


class FakeTrasporto:
    """Trasporto ERP iniettabile.

    - ``risposte``: coda di ``RispostaFinta`` (o dict ``{status_code, corpo}``)
      restituite in ordine; esaurita la coda ritorna ``200 {"data": {}}``.
    - ``errore``: se valorizzato, ogni chiamata solleva quell'eccezione (simula
      un ERP irraggiungibile).
    - ``chiamate``: la lista delle chiamate ricevute, per le asserzioni.
    """

    def __init__(
        self,
        risposte: list[RispostaFinta | dict[str, Any]] | None = None,
        errore: Exception | None = None,
    ) -> None:
        self.chiamate: list[dict[str, Any]] = []
        self._risposte = list(risposte or [])
        self._errore = errore

    def __call__(
        self,
        metodo: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
    ) -> RispostaFinta:
        self.chiamate.append(
            {
                "metodo": metodo,
                "url": url,
                "headers": headers or {},
                "json": json,
                "timeout": timeout,
            }
        )
        if self._errore is not None:
            raise self._errore
        if self._risposte:
            prossima = self._risposte.pop(0)
            if isinstance(prossima, RispostaFinta):
                return prossima
            return RispostaFinta(**prossima)
        return RispostaFinta(200, {"data": {}})
