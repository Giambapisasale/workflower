import type { ButtonHTMLAttributes } from "react";

export interface ToggleSwitchProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange" | "defaultChecked"> {
  size?: "sm" | "md" | "lg";
  checked?: boolean;
  defaultChecked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

export function ToggleSwitch(props: ToggleSwitchProps): JSX.Element;
