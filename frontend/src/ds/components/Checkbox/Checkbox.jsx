import React, { useState } from "react";
import { CheckIcon } from "../Icons/Icons";

const checkboxCss = `
.aitho-checkbox {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  overflow: hidden; border-radius: 0.375rem; position: relative; cursor: pointer;
  padding: 0; font-family: var(--font-custom), sans-serif;
}
.aitho-checkbox:disabled { cursor: not-allowed; opacity: 0.5; background-color: var(--color-primary-disabled) !important; border-color: var(--color-primary-disabled) !important; }
.aitho-checkbox:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.aitho-checkbox[data-state="checked"] { animation: aithoCheck 300ms ease-in-out; }
.aitho-checkbox[data-state="unchecked"] { animation: aithoUncheck 300ms ease-in-out; }
@keyframes aithoCheck { 0% { transform: scale(1); } 50% { transform: scale(0.8); } 100% { transform: scale(1); } }
@keyframes aithoUncheck { 0% { transform: scale(1); } 50% { transform: scale(0.8); } 100% { transform: scale(1); } }

.aitho-checkbox[data-size="sm"] { height: 1.25rem; width: 1.25rem; font-size: var(--font-size-sm); }
.aitho-checkbox[data-size="md"] { height: 2.25rem; width: 2.25rem; font-size: var(--font-size-base); }
.aitho-checkbox[data-size="lg"] { height: 2.75rem; width: 2.75rem; font-size: var(--font-size-lg); }
.aitho-checkbox[data-size="xl"] { height: 3rem; width: 3rem; font-size: var(--font-size-xl); }

.aitho-checkbox[data-variant="primary"] { background: var(--background-primary); border: 1px solid var(--color-primary); }
.aitho-checkbox[data-variant="secondary"] { background: var(--background-primary); border: 1px solid var(--color-attention); }
.aitho-checkbox[data-variant="white"] { background: var(--white); border: 1px solid var(--checkbox-square-color); }

.aitho-checkbox[data-border="solid"] { border-style: solid; }
.aitho-checkbox[data-border="dashed"] { border-style: dashed; }
.aitho-checkbox[data-border="none"] { border: none; background-color: var(--color-primary-disabled); }

.aitho-checkbox[data-required="primary"] { border-color: var(--color-error); }

.aitho-checkbox__indicator { position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.aitho-checkbox[data-variant="primary"] .aitho-checkbox__indicator { background: var(--color-primary); }
.aitho-checkbox[data-variant="secondary"] .aitho-checkbox__indicator { background: var(--color-attention); }
.aitho-checkbox[data-variant="white"] .aitho-checkbox__indicator { background: var(--white); }
.aitho-checkbox[data-required="primary"] .aitho-checkbox__indicator { background: var(--color-error); }

.aitho-checkbox__icon { display: flex; align-items: center; justify-content: center; flex-shrink: 0; overflow: hidden; position: relative; width: 100%; height: 100%; }
.aitho-checkbox[data-variant="primary"] .aitho-checkbox__icon,
.aitho-checkbox[data-variant="secondary"] .aitho-checkbox__icon,
.aitho-checkbox[data-required="primary"] .aitho-checkbox__icon { color: var(--text-on-primary); }
.aitho-checkbox[data-variant="white"] .aitho-checkbox__icon { color: var(--checkbox-square-color); }
.aitho-checkbox:disabled .aitho-checkbox__icon { color: var(--grey-light); }

.aitho-checkbox__square { width: 60%; height: 60%; background-color: var(--text-on-primary); border-radius: 0.25rem; }
.aitho-checkbox:disabled .aitho-checkbox__square { background-color: var(--grey-light); }
`;

function ensureCheckboxStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-checkbox-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-checkbox-styles";
    s.textContent = checkboxCss;
    document.head.appendChild(s);
  }
}

/** A control that allows the user to toggle between checked and not checked. */
export function Checkbox({
  disabled,
  size = "sm",
  variant = "primary",
  border = "solid",
  required = "none",
  squareIcon = false,
  checked,
  defaultChecked = false,
  onCheckedChange,
  ...props
}) {
  ensureCheckboxStyles();
  const isControlled = typeof checked !== "undefined";
  const [internalChecked, setInternalChecked] = useState(defaultChecked);
  const isChecked = isControlled ? checked : internalChecked;
  const requiredVariant = required === true ? "primary" : required || "none";

  const toggle = () => {
    const next = !isChecked;
    if (!isControlled) setInternalChecked(next);
    if (onCheckedChange) onCheckedChange(next);
  };

  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={isChecked}
      className="aitho-checkbox"
      data-state={isChecked ? "checked" : "unchecked"}
      data-size={size}
      data-variant={variant}
      data-border={border}
      data-required={requiredVariant}
      disabled={disabled}
      onClick={toggle}
      {...props}
    >
      {isChecked && (
        <span className="aitho-checkbox__indicator">
          {squareIcon ? (
            <span className="aitho-checkbox__icon">
              <span className="aitho-checkbox__square"></span>
            </span>
          ) : (
            <CheckIcon className="aitho-checkbox__icon" />
          )}
        </span>
      )}
    </button>
  );
}
