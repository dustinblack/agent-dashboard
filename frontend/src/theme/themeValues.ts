/**
 * Theme definitions for the Agent Dashboard.
 *
 * Each theme bundles an accent colour with a brightness /
 * surface palette expressed as Tailwind CSS custom-property
 * overrides for the slate scale.  A `null` slateScale means
 * "use Tailwind v4 defaults" (i.e. standard dark mode).
 */

export type ThemeKey =
  | 'matrix-green'
  | 'cyber-cyan'
  | 'retro-amber'
  | 'proton-purple'
  | 'signal-red'
  | 'space-black';

export interface ThemeDefinition {
  /** Human-readable label shown on hover / aria. */
  label: string;
  /** Primary accent hex. */
  accent: string;
  /** Lighter accent for hover states. */
  accentHover: string;
  /** Darker / muted accent for borders. */
  accentMuted: string;
  /** Text colour for use on accent-coloured backgrounds. */
  accentText: string;
  /** Colour rendered in the selector dot. */
  dotColor: string;
  /**
   * Overrides for `--color-slate-*` CSS custom properties.
   * `null` = keep Tailwind defaults (dark mode).
   */
  slateScale: Record<string, string> | null;
}

/** Slate overrides for the "medium" warm-gray palette. */
const MEDIUM_SLATE: Record<string, string> = {
  '--color-slate-50': '#faf8f5',
  '--color-slate-100': '#e8e4dd',
  '--color-slate-200': '#d5cfc5',
  '--color-slate-300': '#b8b0a2',
  '--color-slate-400': '#9a8f7e',
  '--color-slate-500': '#7d7265',
  '--color-slate-600': '#5e554b',
  '--color-slate-700': '#443d35',
  '--color-slate-800': '#2e2923',
  '--color-slate-900': '#1c1915',
  '--color-slate-950': '#0f0d0a',
};

/** Slate overrides for the high-contrast palette. */
const HIGH_CONTRAST_SLATE: Record<string, string> = {
  '--color-slate-50': '#ffffff',
  '--color-slate-100': '#f1f5f9',
  '--color-slate-200': '#e2e8f0',
  '--color-slate-300': '#cbd5e1',
  '--color-slate-400': '#94a3b8',
  '--color-slate-500': '#64748b',
  '--color-slate-600': '#475569',
  '--color-slate-700': '#1e293b',
  '--color-slate-800': '#0f172a',
  '--color-slate-900': '#020617',
  '--color-slate-950': '#000000',
};

/**
 * Light-mode slate: the scale is inverted so that
 * `slate-900` (used for backgrounds) becomes near-white
 * and `slate-100` (used for text) becomes near-dark.
 */
const LIGHT_SLATE: Record<string, string> = {
  '--color-slate-50': '#020617',
  '--color-slate-100': '#1e293b',
  '--color-slate-200': '#334155',
  '--color-slate-300': '#475569',
  '--color-slate-400': '#64748b',
  '--color-slate-500': '#94a3b8',
  '--color-slate-600': '#cbd5e1',
  '--color-slate-700': '#e2e8f0',
  '--color-slate-800': '#f1f5f9',
  '--color-slate-900': '#f8fafc',
  '--color-slate-950': '#ffffff',
};

export const THEMES: Record<ThemeKey, ThemeDefinition> = {
  'matrix-green': {
    label: 'Matrix Green',
    accent: '#39FF14',
    accentHover: '#5FFF4A',
    accentMuted: '#1A7A0A',
    accentText: '#0a0a0a',
    dotColor: '#39FF14',
    slateScale: null,
  },
  'cyber-cyan': {
    label: 'Cyber Cyan',
    accent: '#00F0FF',
    accentHover: '#4AF5FF',
    accentMuted: '#006B73',
    accentText: '#0a0a0a',
    dotColor: '#00F0FF',
    slateScale: null,
  },
  'retro-amber': {
    label: 'Retro Amber',
    accent: '#FFB800',
    accentHover: '#FFCE4A',
    accentMuted: '#7A5800',
    accentText: '#0a0a0a',
    dotColor: '#FFB800',
    slateScale: MEDIUM_SLATE,
  },
  'proton-purple': {
    label: 'Proton Purple',
    accent: '#BF40BF',
    accentHover: '#D670D6',
    accentMuted: '#5E205E',
    accentText: '#ffffff',
    dotColor: '#BF40BF',
    slateScale: null,
  },
  'signal-red': {
    label: 'Signal Red',
    accent: '#FF4444',
    accentHover: '#FF7070',
    accentMuted: '#7A2020',
    accentText: '#ffffff',
    dotColor: '#FF4444',
    slateScale: HIGH_CONTRAST_SLATE,
  },
  'space-black': {
    label: 'Space Black',
    accent: '#0B0E14',
    accentHover: '#2A2F3A',
    accentMuted: '#64748b',
    accentText: '#f8fafc',
    dotColor: '#0B0E14',
    slateScale: LIGHT_SLATE,
  },
};

/** The theme applied when no preference is stored. */
export const DEFAULT_THEME: ThemeKey = 'matrix-green';
