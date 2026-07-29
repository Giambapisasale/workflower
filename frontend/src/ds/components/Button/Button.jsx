import React from "react";

const buttonCss = `
.aitho-btn {
  font-family: var(--font-custom), sans-serif;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 300ms;
  display: inline-flex;
  align-items: center;
  border: none;
  background: none;
  color: var(--text-primary);
}
.aitho-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}
.aitho-btn[data-full-start="true"] { display: grid; grid-template-columns: 0.2fr 1fr; }
.aitho-btn[data-full-end="true"] { display: grid; grid-template-columns: 1fr 0.2fr; }
.aitho-btn__icon { display: inline-flex; align-items: center; justify-content: end; padding: 0 0.5rem 0 0.5rem; }
.aitho-btn__content { white-space: nowrap; display: flex; align-items: center; justify-content: center; }

/* sizes */
.aitho-btn[data-size="xxs"] { font-size: var(--font-size-2xs); padding: 0; }
.aitho-btn[data-size="xxs"] .aitho-btn__icon { width: 1.5rem; height: 1.5rem; }
.aitho-btn[data-size="xs"] { font-size: var(--font-size-sm); padding: 0; }
.aitho-btn[data-size="xs"] .aitho-btn__icon { width: 1.75rem; height: 1.75rem; }
.aitho-btn[data-size="sm"] { font-size: var(--font-size-sm); padding: 0.25rem 0.5rem; }
.aitho-btn[data-size="sm"] .aitho-btn__icon { width: 2rem; height: 2rem; }
.aitho-btn[data-size="md"] { font-size: var(--font-size-base); padding: 0.5rem 1rem; }
.aitho-btn[data-size="md"] .aitho-btn__icon { width: 2.25rem; height: 2.25rem; }
.aitho-btn[data-size="lg"] { font-size: var(--font-size-lg); padding: 0.75rem 1.5rem; }
.aitho-btn[data-size="lg"] .aitho-btn__icon { width: 2.625rem; height: 2.625rem; }
.aitho-btn[data-size="xl"] { font-size: var(--font-size-xl); padding: 1rem 2rem; }
.aitho-btn[data-size="xl"] .aitho-btn__icon { width: 3rem; height: 3rem; }

/* radius */
.aitho-btn[data-radius="flat"] { border-radius: 0; }
.aitho-btn[data-radius="rounded"] { border-radius: var(--radius); }
.aitho-btn[data-radius="pills"] { border-radius: var(--radius-full); }

/* variants */
.aitho-btn[data-variant="primary"] { background-color: var(--color-primary); color: var(--text-on-primary); border-color: var(--border-color); }
.aitho-btn[data-variant="primary"]:hover:not(:disabled) { background-color: var(--color-primary-hover); }
.aitho-btn[data-variant="primary"]:active:not(:disabled) { background-color: var(--color-primary-opacity-50); }
.aitho-btn[data-variant="primary"] .aitho-btn__icon { color: var(--text-on-primary); }

.aitho-btn[data-variant="transparent"] { background-color: transparent; color: var(--text-primary); }
.aitho-btn[data-variant="transparent"]:hover:not(:disabled) { background-color: rgba(0, 0, 0, 0.05); }
.aitho-btn[data-variant="transparent"]:active:not(:disabled) { background-color: rgba(0, 0, 0, 0.2); }
.aitho-btn[data-variant="transparent"] .aitho-btn__icon { color: var(--text-primary); }

.aitho-btn[data-variant="outline"] { background-color: transparent; color: var(--text-primary); border: 1px solid var(--color-primary); }
.aitho-btn[data-variant="outline"]:hover:not(:disabled) { background-color: rgba(0, 0, 0, 0.1); }
.aitho-btn[data-variant="outline"]:active:not(:disabled) { background-color: var(--color-primary-opacity-20); }
.aitho-btn[data-variant="outline"] .aitho-btn__icon { color: var(--color-primary); }

.aitho-btn[data-variant="neutral"] { background-color: var(--background-tertiary); color: var(--text-primary); }
.aitho-btn[data-variant="neutral"]:hover:not(:disabled) { background-color: rgba(0, 0, 0, 0.3); }
.aitho-btn[data-variant="neutral"]:active:not(:disabled) { background-color: rgba(0, 0, 0, 0.5); }
.aitho-btn[data-variant="neutral"] .aitho-btn__icon { color: var(--text-primary); }

.aitho-btn[data-variant="outlineError"] { background-color: transparent; color: var(--color-error); border: 1px solid var(--color-error); }
.aitho-btn[data-variant="outlineError"]:hover:not(:disabled) { background-color: rgba(255, 0, 0, 0.05); }
.aitho-btn[data-variant="outlineError"]:active:not(:disabled) { background-color: rgba(255, 0, 0, 0.2); }
.aitho-btn[data-variant="outlineError"] .aitho-btn__icon { color: var(--color-error); }

.aitho-btn[data-variant="error"] { background-color: var(--color-error); color: var(--text-on-primary); border: 1px solid var(--color-error); }
.aitho-btn[data-variant="error"]:hover:not(:disabled) { background-color: var(--color-error-hover); }
.aitho-btn[data-variant="error"]:active:not(:disabled) { background-color: var(--color-error-opacity-80); }
.aitho-btn[data-variant="error"] .aitho-btn__icon { color: var(--text-on-primary); }

/* layout */
.aitho-btn[data-layout="horizontal"] { flex-direction: row; }
.aitho-btn[data-layout="vertical"] { flex-direction: column; padding: 0.75rem 0.75rem; }
.aitho-btn[data-layout="horizontal"] .aitho-btn__content { padding: 0.25rem 1rem; }
.aitho-btn[data-layout="vertical"] .aitho-btn__content { padding: 0.25rem 0.25rem; }

/* disabled */
.aitho-btn:disabled { cursor: not-allowed; opacity: 0.5; }
.aitho-btn[data-variant="primary"]:disabled { background-color: var(--color-primary-disabled); }
.aitho-btn[data-variant="transparent"]:disabled { background-color: transparent; border-color: transparent; }
.aitho-btn[data-variant="outline"]:disabled { background-color: var(--color-primary-disabled); }
.aitho-btn[data-variant="outline"]:disabled .aitho-btn__icon { color: var(--text-primary); }
.aitho-btn[data-variant="neutral"]:disabled,
.aitho-btn[data-variant="outlineError"]:disabled,
.aitho-btn[data-variant="error"]:disabled { background-color: var(--color-primary-disabled); }

/* compact */
.aitho-btn[data-compact="true"] { width: auto; height: auto; padding: 0; }
`;

function ensureButtonStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-btn-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-btn-styles";
    s.textContent = buttonCss;
    document.head.appendChild(s);
  }
}

/**
 * Aitho Button — a button means an operation (or a series of operations).
 */
export function Button({
  icon,
  iconPosition = "start",
  children,
  size = "md",
  borderRadius = "rounded",
  variant = "primary",
  layout = "horizontal",
  disabled = false,
  compact = false,
  ...props
}) {
  ensureButtonStyles();

  const renderIcon = () => {
    if (!icon) return null;
    const IconComponent = icon.data;
    return <IconComponent className="aitho-btn__icon" />;
  };

  return (
    <button
      className="aitho-btn"
      data-size={size}
      data-radius={borderRadius}
      data-variant={variant}
      data-layout={layout}
      data-compact={compact || undefined}
      data-full-start={icon && children && iconPosition === "start" ? "true" : undefined}
      data-full-end={icon && children && iconPosition === "end" ? "true" : undefined}
      disabled={disabled}
      {...props}
    >
      {iconPosition === "start" && renderIcon()}
      {children && <span className="aitho-btn__content">{children}</span>}
      {iconPosition === "end" && renderIcon()}
    </button>
  );
}
