import type { HTMLAttributes, ReactNode } from "react";
import type { PaginationProps } from "../Pagination/Pagination";

export type SortDirection = "ascend" | "descend";

/** Una riga della tabella: serve `id` per selezione e chiavi React. */
export interface TableRow {
  id: string | number;
  [key: string]: unknown;
}

export interface TableColumn<R extends TableRow = TableRow> {
  title: ReactNode;
  dataIndex: string;
  render?: (value: never, row: R, rowIndex: number) => ReactNode;
  onSort?: (direction: SortDirection) => void;
  sortIcons?: {
    ascendIcon?: ReactNode;
    descendIcon?: ReactNode;
    undefinedIcon?: ReactNode;
  };
}

export interface TableProps<R extends TableRow = TableRow>
  extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
  columns?: TableColumn<R>[];
  data?: R[];
  /** Totale righe lato server, se la paginazione non è locale. */
  numberOfItems?: number;
  showPagination?: boolean;
  rowsPerPage?: number;
  paginationProps?: Partial<PaginationProps>;
  isLoading?: boolean;
  paginationPosition?: "top" | "bottom" | "topLeft" | "topRight" | "bottomLeft" | "bottomRight";
  variant?: "primary" | "secondary";
  striped?: boolean;
  sideBorders?: boolean;
  bottomBorders?: boolean;
  onPageChange?: (page: number) => void;
  checkable?: boolean;
  onSelectionChange?: (rows: R[]) => void;
  selectedRows?: (string | number)[];
}

export function Table<R extends TableRow = TableRow>(props: TableProps<R>): JSX.Element;
