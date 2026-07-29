import React, { useState, useMemo } from "react";
import { Button } from "../Button/Button";
import { Checkbox } from "../Checkbox/Checkbox";
import { Pagination } from "../Pagination/Pagination";
import { Spinner } from "../Spinner/Spinner";
import { CaretSortIcon, CaretDownIcon, CaretUpIcon } from "../Icons/Icons";

const tableCss = `
.aitho-table__root { display: block; width: 100%; font-family: var(--font-custom), sans-serif; }
.aitho-table__root[data-variant="primary"] { color: var(--text-primary); }
.aitho-table__root[data-variant="secondary"] { color: var(--text-primary); }
.aitho-table__table { display: table; width: 100%; border-collapse: collapse; }
.aitho-table__header {
  font-weight: bold; text-align: left; padding: 0.75rem; position: relative;
}
.aitho-table__root[data-variant="primary"] .aitho-table__header { color: var(--text-on-primary); background: var(--color-primary); }
.aitho-table__root[data-variant="secondary"] .aitho-table__header { color: var(--text-on-primary); background: var(--background-popup); }
.aitho-table__header:not(:last-child)::after {
  content: ""; position: absolute; top: 25%; bottom: 25%; right: 0; width: 1px;
  background: var(--border-color);
}
.aitho-table__header:first-child { border-top-left-radius: var(--radius); }
.aitho-table__header:last-child { border-top-right-radius: var(--radius); }
.aitho-table__header-content { display: flex; align-items: center; gap: 0.5rem; }
.aitho-table__sort-icons { color: var(--text-on-primary); display: inline-flex; }
.aitho-table__row { display: table-row; }
.aitho-table__root[data-variant="primary"] tbody .aitho-table__row { background: var(--table-base-color); }
.aitho-table__root[data-variant="secondary"] tbody .aitho-table__row { color: var(--text-primary); background: var(--background-tertiary); }
.aitho-table__root[data-bottom-borders="true"] tbody .aitho-table__row { border-bottom: 1px solid var(--color-primary); }
.aitho-table__root[data-striped="true"][data-variant="primary"] tbody tr:nth-child(even) { background: var(--table-striped-color); }
.aitho-table__root[data-striped="true"][data-variant="secondary"] tbody tr:nth-child(even) { background: var(--background-secondary); }
.aitho-table__container[data-side-borders="true"] {
  border: 1px solid var(--color-primary); border-bottom: none;
  border-top-left-radius: 0.5rem; border-top-right-radius: 0.5rem;
}
.aitho-table__cell { display: table-cell; padding: 0.75rem; }
.aitho-table__pagination { display: flex; justify-content: center; padding: 0.625rem 0; margin-top: 0.313rem; }
.aitho-table__pagination[data-position$="left"] { justify-content: flex-start; }
.aitho-table__pagination[data-position$="right"] { justify-content: flex-end; }
`;

function ensureTableStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-table-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-table-styles";
    s.textContent = tableCss;
    document.head.appendChild(s);
  }
}

/** A table that displays rows of data with sorting, selection and pagination. */
export function Table({
  columns = [],
  data = [],
  numberOfItems,
  showPagination,
  rowsPerPage,
  paginationProps,
  isLoading,
  paginationPosition = "bottom",
  variant = "primary",
  striped = false,
  sideBorders = false,
  bottomBorders = true,
  onPageChange,
  checkable = false,
  onSelectionChange,
  selectedRows = [],
  ...props
}) {
  ensureTableStyles();
  const [currentPage, setCurrentPage] = useState(1);
  const [sortDirections, setSortDirections] = useState({});
  const [selectedRowIds, setSelectedRowIds] = useState(selectedRows);

  const handleSort = (column) => {
    setSortDirections((prev) => {
      const newDirections = {};
      const currentDirection = prev[column.dataIndex];
      const newDirection = currentDirection === "ascend" ? "descend" : "ascend";
      newDirections[column.dataIndex] = newDirection;
      setTimeout(() => {
        if (column.onSort) column.onSort(newDirection);
      }, 0);
      return newDirections;
    });
  };

  const handlePageChange = (newPage) => {
    setCurrentPage(newPage);
    if (onPageChange) onPageChange(newPage);
  };

  const paginatedData = useMemo(() => {
    if (showPagination && rowsPerPage && data.length > rowsPerPage) {
      return data.slice((currentPage - 1) * rowsPerPage, currentPage * rowsPerPage);
    }
    return data;
  }, [showPagination, rowsPerPage, data, currentPage]);

  const notifySelection = (newSelection) => {
    if (onSelectionChange) {
      onSelectionChange(data.filter((item) => newSelection.includes(item.id)));
    }
  };

  const handleRowSelect = (rowId) => {
    setSelectedRowIds((prev) => {
      const newSelection = prev.includes(rowId)
        ? prev.filter((id) => id !== rowId)
        : [...prev, rowId];
      notifySelection(newSelection);
      return newSelection;
    });
  };

  const areAllRowsSelected =
    paginatedData.length > 0 && paginatedData.every((row) => selectedRowIds.includes(row.id));

  const handleSelectAll = () => {
    const paginatedIds = paginatedData.map((row) => row.id);
    setSelectedRowIds((prev) => {
      let newSelection;
      if (areAllRowsSelected) {
        newSelection = prev.filter((id) => !paginatedIds.includes(id));
      } else {
        newSelection = Array.from(new Set([...prev, ...paginatedIds]));
      }
      notifySelection(newSelection);
      return newSelection;
    });
  };

  if (isLoading) return <Spinner />;

  const getSortIcon = (column, direction) => {
    if (column.sortIcons) {
      if (direction === "ascend") return column.sortIcons.ascendIcon;
      if (direction === "descend") return column.sortIcons.descendIcon;
      return column.sortIcons.undefinedIcon;
    }
    if (direction === "ascend") return <CaretDownIcon />;
    if (direction === "descend") return <CaretUpIcon />;
    return <CaretSortIcon />;
  };

  const renderPagination = () => (
    <div className="aitho-table__pagination" data-position={paginationPosition}>
      <Pagination
        totalItems={numberOfItems ?? data.length}
        itemsPerPage={rowsPerPage ?? data.length}
        onPageChange={handlePageChange}
        showPrevNext={true}
        variant={variant === "primary" ? "outline" : "neutral"}
        {...paginationProps}
      />
    </div>
  );

  return (
    <div
      className="aitho-table__root"
      data-variant={variant}
      data-striped={striped ? "true" : "false"}
      data-bottom-borders={bottomBorders ? "true" : "false"}
      {...props}
    >
      {showPagination && paginationPosition.startsWith("top") && renderPagination()}
      <div className="aitho-table__container" data-side-borders={sideBorders ? "true" : "false"}>
        <table className="aitho-table__table">
          <thead>
            <tr className="aitho-table__row">
              {checkable && (
                <th className="aitho-table__header">
                  <Checkbox
                    squareIcon
                    variant="white"
                    checked={areAllRowsSelected}
                    onCheckedChange={handleSelectAll}
                    size="sm"
                  />
                </th>
              )}
              {columns.map((column) => (
                <th key={column.dataIndex} className="aitho-table__header">
                  <div className="aitho-table__header-content">
                    {column.title}
                    {column.onSort && (
                      <Button
                        variant="transparent"
                        compact
                        layout="vertical"
                        onClick={() => handleSort(column)}
                      >
                        <div className="aitho-table__sort-icons">
                          {getSortIcon(column, sortDirections[column.dataIndex])}
                        </div>
                      </Button>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedData.map((row, rowIndex) => (
              <tr key={row.id} className="aitho-table__row">
                {checkable && (
                  <td className="aitho-table__cell" style={{ padding: "0.75rem" }}>
                    <Checkbox
                      squareIcon
                      variant="white"
                      checked={selectedRowIds.includes(row.id)}
                      onCheckedChange={() => handleRowSelect(row.id)}
                      size="sm"
                    />
                  </td>
                )}
                {columns.map((column) => (
                  <td key={column.dataIndex} className="aitho-table__cell">
                    {column.render
                      ? column.render(row[column.dataIndex], row, rowIndex)
                      : row[column.dataIndex]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showPagination && !paginationPosition.startsWith("top") && renderPagination()}
    </div>
  );
}
