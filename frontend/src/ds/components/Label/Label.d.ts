import type { LabelHTMLAttributes, ReactNode } from "react";

export interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  children?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
  variant?: "text" | "primary";
  required?: boolean | "none" | "primary" | "bold" | "text" | "textBold";
  disabled?: boolean;
}

export function Label(props: LabelProps): JSX.Element;
