"""Dove *non* può stare un nome di tabella: stringhe e separatori di funzione.

Trovato ponendo al prodotto le 120 domande del testbook: «quali mezzi hanno più
di dieci anni?» produce ``... WHERE anno < EXTRACT(YEAR FROM CURRENT_DATE) - 10``,
lettura pura e legittima, che il guardrail rifiutava con «si interrogano solo le
viste v_* (trovato: CURRENT_DATE)».

Scrivendo il test è emerso lo stesso difetto, **già presente prima**, sui
letterali: ``WHERE nome = 'da from a form'`` veniva rifiutato citando una tabella
``a``. Stessa causa (la regex cerca ``FROM`` in tutto il testo), stessa cura.

La cura deve restringersi a questo. Tutto il resto del controllo — comprese le
tabelle citate in sottoquery **dentro** quelle funzioni — deve restare in piedi,
ed è la metà dei test qui sotto.
"""

import pytest

from app.core.interroga import InterrogaError, scheletro, valida_lettura

# ------------------------------------------------- ciò che prima era rifiutato


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM v_mezzi WHERE anno < EXTRACT(YEAR FROM CURRENT_DATE) - 10",
        "SELECT EXTRACT(MONTH FROM data) AS mese, SUM(totale) FROM v_fatture GROUP BY 1",
        "SELECT TRIM(BOTH ' ' FROM nome) AS nome FROM v_cantieri",
        "SELECT SUBSTRING(nome FROM 1 FOR 3) AS sigla FROM v_cantieri",
        # due funzioni nella stessa query, e una annidata nell'altra
        "SELECT EXTRACT(YEAR FROM data), EXTRACT(MONTH FROM data) FROM v_fatture",
        "SELECT EXTRACT(YEAR FROM CURRENT_DATE) - EXTRACT(YEAR FROM data) FROM v_sal",
    ],
)
def test_le_funzioni_con_from_sono_lettura_valida(sql: str) -> None:
    assert valida_lettura(sql) == sql


def test_una_sottoquery_dentro_extract_viene_comunque_controllata() -> None:
    """Il ``FROM`` annidato è a profondità maggiore: la sua tabella resta esposta."""
    legittima = (
        "SELECT id FROM v_fatture "
        "WHERE EXTRACT(YEAR FROM (SELECT max(data) FROM v_sal)) = 2026"
    )
    assert valida_lettura(legittima) == legittima

    # stessa forma, ma la sottoquery cita una tabella non ammessa: va rifiutata
    with pytest.raises(InterrogaError, match="solo le viste"):
        valida_lettura(
            "SELECT id FROM v_fatture "
            "WHERE EXTRACT(YEAR FROM (SELECT max(data) FROM entities)) = 2026"
        )


# ------------------------------------------- ciò che deve restare rifiutato


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM entities",
        "SELECT * FROM v_fatture JOIN segreti ON 1=1",
        "DELETE FROM v_fatture",
        "SELECT * FROM read_json('/etc/passwd')",
    ],
)
def test_il_guardrail_non_si_e_indebolito(sql: str) -> None:
    with pytest.raises(InterrogaError):
        valida_lettura(sql)


# ------------------------------------------------------- la trasformazione


def test_cancella_solo_la_parola_from_e_solo_dove_serve() -> None:
    """Sostituzione con spazi, non rimozione: le posizioni degli altri token restano."""
    sql = "SELECT EXTRACT(YEAR FROM data) FROM v_fatture"
    ridotta = scheletro(sql)
    assert ridotta == "SELECT EXTRACT(YEAR      data) FROM v_fatture"
    assert len(ridotta) == len(sql)
    # una query senza niente da nascondere torna identica, senza copie inutili
    assert scheletro("SELECT 1 FROM v_fatture") == "SELECT 1 FROM v_fatture"


def test_un_from_dentro_una_stringa_non_e_una_tabella() -> None:
    """Difetto preesistente: ``'from a'`` in un literal veniva letto come tabella ``a``."""
    sql = "SELECT id FROM v_cantieri WHERE nome = 'da from a form'"
    prefisso, letterale = sql.split("'", 1)
    ridotta = scheletro(sql)
    # il letterale diventa spazi, il resto è intatto e le posizioni non si spostano
    assert ridotta == prefisso + " " * (len(letterale) + 1)
    assert valida_lettura(sql) == sql
    # e la tabella vera, fuori dal literal, resta vista
    with pytest.raises(InterrogaError, match="solo le viste"):
        valida_lettura("SELECT id FROM segreti WHERE nome = 'from a form'")
