/**
 * Inline SVG logo that responds to the active theme.
 *
 * The hexagon stroke, arrow stroke, and cursor fill use
 * `var(--color-accent)` so they automatically pick up the
 * current accent colour.  The background rect uses
 * `var(--color-slate-950)` so it adapts to the surface
 * brightness of the selected theme.
 */

import React from 'react';

interface LogoSvgProps {
  /** Tailwind size classes. Defaults to "w-9 h-9". */
  className?: string;
}

const LogoSvg: React.FC<LogoSvgProps> = ({ className = 'w-9 h-9' }) => (
  <svg
    className={className}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    {/* Background */}
    <rect
      width="48"
      height="48"
      fill="var(--color-slate-950, #0B0E14)"
      rx="4"
    />

    {/* Hexagon frame */}
    <path
      d="M24 4L41.3205 14V34L24 44L6.67949 34V14L24 4Z"
      stroke="var(--color-accent, #39FF14)"
      strokeWidth="2.5"
      fill="none"
    />

    {/* Prompt arrow */}
    <path
      d="M16 24L21 20L16 16"
      stroke="var(--color-accent, #39FF14)"
      strokeWidth="3"
      strokeLinecap="round"
      transform="translate(0, 4)"
    />

    {/* Blinking cursor */}
    <rect
      x="23"
      y="27"
      width="9"
      height="3"
      fill="var(--color-accent, #39FF14)"
    >
      <animate
        attributeName="opacity"
        values="1;1;0;0"
        keyTimes="0;0.5;0.5;1"
        dur="1.2s"
        repeatCount="indefinite"
      />
    </rect>
  </svg>
);

export default LogoSvg;
