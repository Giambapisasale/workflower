import React from "react";
import { CheckIcon } from "../Icons/Icons";

const stepperCss = `
.aitho-stepper__root { display: flex; width: 100%; gap: 1rem; font-family: var(--font-custom), sans-serif; }
.aitho-stepper__root[data-orientation="horizontal"] { flex-direction: row; align-items: center; justify-content: space-between; }
.aitho-stepper__root[data-orientation="vertical"] { flex-direction: column; align-items: stretch; }
.aitho-stepper__step { display: flex; align-items: center; gap: 0.5rem; flex: 1; }
.aitho-stepper__root[data-orientation="horizontal"] .aitho-stepper__step { flex-direction: column; align-items: center; }
.aitho-stepper__root[data-orientation="vertical"] .aitho-stepper__step { flex-direction: row; }
.aitho-stepper__separator { flex: 1; border: none; margin: 0; }
.aitho-stepper__root[data-orientation="horizontal"] .aitho-stepper__separator { width: 100%; height: 1px; min-width: 1.25rem; }
.aitho-stepper__root[data-orientation="vertical"] .aitho-stepper__separator { width: 1px; height: 100%; margin-left: 1rem; min-height: 1.25rem; }
.aitho-stepper__content { font-size: var(--font-size-sm); font-weight: 500; }
.aitho-stepper__root[data-orientation="horizontal"] .aitho-stepper__content { text-align: center; }
.aitho-stepper__root[data-orientation="vertical"] .aitho-stepper__content { text-align: left; }
.aitho-stepper__indicator {
  display: flex; align-items: center; justify-content: center;
  width: 2rem; height: 2rem; border-radius: var(--radius-full);
  border: 2px solid; flex-shrink: 0; transition: all 200ms; box-sizing: border-box;
}
.aitho-stepper__step[data-status="active"] .aitho-stepper__indicator { border-color: var(--color-primary); background: var(--color-primary); color: var(--text-on-primary); }
.aitho-stepper__step[data-status="active"] .aitho-stepper__content { color: var(--color-primary); }
.aitho-stepper__step[data-status="complete"] .aitho-stepper__indicator { border-color: var(--color-success); background: var(--color-success); color: var(--text-on-primary); }
.aitho-stepper__step[data-status="complete"] .aitho-stepper__content { color: var(--color-success); }
.aitho-stepper__step[data-status="incomplete"] .aitho-stepper__indicator { border-color: var(--border-color); background: var(--background-primary); color: var(--text-secondary); }
.aitho-stepper__step[data-status="incomplete"] .aitho-stepper__content { color: var(--text-secondary); }
.aitho-stepper__separator[data-status="complete"] { background: var(--color-success); }
.aitho-stepper__separator[data-status="active"],
.aitho-stepper__separator[data-status="incomplete"] { background: var(--border-color); }
`;

function ensureStepperStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-stepper-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-stepper-styles";
    s.textContent = stepperCss;
    document.head.appendChild(s);
  }
}

/** A step of the Stepper. */
export function Step({ children }) {
  return <React.Fragment>{children}</React.Fragment>;
}

/** A navigation bar that guides users through the steps of a task. */
export function Stepper({ index, children, orientation = "horizontal", ...props }) {
  ensureStepperStyles();
  const validChildren = React.Children.toArray(children).filter(React.isValidElement);

  const renderProp = (prop, context) => {
    if (!prop) return null;
    return typeof prop === "function" ? prop(context) : prop;
  };

  return (
    <div className="aitho-stepper__root" data-orientation={orientation} {...props}>
      {validChildren.map((child, i) => {
        const isLast = i === validChildren.length - 1;
        const isActive = i === index;
        const isComplete = i < index;
        const status = isActive ? "active" : isComplete ? "complete" : "incomplete";
        const context = { isActive, isComplete, step: i + 1 };

        const renderStatus = () => {
          if (isComplete) return renderProp(child.props.complete, context) || <CheckIcon />;
          if (isActive) return renderProp(child.props.active, context) || context.step;
          return renderProp(child.props.incomplete, context) || context.step;
        };

        return (
          <React.Fragment key={`stepper-step-${i}`}>
            <div className="aitho-stepper__step" data-status={status}>
              <div
                className="aitho-stepper__indicator"
                aria-current={isActive ? "step" : undefined}
              >
                {renderStatus()}
              </div>
              <div className="aitho-stepper__content">{child.props.children}</div>
            </div>
            {!isLast && <hr className="aitho-stepper__separator" data-status={status} />}
          </React.Fragment>
        );
      })}
    </div>
  );
}
