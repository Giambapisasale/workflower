import type { HTMLAttributes, ReactNode } from "react";
import type { ButtonVariant } from "../Button/Button";

export interface PaginationProps extends HTMLAttributes<HTMLDivElement> {
  page?: number;
  totalItems: number;
  onPageChange?: (page: number) => void;
  itemsPerPage?: number;
  showFirstLast?: boolean;
  showPrevNext?: boolean;
  showPageNumbers?: boolean;
  hideNavigationOnDisabled?: boolean;
  maxVisiblePages?: number;
  firstButtonContent?: ReactNode;
  lastButtonContent?: ReactNode;
  variant?: ButtonVariant;
}

export function Pagination(props: PaginationProps): JSX.Element;
