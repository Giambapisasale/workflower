# Design system Aitho (copia locale)

Questa cartella è il linguaggio visivo di Aitho portato dentro Workflower. Non è
codice di Workflower: è un **dato versionato** che arriva da fuori.

## Da dove viene

- Progetto Claude Design **Aitho Design System**, id
  `c0878fb9-47c4-4316-a3e8-ba782bb3b2ce` — lo stesso id che i file in `/design`
  referenziano.
- Quel progetto a sua volta deriva da `@aitho/ui` (repo *Aitho-Design-UI*,
  React + TypeScript + Panda CSS), la libreria interna dell'azienda.

Token, font e componenti sono copiati **verbatim**. I `.d.ts` accanto ai `.jsx`
sono scritti qui: servono a far parlare TypeScript con dei file JavaScript.

## Perché una copia e non il pacchetto npm

`@aitho/ui` vive sul registry privato `git.aitho.it` e porta con sé Panda CSS.
Metterlo in Workflower vorrebbe dire credenziali del registry nel build Docker e
una seconda pipeline CSS accanto a Tailwind. I componenti di questa cartella
leggono soltanto variabili CSS: nessuna dipendenza, nessun build step.

Se un domani si passa al pacchetto vero, l'API dei componenti è la stessa: basta
cambiare gli import in `ds/index.ts`.

## Cosa c'è

- `tokens/` — colori (tema chiaro e scuro), tipografia, raggi. 88 variabili CSS.
- `fonts/` — la famiglia **quatro** self-hosted (400/700, tondo e corsivo),
  licenziata ad Aitho via Adobe Fonts. `fonts.css` importa anche Space Mono e
  Roboto da Google Fonts.
- `styles.css` — l'unico import da fare: tira dentro font e token.
- `components/` — Button, Checkbox, Input, Label, Pagination, Select, Sidebar,
  Spinner, Stepper (+ Step), Table, TextArea, ToggleSwitch.
- `index.ts` — il barrel: si importa sempre da `../ds`.

Le icone **non** sono copiate: sono `@radix-ui/react-icons`, la stessa
dipendenza che usa la libreria originale. `components/Icons/Icons.ts` le
ri-esporta perché i componenti copiati facciano `from "../Icons/Icons"` come nel
sorgente.

## Regole visive da rispettare (dal readme del design system)

- Un solo colore interattivo per tema: navy `#0000AD` sul chiaro, ciano
  `#00D9EA` sullo scuro. Mai due primari nella stessa schermata.
- Fondali piatti. Nessun gradiente, nessuna texture, nessuna immagine.
- Bordi 1px `--border-color`; raggio di lavoro 7px (`--radius`).
- Focus: sempre `2px solid var(--color-primary)` con `outline-offset: 2px`.
- Ombre rare e morbide, solo su popover, toast e dialog.
- Maiuscole solo per le sigle: etichette e titoli in *sentence case*.

## Tema chiaro / scuro

`data-panda-theme="light" | "dark"` su `<html>`. I componenti leggono solo
variabili CSS, quindi il cambio è immediato.

## Come si aggiorna

Non si modificano i file a mano. Si riportano dal progetto Claude Design (o da
`@aitho/ui`) e si riscrivono i `.d.ts` se l'API è cambiata. Ogni divergenza
consapevole va scritta come commento nel file: al momento ce n'è una sola, il
`menuConfig` della Sidebar (vedi `Sidebar.jsx`).
