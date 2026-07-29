import type { InputHTMLAttributes, ReactNode } from "react";

export type BorderColor = "base" | "primary" | "error";

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: ReactNode;
  required?: boolean;
  errorMessage?: ReactNode;
  error?: boolean;
  inputSearch?: boolean;
  borderRadius?: "none" | "rounded";
  borderColor?: BorderColor;
}

export declare const Input: React.ForwardRefExoticComponent<
  InputProps & React.RefAttributes<HTMLInputElement>
>;
