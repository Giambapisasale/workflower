import type { HTMLAttributes, ReactNode } from "react";

export interface StepContext {
  isActive: boolean;
  isComplete: boolean;
  step: number;
}

export type StepSlot = ReactNode | ((context: StepContext) => ReactNode);

export interface StepProps {
  children?: ReactNode;
  active?: StepSlot;
  complete?: StepSlot;
  incomplete?: StepSlot;
}

export interface StepperProps extends HTMLAttributes<HTMLDivElement> {
  /** Indice (0-based) del passo attivo. */
  index: number;
  orientation?: "horizontal" | "vertical";
  children?: ReactNode;
}

export function Step(props: StepProps): JSX.Element;
export function Stepper(props: StepperProps): JSX.Element;
