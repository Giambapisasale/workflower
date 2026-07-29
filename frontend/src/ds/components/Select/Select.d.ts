import type { HTMLAttributes, ReactNode } from "react";
import type { BorderColor } from "../Input/Input";

export interface SelectItem {
  value: string;
  /** Testo mostrato; se assente si usa value. */
  textValue?: string;
  icon?: ReactNode;
  disabled?: boolean;
}

export interface SelectProps extends Omit<HTMLAttributes<HTMLDivElement>, "defaultValue"> {
  borderColor?: BorderColor;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  variant?: "primary" | "secondary";
  items?: SelectItem[];
  placeholder?: ReactNode;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  /** Quante opzioni mostrare prima dello scroll. */
  optionsShows?: number;
  searchable?: boolean;
  searchablePlaceholder?: string;
  disabled?: boolean;
}

export function Select(props: SelectProps): JSX.Element;
