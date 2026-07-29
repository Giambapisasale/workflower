import type { HTMLAttributes } from "react";

export type SpinnerType =
  | "linearFlashingDots"
  | "spinningSlashes"
  | "circularFlashingDots"
  | "rotatingSquares"
  | "rotatingDots";

export interface SpinnerProps extends HTMLAttributes<HTMLDivElement> {
  size?: "sm" | "md" | "lg" | "xl";
  type?: SpinnerType;
}

export function Spinner(props: SpinnerProps): JSX.Element;
