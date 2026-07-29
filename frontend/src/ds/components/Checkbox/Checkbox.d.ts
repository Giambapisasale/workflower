import type { ButtonHTMLAttributes } from "react";

export interface CheckboxProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange" | "defaultChecked"> {
  size?: "sm" | "md" | "lg" | "xl";
  variant?: "primary" | "secondary" | "white";
  border?: "solid" | "dashed" | "none";
  required?: boolean | "none" | "primary";
  squareIcon?: boolean;
  checked?: boolean;
  defaultChecked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

export function Checkbox(props: CheckboxProps): JSX.Element;
