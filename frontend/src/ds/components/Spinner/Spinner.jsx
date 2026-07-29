import React from "react";

const spinnerCss = `
.aitho-spinner__root { display: flex; align-items: center; justify-content: center; width: 3rem; height: 3rem; }
.aitho-spinner__root[data-size="sm"] { font-size: var(--font-size-sm); transform: scale(0.5); }
.aitho-spinner__root[data-size="md"] { font-size: var(--font-size-base); transform: scale(1); }
.aitho-spinner__root[data-size="lg"] { font-size: var(--font-size-lg); transform: scale(1.5); }
.aitho-spinner__root[data-size="xl"] { font-size: var(--font-size-xl); transform: scale(2); }

.aitho-spinner__el[data-type="linearFlashingDots"] {
  width: 1rem; height: 1rem; border-radius: 50%;
  background-color: var(--background-primary); position: relative;
  animation: aithoSpinnerLinearFlashingDots 1s ease-out infinite alternate;
}
@keyframes aithoSpinnerLinearFlashingDots {
  0% { background-color: var(--accent); box-shadow: 32px 0 var(--accent), -32px 0 var(--color-primary); }
  50% { background-color: var(--color-primary); box-shadow: 32px 0 var(--accent), -32px 0 var(--accent); }
  100% { background-color: var(--accent); box-shadow: 32px 0 var(--color-primary), -32px 0 var(--accent); }
}

.aitho-spinner__el[data-type="spinningSlashes"] {
  transform: rotateZ(45deg); perspective: 62.5rem; border-radius: 50%;
  width: 100%; height: 100%; color: var(--color-primary); position: relative; display: block;
}
.aitho-spinner__el[data-type="spinningSlashes"]::before,
.aitho-spinner__el[data-type="spinningSlashes"]::after {
  content: ""; display: block; position: absolute; top: 0; left: 0;
  width: inherit; height: inherit; border-radius: 50%;
  animation: aithoSpinnerSpinningSlashes 1s linear infinite;
}
.aitho-spinner__el[data-type="spinningSlashes"]::before { transform: rotateX(70deg); }
.aitho-spinner__el[data-type="spinningSlashes"]::after { color: var(--accent); transform: rotateY(70deg); animation-delay: .4s; }
@keyframes aithoSpinnerSpinningSlashes {
  0%, 100% { box-shadow: .2em 0px 0 0px; }
  12% { box-shadow: .2em .2em 0 0; }
  25% { box-shadow: 0 .2em 0 0px; }
  37% { box-shadow: -.2em .2em 0 0; }
  50% { box-shadow: -.2em 0 0 0; }
  62% { box-shadow: -.2em -.2em 0 0; }
  75% { box-shadow: 0px -.2em 0 0; }
  87% { box-shadow: .2em -.2em 0 0; }
}

.aitho-spinner__el[data-type="circularFlashingDots"] {
  color: var(--color-primary); width: 1rem; height: 1rem; border-radius: 50%;
  position: relative; animation: aithoSpinnerCircularFlashingDots 1.3s infinite linear;
  transform: translateZ(0); display: block;
}
@keyframes aithoSpinnerCircularFlashingDots {
  0%, 100% { box-shadow: 0 -1.5em 0 0.1em, 1em -1em 0 0em, 1.5em 0 0 -0.5em, 1em 1em 0 -0.5em, 0 1.5em 0 -0.5em, -1em 1em 0 -0.5em, -1.5em 0 0 -0.5em, -1em -1em 0 0; }
  12.5% { box-shadow: 0 -1.5em 0 0, 1em -1em 0 0.1em, 1.5em 0 0 0, 1em 1em 0 -0.5em, 0 1.5em 0 -0.5em, -1em 1em 0 -0.5em, -1.5em 0 0 -0.5em, -1em -1em 0 -0.5em; }
  25% { box-shadow: 0 -1.5em 0 -0.5em, 1em -1em 0 0, 1.5em 0 0 0.1em, 1em 1em 0 0, 0 1.5em 0 -0.5em, -1em 1em 0 -0.5em, -1.5em 0 0 -0.5em, -1em -1em 0 -0.5em; }
  37.5% { box-shadow: 0 -1.5em 0 -0.5em, 1em -1em 0 -0.5em, 1.5em 0em 0 0, 1em 1em 0 0.1em, 0 1.5em 0 0em, -1em 1em 0 -0.5em, -1.5em 0em 0 -0.5em, -1em -1em 0 -0.5em; }
  50% { box-shadow: 0 -1.5em 0 -0.5em, 1em -1em 0 -0.5em, 1.5em 0 0 -0.5em, 1em 1em 0 0em, 0 1.5em 0 0.1em, -1em 1em 0 0, -1.5em 0em 0 -0.5em, -1em -1em 0 -0.5em; }
  62.5% { box-shadow: 0 -1.5em 0 -0.5em, 1em -1em 0 -0.5em, 1.5em 0 0 -0.5em, 1em 1em 0 -0.5em, 0 1.5em 0 0, -1em 1em 0 0.1em, -1.5em 0 0 0, -1em -1em 0 -0.5em; }
  75% { box-shadow: 0em -1.5em 0 -0.5em, 1em -1em 0 -0.5em, 1.5em 0em 0 -0.5em, 1em 1em 0 -0.5em, 0 1.5em 0 -0.5em, -1em 1em 0 0, -1.5em 0em 0 0.1em, -1em -1em 0 0; }
  87.5% { box-shadow: 0em -1.5em 0 0, 1em -1em 0 -0.5em, 1.5em 0em 0 -0.5em, 1em 1em 0 -0.5em, 0em 1.5em 0 -0.5em, -1em 1em 0 -0.5em, -1.5em 0em 0 0, -1em -1em 0 0.1em; }
}

.aitho-spinner__el[data-type="rotatingSquares"] {
  position: relative; display: block;
  background-image: linear-gradient(var(--accent) 1rem, transparent 0), linear-gradient(var(--color-primary) 1rem, transparent 0), linear-gradient(var(--color-primary) 1rem, transparent 0), linear-gradient(var(--accent) 1rem, transparent 0);
  background-repeat: no-repeat; background-size: 1rem 1rem;
  background-position: left top, left bottom, right top, right bottom;
  animation: aithoSpinnerRotatingSquares 1s linear infinite;
}
@keyframes aithoSpinnerRotatingSquares {
  0% { width: 48px; height: 48px; transform: rotate(0deg); }
  50% { width: 32px; height: 32px; transform: rotate(180deg); }
  100% { width: 48px; height: 48px; transform: rotate(360deg); }
}

.aitho-spinner__el[data-type="rotatingDots"] { animation: aithoSpinnerRotatingDots 1.3s infinite; height: 50px; width: 50px; display: block; }
.aitho-spinner__el[data-type="rotatingDots"]::before,
.aitho-spinner__el[data-type="rotatingDots"]::after {
  border-radius: 50%; content: ""; display: block; height: 1.25rem; width: 1.25rem;
}
.aitho-spinner__el[data-type="rotatingDots"]::before {
  animation: aithoSpinnerRotatingDots1 1.3s infinite; background-color: var(--accent);
  box-shadow: 30px 0 0 #000; margin-bottom: 0.625rem;
}
.aitho-spinner__el[data-type="rotatingDots"]::after {
  animation: aithoSpinnerRotatingDots2 1.3s infinite; background-color: var(--color-primary);
  box-shadow: 30px 0 0 #000;
}
@keyframes aithoSpinnerRotatingDots {
  0% { transform: rotate(0deg) scale(0.6); }
  50% { transform: rotate(360deg) scale(1); }
  100% { transform: rotate(720deg) scale(0.6); }
}
@keyframes aithoSpinnerRotatingDots1 {
  0% { box-shadow: 30px 0 0 var(--color-primary); }
  50% { box-shadow: 0 0 0 var(--color-primary); margin-bottom: 0; transform: translate(15px, 15px); }
  100% { box-shadow: 30px 0 0 var(--color-primary); margin-bottom: 10px; }
}
@keyframes aithoSpinnerRotatingDots2 {
  0% { box-shadow: 30px 0 0 var(--accent); }
  50% { box-shadow: 0 0 0 var(--accent); margin-top: -20px; transform: translate(15px, 15px); }
  100% { box-shadow: 30px 0 0 var(--accent); margin-top: 0; }
}
`;

function ensureSpinnerStyles() {
  if (typeof document !== "undefined" && !document.getElementById("aitho-spinner-styles")) {
    const s = document.createElement("style");
    s.id = "aitho-spinner-styles";
    s.textContent = spinnerCss;
    document.head.appendChild(s);
  }
}

/** Displays an animated loading indicator. */
export function Spinner({ size = "md", type = "linearFlashingDots", ...props }) {
  ensureSpinnerStyles();
  return (
    <div className="aitho-spinner__root" data-size={size} {...props}>
      <span className="aitho-spinner__el" data-type={type}></span>
    </div>
  );
}
