import { useNavigate } from "react-router-dom";
import {
  ArrowUpIcon,
  CalendarIcon,
  ChatBubbleIcon,
  FileIcon,
} from "@radix-ui/react-icons";
import { Button } from "../ds";
import { TESTI } from "./testi";
import { BottoneGrande, Colonna } from "./ui";
import { useSessione } from "./sessione";

export default function Home() {
  const naviga = useNavigate();
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
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 24,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 18,
              fontWeight: 700,
              letterSpacing: ".06em",
              textTransform: "uppercase",
            }}
          >
            {TESTI.marchio}
          </div>
          <div style={{ color: "var(--text-secondary)", marginTop: 2 }}>
            {TESTI.benvenuto(primoNome)}
            {dovesono ? ` · ${dovesono}` : ""}
          </div>
        </div>
        <Button variant="transparent" size="sm" compact onClick={esci} style={{ minHeight: 32 }}>
          {TESTI.esci}
        </Button>
      </div>

      <Colonna>
        <BottoneGrande primario icona={ArrowUpIcon} onClick={() => naviga("/op/carica")}>
          {TESTI.bottoneCarica}
        </BottoneGrande>
        <BottoneGrande icona={CalendarIcon} onClick={() => naviga("/op/ore")}>
          {TESTI.bottoneOre}
        </BottoneGrande>
        <BottoneGrande icona={FileIcon} onClick={() => naviga("/op/documenti")}>
          {TESTI.bottoneDocumenti}
        </BottoneGrande>
        <BottoneGrande icona={ChatBubbleIcon} onClick={() => naviga("/op/chiedi")}>
          {TESTI.bottoneChiedi}
        </BottoneGrande>
      </Colonna>

      <p
        style={{
          marginTop: 36,
          textAlign: "center",
          color: "var(--text-secondary)",
          textWrap: "pretty",
        }}
      >
        {TESTI.sottoBenvenuto}
      </p>
    </div>
  );
}
