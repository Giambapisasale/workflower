import React from "react";

const labelCss = `
.aitho-label {
  display: flex; align-items: center; justify-content: center; position: relative;
  font-family: var(--font-custom), sans-serif;
}
.aitho-label[data-size="sm"] { font-size: var(--font-size-sm); }
.aitho-label[data-size="md"] { font-size: var(--font-size-base); }
.aitho-label[data-size="lg"] { font-size: var(--font-size-lg); }
.aitho-label[data-size="xl"] { font-size: var(--font-size-xl); }
.aitho-label[data-variant="text"] { color: var(--text-primary); }
.aitho-label[data-variant="primary"] { color: var(--color-primary); }
.aitho-label[data-disabled="true"] { color: var(--grey-light); cursor: not-allowed; }
.aitho-label[data-required="primary"] { align-items: start; }
.aitho-label[data-required="primary"]::before { content: " *"; color: var(--color-error); }
.aitho-label[data-required="bold"] { align-items: start; }
.aitho-label[data-required="bold"]::before { content: " *"; font-size: 1.125rem; color: var(--color-error); font-weight: bold; }
.aitho-label[data-required="text"] { align-items: start; justify-content: flex-start; color: var(--color-error); }
.aitho-label[data-required="text"]::before { content: " *"; color: var(--color-error); }
.aitho-label[data-required="textBold"] { align-items: start; justify-content: flex-start; color: var(--color-error); font-weight: bold; }
.aitho-label[data-required="textBold"]::before { content: " *"; color: var(--color-error); font-weight: bold; }
`;

function ensureLabelStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-label-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-label-styles";
    s.textContent = labelCss;
    document.head.appendChild(s);
  }
}

/** Renders an accessible label associated with controls. */
export function Label({
  children,
  size = "md",
  variant = "text",
  required = "none",
  disabled = false,
  ...props
}) {
  ensureLabelStyles();
  const requiredVariant = required === true ? "primary" : required || "none";
  return (
    <label
      className="aitho-label"
      data-size={size}
      data-variant={variant}
      data-required={requiredVariant}
      data-disabled={disabled || undefined}
      {...props}
    >
      {children}
    </label>
  );
}
