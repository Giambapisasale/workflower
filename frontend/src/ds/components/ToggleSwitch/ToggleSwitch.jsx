import React, { useState } from "react";

const toggleCss = `
.aitho-switch {
  width: 2.625rem; height: 1.563rem; border-radius: 9999px; position: relative;
  -webkit-tap-highlight-color: rgba(0,0,0,0); transition: background-color 200ms ease-in-out;
  cursor: pointer; overflow: hidden; background-color: var(--background-tertiary);
  border: none; padding: 0; display: inline-block;
}
.aitho-switch[data-state="checked"] { background-color: var(--color-primary); }
.aitho-switch:disabled { cursor: not-allowed; background-color: grey; }
.aitho-switch:disabled[data-state="checked"] { background-color: var(--color-primary-disabled); }
.aitho-switch:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; border-radius: var(--radius-sm); }
.aitho-switch__thumb {
  display: block; width: 1.313rem; height: 1.313rem; background-color: var(--light);
  border-radius: var(--radius-full); box-shadow: 0 2px 2px var(--dark);
  transition: transform 100ms; transform: translateX(2px); will-change: transform;
}
.aitho-switch[data-state="checked"] .aitho-switch__thumb { transform: translateX(19px); }
.aitho-switch:disabled .aitho-switch__thumb { box-shadow: none; }

.aitho-switch[data-size="sm"] { width: 2.25rem; height: 1.25rem; }
.aitho-switch[data-size="sm"] .aitho-switch__thumb { width: 1rem; height: 1rem; }
.aitho-switch[data-size="sm"][data-state="checked"] .aitho-switch__thumb { transform: translateX(17px); }
.aitho-switch[data-size="lg"] { width: 3.125rem; height: 1.875rem; }
.aitho-switch[data-size="lg"] .aitho-switch__thumb { width: 1.625rem; height: 1.625rem; }
.aitho-switch[data-size="lg"][data-state="checked"] .aitho-switch__thumb { transform: translateX(22px); }
`;

function ensureToggleStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-switch-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-switch-styles";
    s.textContent = toggleCss;
    document.head.appendChild(s);
  }
}

/** A control that allows the user to toggle between checked and not checked. */
export function ToggleSwitch({
  size = "md",
  checked,
  defaultChecked = false,
  onCheckedChange,
  disabled,
  ...props
}) {
  ensureToggleStyles();
  const isControlled = typeof checked !== "undefined";
  const [internal, setInternal] = useState(defaultChecked);
  const isChecked = isControlled ? checked : internal;

  const toggle = () => {
    const next = !isChecked;
    if (!isControlled) setInternal(next);
    if (onCheckedChange) onCheckedChange(next);
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isChecked}
      className="aitho-switch"
      data-state={isChecked ? "checked" : "unchecked"}
      data-size={size}
      disabled={disabled}
      onClick={toggle}
      {...props}
    >
      <span className="aitho-switch__thumb"></span>
    </button>
  );
}
