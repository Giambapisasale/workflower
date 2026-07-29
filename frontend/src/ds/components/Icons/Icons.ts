/** Icone del design system Aitho: @radix-ui/react-icons, 15x15, currentColor.
 *  Il design system ne riproduce un sottoinsieme di 37 glifi; in codice di
 *  produzione si importano da qui, che è il pacchetto npm originale. */

import type { ComponentType, CSSProperties } from "react";

export * from "@radix-ui/react-icons";

/** I props che ogni icona Radix accetta. Non `SVGProps`: le icone Radix
 *  dichiarano `children?: never`, quindi il tipo va tenuto stretto. */
export type PropsIcona = {
  width?: string | number;
  height?: string | number;
  className?: string;
  color?: string;
  style?: CSSProperties;
  "aria-hidden"?: boolean | "true" | "false";
};

/** Un'icona da passare come componente (non come elemento). */
export type Icona = ComponentType<PropsIcona>;
