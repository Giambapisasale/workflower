import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Icona } from "../Icons/Icons";

/** Icona passata ai componenti Aitho: si avvolge il componente in { data }. */
export type AithoIcon = { data: Icona };

export type ButtonVariant =
  | "primary"
  | "transparent"
  | "outline"
  | "neutral"
  | "outlineError"
  | "error";
export type ButtonSize = "xxs" | "xs" | "sm" | "md" | "lg" | "xl";
export type ButtonRadius = "flat" | "rounded" | "pills";

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon?: AithoIcon;
  iconPosition?: "start" | "end";
  children?: ReactNode;
  size?: ButtonSize;
  borderRadius?: ButtonRadius;
  variant?: ButtonVariant;
  layout?: "horizontal" | "vertical";
  compact?: boolean;
}

export function Button(props: ButtonProps): JSX.Element;
