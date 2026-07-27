/** Hub della gestione manuale (M13): i tipi gestibili, per anagrafiche e documenti. */

import { Link } from "react-router-dom";
import { admin, type MetaTipo } from "./api";
import { useCarica } from "./formato";
import { Badge, Card, Errore, Stato } from "./ui";

function Riquadri({ tipi }: { tipi: MetaTipo[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      {tipi.map((t) => (
        <Link
          key={t.tipo}
          to={`/admin/dati/${t.tipo}`}
          className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-sky-300 hover:shadow"
        >
          <div className="text-base font-semibold text-slate-800">{t.etichetta}</div>
          <div className="mt-1 text-xs text-slate-400">apri e gestisci →</div>
        </Link>
      ))}
    </div>
  );
}

export default function Dati() {
  const { dati, errore, inCorso } = useCarica(() => admin.entitiesMeta());
  const scartati = useCarica(() => admin.scartati());
  if (inCorso) return <Stato>Carico…</Stato>;
  if (errore || !dati) return <Errore>{errore ?? "Nessun dato"}</Errore>;
  const master = dati.filter((t) => t.is_master);
  const documenti = dati.filter((t) => !t.is_master);
  const quantiScartati = scartati.dati?.length ?? 0;

  return (
    <>
      <div className="mb-4">
        <h1 className="text-lg font-bold">Gestione dati</h1>
        <p className="text-sm text-slate-500">
          Inserisci, correggi o elimina i dati a mano. Ogni modifica resta tracciata.
        </p>
      </div>
      <Card titolo="Anagrafiche">
        <Riquadri tipi={master} />
      </Card>
      <Card titolo="Documenti gestionali">
        <Riquadri tipi={documenti} />
      </Card>
      <Card titolo="Scartati">
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
          <Link
            to="/admin/dati/scartati"
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-sky-300 hover:shadow"
          >
            <div className="flex items-center gap-2 text-base font-semibold text-slate-800">
              Inserimenti scartati
              {quantiScartati > 0 ? <Badge tono="giallo">{quantiScartati}</Badge> : null}
            </div>
            <div className="mt-1 text-xs text-slate-400">apri e ripristina →</div>
          </Link>
          <p className="max-w-md">
            I documenti che l'ufficio ha ripudiato. Non contano nei costi e non sono cancellati:
            da lì si ripristinano.
          </p>
        </div>
      </Card>
    </>
  );
}
