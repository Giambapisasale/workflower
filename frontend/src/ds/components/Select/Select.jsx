import React, { useState, useRef, useEffect } from "react";
import { ChevronDownIcon } from "../Icons/Icons";
import { Input } from "../Input/Input";

const selectCss = `
.aitho-select__root { position: relative; display: inline-block; font-family: var(--font-custom), sans-serif; }
.aitho-select__trigger {
  display: flex; align-items: center; justify-content: space-between;
  border-radius: var(--radius); padding: 0 0.938rem 0 0.5rem; gap: 0.5rem;
  width: 100%; cursor: pointer; overflow: hidden; color: var(--text-primary);
  background-color: var(--background-primary); border: 1px solid var(--border-color);
  font-family: inherit;
}
.aitho-select__trigger:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; border-radius: var(--radius-sm); }
.aitho-select__trigger:hover:not(:disabled) { background-color: var(--background-secondary); border-color: var(--border-color); }
.aitho-select__trigger:active:not(:disabled) { background-color: var(--background-tertiary); }
.aitho-select__trigger:disabled { cursor: not-allowed; background-color: var(--background-secondary); color: var(--text-secondary); opacity: 0.6; }
.aitho-select__trigger[data-border-color="primary"] { border-color: var(--color-primary); }
.aitho-select__trigger[data-border-color="error"] { border-color: var(--color-error); }
.aitho-select__trigger-content { display: flex; flex-direction: row; align-items: center; gap: 0.5rem; flex: 1; }
.aitho-select__placeholder { color: var(--background-popup); }
.aitho-select__chevron { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.aitho-select__chevron svg { stroke-width: 0.013rem; stroke: currentColor; width: 100%; height: 100%; }

.aitho-select__content {
  color: var(--text-primary); position: absolute; top: calc(100% + 4px); left: 0; right: 0;
  overflow-y: auto; border-radius: var(--radius); border: 1px solid var(--background-contrast);
  padding: 0.438rem; z-index: 9999; background-color: var(--background-secondary);
  box-sizing: border-box;
}
.aitho-select__content[data-border-color="primary"] { border-color: var(--color-primary); }
.aitho-select__content[data-border-color="error"] { border-color: var(--border-color); }
.aitho-select__search { margin-bottom: 0.5rem; }
.aitho-select__item {
  position: relative; padding: 0 0.75rem; height: 2.188rem; cursor: pointer; outline: none;
  display: flex; align-items: center; width: 100%; border-radius: var(--radius);
  margin: 0.125rem 0; box-sizing: border-box; background: none; border: none;
  color: inherit; font-family: inherit; font-size: inherit; text-align: left;
}
.aitho-select__item:first-child { margin-top: 0; }
.aitho-select__item:last-child { margin-bottom: 0; }
.aitho-select__item[data-state="checked"] { background-color: var(--color-primary-disabled); color: var(--text-on-primary); }
.aitho-select__item[data-state="checked"]:hover { background-color: var(--color-primary-hover); color: var(--text-on-primary); }
.aitho-select__item:hover:not([data-state="checked"]):not(:disabled) { background-color: var(--color-primary-disabled); color: var(--text-on-primary); }
.aitho-select__item:disabled { cursor: not-allowed; opacity: 0.5; color: var(--text-secondary); }
.aitho-select__item-content { display: flex; flex-direction: row; align-items: center; gap: 0.5rem; height: 100%; }

/* sizes */
.aitho-select__root[data-size="xs"] .aitho-select__trigger { height: 1.875rem; font-size: 0.875rem; min-width: 7.5rem; width: 7.5rem; }
.aitho-select__root[data-size="xs"] .aitho-select__chevron { height: 0.875rem; width: 0.875rem; }
.aitho-select__root[data-size="xs"] .aitho-select__content { font-size: 0.875rem; }
.aitho-select__root[data-size="sm"] .aitho-select__trigger { height: 1.875rem; font-size: 0.875rem; min-width: 12.5rem; }
.aitho-select__root[data-size="sm"] .aitho-select__chevron { height: 0.875rem; width: 0.875rem; }
.aitho-select__root[data-size="sm"] .aitho-select__content { font-size: 0.875rem; }
.aitho-select__root[data-size="md"] .aitho-select__trigger { height: 2.5rem; font-size: 1rem; min-width: 15.625rem; }
.aitho-select__root[data-size="md"] .aitho-select__chevron { height: 1.125rem; width: 1.125rem; }
.aitho-select__root[data-size="md"] .aitho-select__content { font-size: 1rem; }
.aitho-select__root[data-size="lg"] .aitho-select__trigger { min-height: 3.125rem; font-size: 1.125rem; min-width: 18.75rem; }
.aitho-select__root[data-size="lg"] .aitho-select__chevron { height: 1.375rem; width: 1.375rem; }
.aitho-select__root[data-size="xl"] .aitho-select__trigger { min-height: 3.75rem; font-size: 1.25rem; min-width: 21.875rem; }
.aitho-select__root[data-size="xl"] .aitho-select__chevron { height: 1.625rem; width: 1.625rem; }
`;

function ensureSelectStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-select-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-select-styles";
    s.textContent = selectCss;
    document.head.appendChild(s);
  }
}

/** Displays a list of options for the user to pick from, triggered by a button. */
export function Select({
  borderColor = "base",
  size = "md",
  variant = "primary",
  items = [],
  placeholder,
  value,
  defaultValue,
  onValueChange,
  optionsShows,
  searchable = false,
  searchablePlaceholder,
  disabled,
  ...props
}) {
  ensureSelectStyles();
  const isControlled = typeof value !== "undefined";
  const [internalValue, setInternalValue] = useState(defaultValue);
  const currentValue = isControlled ? value : internalValue;
  const [isOpen, setIsOpen] = useState(false);
  const [searchOption, setSearchOption] = useState("");
  const rootRef = useRef(null);

  const selectedItem = items.find((item) => item.value === currentValue);
  const maxHeight = optionsShows ? `${optionsShows * 2.188}rem` : "43.75rem";

  useEffect(() => {
    const onDocClick = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setIsOpen(false);
        setSearchOption("");
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const pick = (item) => {
    if (item.disabled) return;
    if (!isControlled) setInternalValue(item.value);
    if (onValueChange) onValueChange(item.value);
    setIsOpen(false);
    setSearchOption("");
  };

  const filteredItems = [
    ...items.filter((item) => item.value === currentValue),
    ...items.filter(
      (item) =>
        item.value !== currentValue &&
        String(item.textValue ?? item.value)
          .toLowerCase()
          .includes(searchOption.toLowerCase()),
    ),
  ];

  return (
    <div className="aitho-select__root" data-size={size} ref={rootRef} {...props}>
      <button
        type="button"
        className="aitho-select__trigger"
        data-border-color={borderColor}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="aitho-select__trigger-content">
          {selectedItem && selectedItem.icon && (
            <span className="aitho-select__chevron">{selectedItem.icon}</span>
          )}
          {selectedItem ? (
            <span>{selectedItem.textValue ?? selectedItem.value}</span>
          ) : (
            <span className="aitho-select__placeholder">{placeholder}</span>
          )}
        </div>
        <span className="aitho-select__chevron">
          <ChevronDownIcon />
        </span>
      </button>
      {isOpen && (
        <div
          className="aitho-select__content"
          data-border-color={borderColor}
          role="listbox"
          style={{ maxHeight }}
        >
          {searchable && (
            <div className="aitho-select__search">
              <Input
                inputSearch
                autoFocus
                placeholder={searchablePlaceholder}
                type="search"
                value={searchOption}
                onChange={(e) => setSearchOption(e.target.value)}
                borderColor={borderColor}
              />
            </div>
          )}
          {filteredItems.map((item) => (
            <button
              type="button"
              key={item.value}
              role="option"
              aria-selected={item.value === currentValue}
              className="aitho-select__item"
              data-state={item.value === currentValue ? "checked" : "unchecked"}
              disabled={item.disabled}
              style={
                item.value === currentValue && searchOption.trim().length > 0
                  ? { display: "none" }
                  : undefined
              }
              onClick={() => pick(item)}
            >
              <div className="aitho-select__item-content">
                {item.icon && <span>{item.icon}</span>}
                <span>{item.textValue ?? item.value}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
