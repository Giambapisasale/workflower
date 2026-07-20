# Insegna alla skill a usare il tool

È stato consolidato un tool deterministico che calcola in modo affidabile un
valore che finora la skill di estrazione ricavava "a mano". Il tuo compito:
aggiornare le istruzioni della skill perché **chiami quel tool** per quel valore,
invece di calcolarlo o interpretarlo da sé.

## Principi

- Cambia il minimo necessario: aggiungi una sezione che dice quando e come
  chiamare il tool, senza toccare le regole già corrette.
- **Il tool prima, l'LLM come fallback**: se il tool non è disponibile, va in
  errore o restituisce un risultato che non torna, la skill deve procedere come
  faceva prima (leggere/derivare il valore dal documento). Il tool è
  un'ottimizzazione, mai un obbligo.
- Sii concreto: indica il nome del tool, quali campi passargli e in quale campo
  di output mettere il risultato.

## Cosa consegnare

Un unico oggetto JSON, senza testo prima o dopo:

{
  "analisi": "quale calcolo passa al tool, in una frase",
  "motivazione": "perché il tool è più affidabile del calcolo a mano, e come resta il fallback",
  "skill_nuova": "<il testo COMPLETO della nuova skill, in Markdown>"
}

In `skill_nuova` riporta la skill attuale con dentro la nuova sezione: il testo
deve poter sostituire integralmente il file esistente.
