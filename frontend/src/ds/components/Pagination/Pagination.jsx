import React, { useCallback } from "react";
import { Button } from "../Button/Button";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  DoubleArrowLeftIcon,
  DoubleArrowRightIcon,
} from "../Icons/Icons";

const paginationCss = `
.aitho-pagination__root { display: flex; gap: 0.25rem; align-items: center; justify-content: center; border-radius: 0.375rem; padding: 0.375rem; font-family: var(--font-custom), sans-serif; }
`;

function ensurePaginationStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-pagination-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-pagination-styles";
    s.textContent = paginationCss;
    document.head.appendChild(s);
  }
}

/** Provides ability to change the visible page of a data set. */
export function Pagination({
  page = 1,
  totalItems,
  onPageChange,
  itemsPerPage = 10,
  showFirstLast = false,
  showPrevNext = false,
  showPageNumbers = true,
  hideNavigationOnDisabled = false,
  maxVisiblePages = 5,
  firstButtonContent,
  lastButtonContent,
  variant = "primary",
  ...props
}) {
  ensurePaginationStyles();
  const totalPages = Math.ceil(totalItems / itemsPerPage);

  const resolveCurrentPage = useCallback(() => {
    if (!page || page < 1) return 1;
    if (page > totalPages) return totalPages;
    return page;
  }, [page, totalPages]);

  const [currentPage, setCurrentPage] = React.useState(resolveCurrentPage());

  React.useEffect(() => {
    setCurrentPage(resolveCurrentPage());
  }, [page, resolveCurrentPage]);

  const isFirstPage = currentPage === 1;
  const isLastPage = currentPage === totalPages;

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage);
      if (onPageChange) onPageChange(newPage);
    }
  };

  const pagesPerSide = Math.floor(maxVisiblePages / 2);
  let numberIndex = currentPage - pagesPerSide;
  const pagesLeft = totalPages - currentPage;
  if (pagesLeft < pagesPerSide) numberIndex -= pagesPerSide - pagesLeft;
  numberIndex = Math.max(1, numberIndex);
  const pages = [];
  for (let i = 0; i < maxVisiblePages && numberIndex <= totalPages; numberIndex++, i++) {
    pages.push(numberIndex);
  }

  const shouldShowNavButton = (showCondition, disabledCondition) => {
    if (!showCondition) return false;
    if (disabledCondition && hideNavigationOnDisabled) return false;
    return true;
  };

  return (
    <div className="aitho-pagination__root" {...props}>
      {shouldShowNavButton(showFirstLast, isFirstPage) && (
        <Button variant={variant} onClick={() => handlePageChange(1)} disabled={isFirstPage} size="xs">
          {firstButtonContent ?? <DoubleArrowLeftIcon height={21} />}
        </Button>
      )}
      {shouldShowNavButton(showPrevNext, isFirstPage) && (
        <Button variant={variant} onClick={() => handlePageChange(currentPage - 1)} disabled={isFirstPage} size="xs">
          <ChevronLeftIcon height={21} />
        </Button>
      )}
      {showPageNumbers &&
        pages.map((p) => (
          <Button
            variant={variant}
            key={p}
            onClick={() => handlePageChange(p)}
            size="xs"
            disabled={currentPage === p}
          >
            {p.toString()}
          </Button>
        ))}
      {shouldShowNavButton(showPrevNext, isLastPage) && (
        <Button variant={variant} onClick={() => handlePageChange(currentPage + 1)} disabled={isLastPage} size="xs">
          <ChevronRightIcon height={21} />
        </Button>
      )}
      {shouldShowNavButton(showFirstLast, isLastPage) && (
        <Button variant={variant} size="xs" onClick={() => handlePageChange(totalPages)} disabled={isLastPage}>
          {lastButtonContent ?? <DoubleArrowRightIcon height={21} />}
        </Button>
      )}
    </div>
  );
}
