import { TESTI } from "./testi";
import { BottoneLink } from "./ui";
import { useSessione } from "./sessione";

export default function Home() {
  const { sessione, esci } = useSessione();
  const { nome, cantieri } = sessione.utente;
  const primoNome = nome.split(" ")[0];
  const dovesono =
    cantieri.length === 0
      ? ""
      : cantieri.length === 1
        ? `cantiere ${cantieri[0].nome}`
        : `${cantieri.length} cantieri`;

  return (
    <div>
      <div className="mb-5 flex items-start justify-between">
        <div>
          <div className="text-lg font-bold tracking-wide">WORKFLOWER</div>
          <div className="text-neutral-500">
            {TESTI.benvenuto(primoNome)}
            {dovesono ? ` · ${dovesono}` : ""}
          </div>
        </div>
        <button
          type="button"
          className="min-h-[48px] px-2 py-2 text-neutral-400 underline"
          onClick={esci}
        >
          {TESTI.esci}
        </button>
      </div>

      <div className="space-y-4">
        <BottoneLink a="/op/carica" icona="📷" variante="primario">
          {TESTI.bottoneCarica}
        </BottoneLink>
        <BottoneLink a="/op/documenti" icona="📄">
          {TESTI.bottoneDocumenti}
        </BottoneLink>
        <BottoneLink a="/op/chiedi" icona="💬">
          {TESTI.bottoneChiedi}
        </BottoneLink>
      </div>

      <p className="mt-8 text-center text-neutral-500">{TESTI.sottoBenvenuto}</p>
    </div>
  );
}
