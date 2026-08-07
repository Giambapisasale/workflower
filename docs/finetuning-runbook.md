# Runbook del modello locale e dell’agente dati

Il prodotto usa un agente dati conversazionale, in sola lettura. Il modello sceglie
strumenti con argomenti validati; non riceve né produce istruzioni del motore dati.

## Valutazione

Il set di regressione dell’agente contiene casi approvati con:

- domanda e, se necessario, contesto precedente;
- strumenti attesi e argomenti normalizzati;
- impronta del risultato normalizzato.

La valutazione T3 confronta candidato e riferimento su scelta dello strumento,
argomenti e risultato. Una regressione blocca l’approvazione di nuove capacità.

## Evoluzione del catalogo

Le nuove capacità arrivano da feedback, richieste non coperte, trace e golden. La
proposta contiene DSL dichiarativa, ruoli, scope, esempi, test mirato e motivazione.
Prima dell’approvazione il servizio ricompila la DSL, verifica il perimetro
operatore e riesegue l’intero replay. Registry, skill, proposta e versione vengono
pubblicati insieme in un commit del repo dati.

## Archivio storico

Le interrogazioni e i golden precedenti sono conservati solo per confronto. Il report
offline è `python scripts/testbook_legacy_sql.py --data data`; non invoca API di
prodotto e non alimenta l’agente.
