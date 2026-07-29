import type { ReactNode, TextareaHTMLAttributes } from "react";
import type { BorderColor } from "../Input/Input";

export interface TextAreaSendButton {
  onClick?: (text: string) => void;
  icon?: ReactNode;
  loading?: boolean;
  loadingElement?: ReactNode;
  disabled?: boolean;
  sendWithEnter?: boolean;
}

export interface TextAreaProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "size"> {
  label?: ReactNode;
  sendButton?: TextAreaSendButton;
  helperText?: ReactNode;
  showCount?: boolean;
  autoResize?: boolean;
  onTextChange?: (text: string) => void;
  onLimitReached?: () => void;
  type?: "outline" | "filled" | "inputForm" | "ghost" | "glass";
  size?: "sm" | "md" | "lg";
  borderColor?: BorderColor;
}

export function TextArea(props: TextAreaProps): JSX.Element;
