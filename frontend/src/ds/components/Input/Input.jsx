import React, { useState, useRef } from "react";
import { Label } from "../Label/Label";
import {
  Cross1Icon,
  EyeNoneIcon,
  EyeOpenIcon,
  MagnifyingGlassIcon,
} from "../Icons/Icons";

const inputCss = `
.aitho-input__wrapper { display: flex; align-items: center; gap: 0.938rem; width: 100%; font-family: var(--font-custom), sans-serif; }
.aitho-input__required { color: var(--color-error); }
.aitho-input__container { position: relative; width: 100%; }
.aitho-input__icon {
  position: absolute; z-index: 20; color: var(--text-secondary);
  height: 1.063rem; width: 1.063rem; cursor: pointer;
  right: 0.625rem; top: 50%; transform: translateY(-50%);
  display: inline-flex; align-items: center; justify-content: center;
  background: none; border: none; padding: 0;
}
.aitho-input__icon:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; border-radius: var(--radius-sm); }
.aitho-input__field {
  border: 1px solid var(--border-color);
  background-color: var(--background-primary);
  color: var(--text-primary);
  padding: 0.5rem;
  min-width: 15.625rem; width: 100%; max-height: 2.5rem;
  transition: all 300ms;
  font-family: inherit; font-size: 1rem;
  box-sizing: border-box;
}
.aitho-input__field:disabled { cursor: not-allowed; opacity: 0.5; }
.aitho-input__field:hover:not(:disabled) { background: var(--background-secondary); }
.aitho-input__field:focus { background: var(--background-secondary); }
.aitho-input__field:active:not(:disabled) { background: var(--background-tertiary); }
.aitho-input__field:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; border-radius: var(--radius-sm); }
.aitho-input__field::placeholder { color: var(--background-popup); }
.aitho-input__field::-webkit-calendar-picker-indicator { cursor: pointer; border-radius: 0.25rem; margin-right: 0.125rem; filter: invert(0.7); }
.aitho-input__field[data-border-color="base"] { border-color: var(--border-color); }
.aitho-input__field[data-border-color="primary"] { border-color: var(--color-primary); }
.aitho-input__field[data-border-color="error"] { border-color: var(--color-error); }
.aitho-input__field[data-border-radius="none"] { border-radius: 0; }
.aitho-input__field[data-border-radius="rounded"] { border-radius: var(--radius); }
.aitho-input__error { color: var(--color-error); font-size: 0.75rem; font-family: var(--font-custom), sans-serif; }
`;

function ensureInputStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-input-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-input-styles";
    s.textContent = inputCss;
    document.head.appendChild(s);
  }
}

let inputIdCounter = 0;

/** Provides an input bar of the chosen type. */
export const Input = React.forwardRef(function Input(
  {
    label,
    required,
    errorMessage,
    error,
    inputSearch,
    onChange,
    borderRadius = "rounded",
    borderColor = "base",
    type = "text",
    value,
    ...props
  },
  ref,
) {
  ensureInputStyles();
  const uniqueId = useRef(`aitho-input-${++inputIdCounter}`).current;
  const internalRef = useRef(null);
  const inputRef = ref ?? internalRef;

  const [val, setVal] = useState(value ?? "");
  const [prevValue, setPrevValue] = useState(value);
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);

  if (value !== prevValue) {
    setPrevValue(value);
    setVal(value ?? "");
  }

  const onValChange = (e) => {
    setVal(e.target.value);
    if (onChange) onChange(e);
  };

  const deleteValue = () => {
    setVal("");
    if (onChange) onChange({ target: { value: "" } });
    if (inputRef.current) inputRef.current.focus();
  };

  return (
    <React.Fragment>
      <div className="aitho-input__wrapper">
        {label && (
          <Label htmlFor={uniqueId}>
            {required && <span className="aitho-input__required">*</span>}
            {label}:
          </Label>
        )}
        <div className="aitho-input__container">
          <input
            id={uniqueId}
            ref={inputRef}
            className="aitho-input__field"
            data-border-color={error ? "error" : borderColor}
            data-border-radius={borderRadius}
            value={val}
            onChange={onValChange}
            type={isPasswordVisible ? "text" : type}
            {...props}
          />
          {inputSearch && type === "search" && (
            val === "" ? (
              <MagnifyingGlassIcon className="aitho-input__icon" />
            ) : (
              <button type="button" className="aitho-input__icon" onClick={deleteValue}>
                <Cross1Icon />
              </button>
            )
          )}
          {type === "password" && String(val).length > 0 && (
            <button
              type="button"
              className="aitho-input__icon"
              onClick={() => setIsPasswordVisible(!isPasswordVisible)}
            >
              {isPasswordVisible ? <EyeNoneIcon /> : <EyeOpenIcon />}
            </button>
          )}
        </div>
      </div>
      {error && <span className="aitho-input__error">{errorMessage}</span>}
    </React.Fragment>
  );
});
