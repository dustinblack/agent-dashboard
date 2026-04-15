/**
 * Utility functions for Dashboard components.
 * Extracted from Dashboard.tsx for maintainability.
 */

/** Ordered list of context window size tiers for dynamic scaling. */
export const CONTEXT_TIERS = [
  8000, 16000, 32000, 64000, 128000, 200000, 500000, 1000000, 2000000, 4000000,
  8000000,
];

/**
 * Known context window sizes keyed by partial model name.
 * Used for matching against normalized model identifiers.
 *
 * Key ordering is critical: `.includes()` matching stops
 * at the first hit, so more-specific keys must precede
 * less-specific ones within each model family.
 *
 * Claude models with a `[1m]` suffix (e.g.
 * "claude-opus-4-6[1m]") use 1M context; without the
 * suffix they default to 200k. The suffix is parsed in
 * `getContextWindow()` before consulting this map.
 *
 * Last verified: 2026-04-15
 */
export const CONTEXT_WINDOWS: Record<string, number> = {
  // Claude — all default to 200k; 1M via [1m] suffix
  'claude-opus-4-6': 200000,
  'claude-sonnet-4-6': 200000,
  'claude-opus-4-5': 200000,
  'claude-opus-4-1': 200000,
  'claude-opus-4': 200000,
  'claude-sonnet-4-5': 200000,
  'claude-sonnet-4': 200000,
  'claude-haiku-4': 200000,
  'claude-3-5': 200000,
  'claude-3': 200000,
  // Gemini — all 1,048,576 input tokens
  'gemini-3.1-pro': 1048576,
  'gemini-3.1-flash': 1048576,
  'gemini-3-flash': 1048576,
  'gemini-2.5-pro': 1048576,
  'gemini-2.5-flash-lite': 1048576,
  'gemini-2.5-flash': 1048576,
  'gemini-2.0-flash': 1048576,
  // GPT
  'gpt-4o': 128000,
  'gpt-4': 128000,
};

/**
 * Determines the effective context window size for a model.
 * Dynamically expands or contracts the visual maximum so
 * the progress bar stays meaningful regardless of actual
 * token usage.
 */
export const getContextWindow = (
  model?: string,
  tokensUsed: number = 0,
): number => {
  let baseMax = 200000;
  if (model) {
    let normalizedModel = model.toLowerCase();

    // Detect [1m] context suffix (e.g. "claude-opus-4-6[1m]")
    const has1mSuffix = normalizedModel.includes('[1m]');
    if (has1mSuffix) {
      normalizedModel = normalizedModel.replace('[1m]', '');
    }

    let found = false;
    for (const [key, size] of Object.entries(CONTEXT_WINDOWS)) {
      if (normalizedModel.includes(key)) {
        baseMax = size;
        found = true;
        break;
      }
    }
    if (!found) {
      if (normalizedModel.includes('gemini')) baseMax = 1048576;
      else if (normalizedModel.includes('claude')) baseMax = 200000;
    }

    // Override with 1M if the [1m] suffix was present
    if (has1mSuffix) {
      baseMax = 1_000_000;
    }
  }

  if (!tokensUsed) return baseMax;

  // Expansion: If tokens exceed the hardcoded limit,
  // expand to next tier.
  if (tokensUsed >= baseMax) {
    const higherTiers = CONTEXT_TIERS.filter((t) => t > tokensUsed);
    return higherTiers.length > 0
      ? higherTiers[0]
      : Math.ceil(tokensUsed * 1.5);
  }

  // Contraction: If usage is very low compared to the
  // hardcoded baseMax, dynamically contract the visual
  // maximum so the progress bar remains meaningful.
  const idealMax = Math.max(tokensUsed * 1.5, 32000);
  if (idealMax < baseMax) {
    const lowerTiers = CONTEXT_TIERS.filter(
      (t) => t >= idealMax && t <= baseMax,
    );
    if (lowerTiers.length > 0) {
      return lowerTiers[0];
    }
  }

  return baseMax;
};

/**
 * Returns true if the model string matches a known entry in
 * the CONTEXT_WINDOWS map. Returns true for undefined/empty
 * model (no warning when telemetry hasn't reported yet).
 *
 * Use this to flag models that may need to be added to the
 * hardcoded lookup tables.
 */
export const isModelRecognized = (model?: string): boolean => {
  if (!model) return true;
  const normalized = model.toLowerCase().replace('[1m]', '');
  for (const key of Object.keys(CONTEXT_WINDOWS)) {
    if (normalized.includes(key)) return true;
  }
  return false;
};

/**
 * Returns Tailwind color classes for agent tool type badges.
 * Gemini = blue, Claude = purple, Bash = slate.
 */
export const getToolColors = (toolName?: string) => {
  const t = (toolName || '').toLowerCase();
  if (t.includes('claude')) {
    return {
      badge: 'bg-purple-500/20 text-purple-400 border-purple-500/20',
      border: 'hover:border-purple-500/50',
    };
  }
  if (t.includes('bash') || t.includes('shell')) {
    return {
      badge: 'bg-slate-500/20 text-slate-300 border-slate-500/20',
      border: 'hover:border-slate-500/50',
    };
  }
  // Default: gemini / blue
  return {
    badge: 'bg-blue-500/20 text-blue-400 border-blue-500/20',
    border: 'hover:border-blue-500/50',
  };
};

/**
 * Returns a Tailwind background color class for a context
 * usage progress bar based on the percentage filled.
 */
export const getProgressColor = (pct: number): string => {
  if (pct > 80) return 'bg-red-500';
  if (pct > 50) return 'bg-amber-500';
  return 'bg-green-500';
};

/**
 * Per-model pricing in dollars per million tokens.
 * Used for cost estimation when the tool does not report
 * cost directly (e.g. Gemini). Claude Code reports its own
 * cost via OTLP so these are only used as fallback.
 *
 * Last verified: 2026-04-15
 */
export interface ModelPricing {
  /** Dollars per million input tokens. */
  input: number;
  /** Dollars per million output tokens. */
  output: number;
  /** Dollars per million cache read tokens. */
  cacheRead?: number;
  /** Dollars per million cache creation tokens. */
  cacheWrite?: number;
}

export const MODEL_PRICING: Record<string, ModelPricing> = {
  // Claude — ordered most-specific first
  'claude-opus-4-6': {
    input: 5,
    output: 25,
    cacheRead: 0.5,
    cacheWrite: 6.25,
  },
  'claude-sonnet-4-6': {
    input: 3,
    output: 15,
    cacheRead: 0.3,
    cacheWrite: 3.75,
  },
  'claude-opus-4-5': { input: 5, output: 25 },
  'claude-opus-4-1': { input: 15, output: 75 },
  'claude-opus-4': {
    input: 15,
    output: 75,
    cacheRead: 1.5,
    cacheWrite: 18.75,
  },
  'claude-sonnet-4-5': {
    input: 3,
    output: 15,
    cacheRead: 0.3,
    cacheWrite: 3.75,
  },
  'claude-sonnet-4': {
    input: 3,
    output: 15,
    cacheRead: 0.3,
    cacheWrite: 3.75,
  },
  'claude-haiku-4': {
    input: 1,
    output: 5,
    cacheRead: 0.1,
    cacheWrite: 1.25,
  },
  'claude-3-5-sonnet': {
    input: 3,
    output: 15,
    cacheRead: 0.3,
    cacheWrite: 3.75,
  },
  'claude-3-5-haiku': {
    input: 0.8,
    output: 4,
    cacheRead: 0.08,
    cacheWrite: 1,
  },
  // Gemini
  'gemini-3.1-pro': { input: 2, output: 12 },
  'gemini-3.1-flash': { input: 0.25, output: 1.5 },
  'gemini-3-flash': { input: 0.5, output: 3 },
  'gemini-2.5-pro': { input: 1.25, output: 10 },
  'gemini-2.5-flash': { input: 0.15, output: 0.6 },
  'gemini-2.0-flash': { input: 0.1, output: 0.4 },
};

/**
 * Looks up pricing for a model using partial name matching.
 * Returns null if no pricing is found.
 */
export const getModelPricing = (model?: string): ModelPricing | null => {
  if (!model) return null;
  const normalized = model.toLowerCase().replace('[1m]', '');
  for (const [key, pricing] of Object.entries(MODEL_PRICING)) {
    if (normalized.includes(key)) return pricing;
  }
  return null;
};

/**
 * Estimates session cost in USD from token breakdown and
 * model pricing. Returns null if model pricing is unknown.
 */
export const estimateCost = (
  model?: string,
  inputTokens?: number,
  outputTokens?: number,
  cacheReadTokens?: number,
  cacheCreationTokens?: number,
): number | null => {
  const pricing = getModelPricing(model);
  if (!pricing) return null;
  const inp = ((inputTokens || 0) / 1_000_000) * pricing.input;
  const out = ((outputTokens || 0) / 1_000_000) * pricing.output;
  const cr =
    ((cacheReadTokens || 0) / 1_000_000) * (pricing.cacheRead || pricing.input);
  const cw =
    ((cacheCreationTokens || 0) / 1_000_000) *
    (pricing.cacheWrite || pricing.input);
  return inp + out + cr + cw;
};

/**
 * Formats a cost in USD for display. Returns "—" if null.
 * Uses appropriate precision: sub-cent shows 3 decimals,
 * otherwise 2.
 */
export const formatCost = (cost: number | null): string => {
  if (cost === null || cost === undefined) return '—';
  if (cost === 0) return '$0.00';
  if (cost < 0.01) return `$${cost.toFixed(3)}`;
  return `$${cost.toFixed(2)}`;
};

/**
 * Formats a token count in compact form (e.g. 1.2k, 1.2M).
 */
export const formatTokenCount = (tokens: number): string => {
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  }
  if (tokens >= 1_000) {
    return `${(tokens / 1_000).toFixed(1).replace(/\.0$/, '')}k`;
  }
  return tokens.toString();
};

/**
 * Formats a duration in seconds to a compact human-readable
 * string (e.g. "45s", "12m", "2h 15m", "1d 3h").
 * Falls back to wall-clock elapsed from a start timestamp
 * if seconds is not available.
 */
export const formatDuration = (
  seconds?: number,
  startedAt?: string,
): string => {
  let secs = seconds || 0;
  if (!secs && startedAt) {
    const start = new Date(startedAt).getTime();
    if (!isNaN(start)) {
      secs = Math.floor((Date.now() - start) / 1000);
    }
  }
  if (secs <= 0) return '';
  if (secs < 60) return `${secs}s`;
  const minutes = Math.floor(secs / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours < 24) return `${hours}h ${mins}m`;
  const days = Math.floor(hours / 24);
  const hrs = hours % 24;
  return `${days}d ${hrs}h`;
};
