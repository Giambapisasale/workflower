import type { HTMLAttributes, ReactNode } from "react";

export interface SidebarItem {
  key: string;
  text: ReactNode;
  icon?: ReactNode;
  onClick?: () => void;
  selected?: boolean;
  disabled?: boolean;
  subItems?: SidebarItem[];
  /** Intestazione di sezione: non cliccabile, ignora icon/onClick/selected. */
  heading?: boolean;
}

export interface SidebarProps extends HTMLAttributes<HTMLElement> {
  behaviour?: "permanent" | "toggle" | "hover";
  anchor?: "left" | "right";
  open?: boolean;
  /** Collassata a 4rem, si apre al passaggio del mouse. */
  expandOnHover?: boolean;
  header?: ReactNode;
  footer?: ReactNode;
  items?: SidebarItem[];
  onOpenChange?: (open: boolean) => void;
  children?: ReactNode;
  lastSelectedKey?: string;
  variant?: "primary" | "secondary" | "tertiary";
  itemsLoading?: boolean;
  position?: "static" | "fixed";
}

export function Sidebar(props: SidebarProps): JSX.Element;
