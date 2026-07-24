/** Costruzione del contesto per il form schema-driven di un tipo entità:
 * schema + mappa dei riferimenti + etichette + opzioni dei picker. Condiviso da
 * EntitaForm, RevisioneDettaglio (Modifica dati) e RiferimentiDaCompletare. */

import { ErroreApi } from "../shared/api";
import { admin, type JsonSchema, type MetaTipo, type VoceEntita } from "./api";

export type MetaForm = {
  metaTipo: MetaTipo;
  schema: JsonSchema;
  riferimenti: Record<string, string>; // campo → tipo referenziato
  etichette: Record<string, string>; // tipo → etichetta
  opzioni: Record<string, VoceEntita[]>; // tipo referenziato → voci esistenti
  tipi: MetaTipo[];
};

export async function caricaMetaForm(tipo: string): Promise<MetaForm> {
  const tipi = await admin.entitiesMeta();
  const metaTipo = tipi.find((t) => t.tipo === tipo);
  if (!metaTipo) throw new ErroreApi(`Tipo non gestibile: ${tipo}`, 404);
  const etichette = Object.fromEntries(tipi.map((t) => [t.tipo, t.etichetta]));
  const tipiRif = [...new Set(Object.values(metaTipo.riferimenti))];
  const coppie = await Promise.all(
    tipiRif.map(async (t) => [t, await admin.entitiesLista(t)] as const),
  );
  const opzioni = Object.fromEntries(coppie) as Record<string, VoceEntita[]>;
  return { metaTipo, schema: metaTipo.schema, riferimenti: metaTipo.riferimenti, etichette, opzioni, tipi };
}
