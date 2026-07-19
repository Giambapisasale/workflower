/**
 * Form generato dallo schema JSON dell'entità (M13). Nessun form scritto a mano
 * per tipo: i campi (testo, numero, data, riferimento con picker, righe/voci
 * ripetibili) nascono dallo schema. Si lega all'INTERO oggetto `dati`, così i
 * campi non mostrati (es. `voce_computo_id`) fanno round-trip senza perdersi.
 * L'autorità di validazione resta il backend (DAL): qui si guida solo l'input.
 */

import type { JsonSchema, VoceEntita } from "./api";

type Opzioni = Record<string, VoceEntita[]>; // tipo → voci per i picker
type Etichette = Record<string, string>; // tipo → etichetta

type Props = {
  schema: JsonSchema;
  valore: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
  riferimenti: Record<string, string>; // campo → tipo referenziato
  opzioni: Opzioni;
  etichette: Etichette;
};

function tipiDi(schema: JsonSchema): string[] {
  return Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];
}

function nullable(schema: JsonSchema): boolean {
  return tipiDi(schema).includes("null");
}

function umana(chiave: string): string {
  const s = chiave.replace(/_id$/, "").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function etichettaCampo(
  campo: string,
  riferimenti: Record<string, string>,
  etichette: Etichette,
): string {
  const tipoRif = riferimenti[campo];
  if (tipoRif) return etichette[tipoRif] ?? umana(campo);
  return umana(campo);
}

function valoreDefault(schema: JsonSchema): unknown {
  if (nullable(schema)) return null;
  const tipi = tipiDi(schema);
  if (tipi.includes("number") || tipi.includes("integer")) return 0;
  if (tipi.includes("array")) return [];
  if (tipi.includes("boolean")) return false;
  return "";
}

function classeInput(): string {
  return "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-sky-400 focus:outline-none";
}

/** Un campo scalare (o riferimento) dello schema. */
function Campo({
  schema,
  valore,
  onChange,
  obbligatorio,
  etichetta,
  tipoRiferimento,
  opzioni,
}: {
  schema: JsonSchema;
  valore: unknown;
  onChange: (v: unknown) => void;
  obbligatorio: boolean;
  etichetta: string;
  tipoRiferimento?: string;
  opzioni: Opzioni;
}) {
  const tipi = tipiDi(schema);
  const puoEsserVuoto = !obbligatorio || nullable(schema);
  const comune = (
    <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
      {etichetta}
      {obbligatorio ? <span className="text-red-500"> *</span> : null}
    </label>
  );

  // Riferimento a un'altra entità → picker
  if (tipoRiferimento) {
    const voci = opzioni[tipoRiferimento] ?? [];
    return (
      <div>
        {comune}
        <select
          className={classeInput()}
          value={(valore as string) ?? ""}
          onChange={(e) => onChange(e.target.value || (puoEsserVuoto ? null : ""))}
        >
          <option value="">{puoEsserVuoto ? "— nessuno —" : "— scegli —"}</option>
          {voci.map((v) => (
            <option key={v.id} value={v.id}>
              {v.titolo ?? v.id}
            </option>
          ))}
        </select>
        {schema.description ? <Nota testo={schema.description} /> : null}
      </div>
    );
  }

  // enum → select
  if (schema.enum) {
    return (
      <div>
        {comune}
        <select
          className={classeInput()}
          value={(valore as string) ?? ""}
          onChange={(e) => onChange(e.target.value || (puoEsserVuoto ? null : ""))}
        >
          {puoEsserVuoto ? <option value="">— nessuno —</option> : null}
          {schema.enum.map((v) => (
            <option key={String(v)} value={String(v)}>
              {String(v)}
            </option>
          ))}
        </select>
      </div>
    );
  }

  // numero
  if (tipi.includes("number") || tipi.includes("integer")) {
    return (
      <div>
        {comune}
        <input
          type="number"
          step="any"
          className={classeInput()}
          value={valore === null || valore === undefined ? "" : String(valore)}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") return onChange(puoEsserVuoto ? null : "");
            const n = Number(raw);
            onChange(Number.isNaN(n) ? raw : n);
          }}
        />
        {schema.description ? <Nota testo={schema.description} /> : null}
      </div>
    );
  }

  // data
  if (schema.format === "date") {
    return (
      <div>
        {comune}
        <input
          type="date"
          className={classeInput()}
          value={(valore as string) ?? ""}
          onChange={(e) => onChange(e.target.value || (puoEsserVuoto ? null : ""))}
        />
      </div>
    );
  }

  // testo (default)
  return (
    <div>
      {comune}
      <input
        type="text"
        className={classeInput()}
        value={(valore as string) ?? ""}
        onChange={(e) => onChange(e.target.value === "" && puoEsserVuoto ? null : e.target.value)}
      />
      {schema.description ? <Nota testo={schema.description} /> : null}
    </div>
  );
}

function Nota({ testo }: { testo: string }) {
  return <p className="mt-1 text-xs text-slate-400">{testo}</p>;
}

/** Un array di oggetti (righe di fattura/DDT, voci di computo): sotto-form ripetibili. */
function CampoArray({
  schema,
  valore,
  onChange,
  etichetta,
  riferimenti,
  opzioni,
  etichette,
}: {
  schema: JsonSchema;
  valore: unknown[];
  onChange: (v: unknown[]) => void;
  etichetta: string;
  riferimenti: Record<string, string>;
  opzioni: Opzioni;
  etichette: Etichette;
}) {
  const item = schema.items ?? {};
  const props = item.properties ?? {};
  const richiesti = new Set(item.required ?? []);
  const righe = Array.isArray(valore) ? valore : [];

  const nuovaRiga = () => {
    const riga: Record<string, unknown> = {};
    for (const [k, s] of Object.entries(props)) riga[k] = valoreDefault(s);
    onChange([...righe, riga]);
  };
  const aggiorna = (i: number, riga: Record<string, unknown>) =>
    onChange(righe.map((r, j) => (j === i ? riga : r)));
  const rimuovi = (i: number) => onChange(righe.filter((_, j) => j !== i));

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
          {etichetta} ({righe.length})
        </span>
        <button
          type="button"
          onClick={nuovaRiga}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          + Aggiungi
        </button>
      </div>
      <div className="space-y-3">
        {righe.map((riga, i) => (
          <div key={i} className="rounded-lg border border-slate-200 bg-white p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs text-slate-400">#{i + 1}</span>
              <button
                type="button"
                onClick={() => rimuovi(i)}
                className="text-xs font-medium text-red-600 hover:underline"
              >
                Rimuovi
              </button>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {Object.entries(props).map(([k, s]) => (
                <Campo
                  key={k}
                  schema={s}
                  valore={(riga as Record<string, unknown>)[k]}
                  onChange={(v) => aggiorna(i, { ...(riga as Record<string, unknown>), [k]: v })}
                  obbligatorio={richiesti.has(k)}
                  etichetta={etichettaCampo(k, riferimenti, etichette)}
                  tipoRiferimento={riferimenti[k]}
                  opzioni={opzioni}
                />
              ))}
            </div>
          </div>
        ))}
        {righe.length === 0 ? (
          <p className="text-sm text-slate-400">Nessuna riga. Usa “+ Aggiungi”.</p>
        ) : null}
      </div>
    </div>
  );
}

export default function CampiSchema({
  schema,
  valore,
  onChange,
  riferimenti,
  opzioni,
  etichette,
}: Props) {
  const props = schema.properties ?? {};
  const richiesti = new Set(schema.required ?? []);
  const imposta = (campo: string, v: unknown) => onChange({ ...valore, [campo]: v });

  return (
    <div className="space-y-4">
      {Object.entries(props).map(([campo, sotto]) => {
        const isArray = tipiDi(sotto).includes("array");
        const etichetta = etichettaCampo(campo, riferimenti, etichette);
        if (isArray && (sotto.items?.properties ?? null)) {
          return (
            <CampoArray
              key={campo}
              schema={sotto}
              valore={(valore[campo] as unknown[]) ?? []}
              onChange={(v) => imposta(campo, v)}
              etichetta={etichetta}
              riferimenti={riferimenti}
              opzioni={opzioni}
              etichette={etichette}
            />
          );
        }
        return (
          <Campo
            key={campo}
            schema={sotto}
            valore={valore[campo]}
            onChange={(v) => imposta(campo, v)}
            obbligatorio={richiesti.has(campo)}
            etichetta={etichetta}
            tipoRiferimento={riferimenti[campo]}
            opzioni={opzioni}
          />
        );
      })}
    </div>
  );
}
