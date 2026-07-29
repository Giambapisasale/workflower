import React from "react";
import { ArrowRightIcon } from "../Icons/Icons";
import { Spinner } from "../Spinner/Spinner";

const textAreaCss = `
.aitho-ta__root { display: flex; flex-direction: column; width: 100%; position: relative; height: auto; align-items: stretch; transition: opacity 0.2s ease; border: none; margin: 0; padding: 0; font-family: var(--font-custom), sans-serif; }
.aitho-ta__label { color: var(--text-secondary); font-size: var(--font-size-sm); font-weight: 500; line-height: 1.25; margin-bottom: 0.25rem; transition: color 0.2s ease; }
.aitho-ta__wrapper { position: relative; width: 100%; display: flex; align-items: stretch; }
.aitho-ta__textarea {
  width: 100%; min-height: 4.375rem; max-height: 13.125rem; resize: none;
  border-radius: var(--radius); background-color: var(--background-primary);
  color: var(--text-primary); border: 1px solid var(--border-color);
  font-size: 1rem; padding: 1rem; padding-right: 3rem; box-sizing: border-box;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); font-family: inherit;
}
.aitho-ta__textarea::placeholder { color: var(--text-secondary); opacity: 0.6; }
.aitho-ta__textarea:hover:not(:disabled) { background-color: var(--background-secondary); border-color: var(--color-primary); transform: translateY(-1px); }
.aitho-ta__textarea:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; border-radius: var(--radius-sm); }
.aitho-ta__textarea:disabled { cursor: not-allowed; opacity: 0.6; background-color: var(--background-tertiary); }
.aitho-ta__textarea:disabled:hover { transform: none; box-shadow: none; }

/* sizes */
.aitho-ta__root[data-size="sm"] .aitho-ta__textarea { padding: 0.75rem; padding-right: 2.75rem; font-size: var(--font-size-sm); min-height: 3.75rem; border-radius: calc(var(--radius) * 0.8); }
.aitho-ta__root[data-size="sm"] .aitho-ta__label { font-size: var(--font-size-xs); }
.aitho-ta__root[data-size="lg"] .aitho-ta__textarea { padding: 1.25rem; padding-right: 3.25rem; font-size: var(--font-size-lg); min-height: 6.25rem; border-radius: calc(var(--radius) * 1.2); }
.aitho-ta__root[data-size="lg"] .aitho-ta__label { font-size: var(--font-size-base); }

/* type variants */
.aitho-ta__root[data-type="outline"] .aitho-ta__textarea { background-color: var(--background-primary); border-color: var(--color-primary); }
.aitho-ta__root[data-type="outline"] .aitho-ta__label { color: var(--text-primary); }
.aitho-ta__root[data-type="filled"] .aitho-ta__textarea { background-color: var(--background-secondary); border-color: transparent; }
.aitho-ta__root[data-type="filled"] .aitho-ta__textarea:hover:not(:disabled) { background-color: var(--background-tertiary); border-color: transparent; }
.aitho-ta__root[data-type="filled"] .aitho-ta__label { color: var(--text-primary); }
.aitho-ta__root[data-type="inputForm"] .aitho-ta__textarea { background-color: var(--background-primary); border-color: var(--border-color); }
.aitho-ta__root[data-type="inputForm"] .aitho-ta__textarea:hover:not(:disabled) { background-color: var(--background-secondary); border-color: var(--border-color) !important; transform: translateY(0px) !important; }
.aitho-ta__root[data-type="inputForm"] .aitho-ta__label { color: var(--text-primary); }
.aitho-ta__root[data-type="ghost"] .aitho-ta__textarea { background-color: transparent; border-color: transparent; }
.aitho-ta__root[data-type="ghost"] .aitho-ta__textarea:hover:not(:disabled) { background-color: var(--background-secondary); border-color: transparent; }
.aitho-ta__root[data-type="ghost"] .aitho-ta__label { color: var(--text-secondary); }
.aitho-ta__root[data-type="glass"] .aitho-ta__textarea { backdrop-filter: blur(8px); border: none; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06); }

/* border colors */
.aitho-ta__root[data-border-color="base"] .aitho-ta__textarea { border-color: var(--border-color); }
.aitho-ta__root[data-border-color="primary"] .aitho-ta__textarea { border-color: var(--color-primary); }
.aitho-ta__root[data-border-color="error"] .aitho-ta__textarea { border-color: var(--color-error); }

.aitho-ta__footer { display: flex; justify-content: space-between; align-items: center; padding: 0.125rem 0.25rem; transition: opacity 0.2s ease; }
.aitho-ta__counter { font-size: var(--font-size-sm); color: var(--text-secondary); margin-left: auto; transition: color 0.2s ease; }
.aitho-ta__counter[data-state="char-length-exceeded"] { color: var(--color-error); font-weight: 500; }
.aitho-ta__indicator { display: flex; align-items: center; gap: 0.25rem; color: var(--text-secondary); font-size: var(--font-size-sm); flex: 1; transition: color 0.2s ease; }
.aitho-ta__send {
  position: absolute; right: 0.75rem; top: 50%; transform: translateY(-50%);
  display: inline-flex; align-items: center; justify-content: center;
  width: 2rem; height: 2rem; padding: 0; background-color: transparent; border: none;
  border-radius: calc(var(--radius) * 0.8); color: var(--color-primary); cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); outline: none;
}
.aitho-ta__send:hover:not(:disabled) { color: var(--color-primary-hover); background-color: var(--background-overlay); transform: translateY(-50%) scale(1.05); }
.aitho-ta__send:active:not(:disabled) { color: var(--color-primary-active); transform: translateY(-50%) scale(0.95); }
.aitho-ta__send:disabled { opacity: 0.5; cursor: not-allowed; color: var(--text-secondary); }
.aitho-ta__root[data-size="sm"] .aitho-ta__send { width: 1.75rem; height: 1.75rem; right: 8px; }
.aitho-ta__root[data-size="sm"] .aitho-ta__send svg { width: 1rem; height: 1rem; }
.aitho-ta__root[data-size="lg"] .aitho-ta__send { width: 2.25rem; height: 2.25rem; right: 1rem; }
.aitho-ta__root[data-size="lg"] .aitho-ta__send svg { width: 1.25rem; height: 1.25rem; }
`;

function ensureTextAreaStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-ta-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-ta-styles";
    s.textContent = textAreaCss;
    document.head.appendChild(s);
  }
}

let taIdCounter = 0;

/** Enhanced textarea with auto-resize, character count and send button. */
export function TextArea({
  label,
  sendButton,
  helperText,
  maxLength,
  showCount = false,
  autoResize = false,
  value,
  defaultValue,
  onChange,
  onTextChange,
  onLimitReached,
  type = "outline",
  size = "md",
  borderColor = "base",
  ...props
}) {
  ensureTextAreaStyles();
  const isControlled = typeof value !== "undefined";
  const [uncontrolledText, setUncontrolledText] = React.useState(
    (defaultValue ?? "").toString(),
  );
  const text = isControlled ? String(value) : uncontrolledText;
  const uniqueId = React.useRef(`aitho-ta-${++taIdCounter}`).current;
  const textareaRef = React.useRef(null);

  const adjustHeight = React.useCallback(() => {
    if (!textareaRef.current || !autoResize) return;
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${textareaRef.current.scrollHeight + 2}px`;
  }, [autoResize]);

  const handleSendButtonClick = () => {
    if (!sendButton || !sendButton.onClick) return;
    sendButton.onClick(text);
    if (!isControlled) setUncontrolledText("");
    if (autoResize) adjustHeight();
  };

  const handleChange = (e) => {
    const newText = maxLength ? e.target.value.slice(0, maxLength) : e.target.value;
    if (!isControlled) setUncontrolledText(newText);
    if (autoResize) adjustHeight();
    if (onChange) onChange(e);
    if (onTextChange) onTextChange(newText);
    if (maxLength && newText.length === maxLength && onLimitReached) onLimitReached();
  };

  const handleKeyDown = (e) => {
    if (sendButton && sendButton.sendWithEnter && e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendButtonClick();
      if (textareaRef.current) textareaRef.current.blur();
    }
  };

  return (
    <fieldset
      className="aitho-ta__root"
      data-type={type}
      data-size={size}
      data-border-color={borderColor}
    >
      {label && (
        <label htmlFor={uniqueId} className="aitho-ta__label">
          {label}
        </label>
      )}
      <div className="aitho-ta__wrapper">
        <textarea
          ref={textareaRef}
          id={uniqueId}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          className="aitho-ta__textarea"
          maxLength={maxLength}
          {...props}
        />
        {sendButton && (
          <button
            type="button"
            className="aitho-ta__send"
            onClick={handleSendButtonClick}
            disabled={text.length === 0 || sendButton.disabled || sendButton.loading}
          >
            {sendButton.loading
              ? (sendButton.loadingElement ?? <Spinner type="circularFlashingDots" size="sm" />)
              : (sendButton.icon ?? <ArrowRightIcon />)}
          </button>
        )}
      </div>
      <footer className="aitho-ta__footer">
        {helperText && <small className="aitho-ta__indicator">{helperText}</small>}
        {showCount && (
          <small
            className="aitho-ta__counter"
            data-state={maxLength && text.length >= maxLength ? "char-length-exceeded" : ""}
          >
            {maxLength ? `${text.length}/${maxLength}` : text.length}
          </small>
        )}
      </footer>
    </fieldset>
  );
}
