# Guida a Workflower

Materiale per **usare** il sistema e per **mostrarlo a un cliente**. Non è la
documentazione tecnica (quella sta nel README del progetto e in `docs/`): qui si
parte da quello che una persona vuole ottenere e si arriva a dove si clicca.

## Come è organizzata

| File | A cosa serve |
|---|---|
| [00-preparare-la-demo.md](00-preparare-la-demo.md) | Accendere tutto, credenziali, checklist prima di presentarsi davanti al cliente |
| [01-operatore.md](01-operatore.md) | Chi sta in cantiere: caricare documenti, segnare le ore, chiedere |
| [02-ufficio-revisione.md](02-ufficio-revisione.md) | Controllare, correggere, validare, scartare — il cuore del lavoro d'ufficio |
| [03-controllo-costi.md](03-controllo-costi.md) | Cruscotto, cantiere, scostamenti, interrogazione libera, report |
| [04-anagrafiche-e-dati.md](04-anagrafiche-e-dati.md) | Cantieri, fornitori, dipendenti, mezzi, computi: creare e correggere |
| [05-sistema-e-qualita.md](05-sistema-e-qualita.md) | Workflow, run, strumenti, dataset, miglioramento automatico, diagnosi, log |
| [06-copione-demo.md](06-copione-demo.md) | **Il copione**: 30 minuti, minuto per minuto, con cosa dire |
| [07-domande-difficili.md](07-domande-difficili.md) | Le obiezioni che arrivano davvero, e la risposta onesta |
| [esempi/](esempi/) | I documenti di prova, uno per ogni strada del sistema |

Se hai poco tempo: [00](00-preparare-la-demo.md) per accendere, poi
[06](06-copione-demo.md) per la presentazione. Il resto è consultazione.

## Le due facce del prodotto

Workflower è **una** applicazione con **due** interfacce, ed è la cosa più
importante da far capire in una demo.

**L'operatore** (`/op`) è chi sta in cantiere. Vede quattro bottoni grandi, non
compila moduli, non sceglie categorie, non sa cos'è un workflow. Fotografa una
bolla e ha finito. Il sistema gli parla come parlerebbe un collega: «Ho letto:
fattura!», «Grazie! Ci pensiamo noi».

**L'ufficio** (`/admin`) vede la meccanica: cosa ha letto il sistema, con quanta
sicurezza, quali strumenti ha usato, dove ha esitato. Controlla, corregge,
valida. E da quelle correzioni il sistema impara.

La frase da tenere in tasca: *l'operatore non deve imparare niente, l'ufficio non
deve digitare niente*.

## Cosa lo rende diverso

- **Non ci sono maschere di inserimento.** Il documento entra come foto o file, e
  ne esce un dato strutturato. Nessuno digita numeri di fattura.
- **Ogni dato è tracciabile fino al pixel.** Per ogni valore si sa da quale
  documento viene, con che confidenza è stato letto, chi lo ha validato e quando.
- **Il sistema dichiara quando non è sicuro.** Non c'è un output "sempre giusto":
  c'è una confidenza per campo, e sotto soglia il documento va in revisione.
- **Impara dalle correzioni.** Le note che l'ufficio lascia su un campo diventano
  proposte di modifica alle istruzioni, che un umano approva o rifiuta.
- **Tutto è un file versionato.** Lo stato del sistema è un repo git: ogni
  modifica ha un autore, una data e si può annullare.
