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
 */
export const CONTEXT_WINDOWS: Record<string, number> = {
  "claude-3-5": 200000,
  "claude-3": 200000,
  "claude-opus-4": 1000000,
  "claude-sonnet-4": 1000000,
  "claude-haiku-4": 1000000,
  "gemini-1.5-pro": 2000000,
  "gemini-exp": 2000000,
  "gemini-1.5-flash": 1000000,
  "gemini-2.5-pro": 2000000,
  "gemini-2.5-flash": 1000000,
  "gemini-2.0-flash": 1000000,
  "gpt-4": 128000,
  "gpt-4o": 128000,
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
    const normalizedModel = model.toLowerCase();
    let found = false;

    for (const [key, size] of Object.entries(CONTEXT_WINDOWS)) {
      if (normalizedModel.includes(key)) {
        baseMax = size;
        found = true;
        break;
      }
    }
    if (!found) {
      if (normalizedModel.includes("gemini")) baseMax = 1000000;
      else if (normalizedModel.includes("claude")) baseMax = 200000;
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
 * Returns Tailwind color classes for agent tool type badges.
 * Gemini = blue, Claude = purple, Bash = slate.
 */
export const getToolColors = (toolName?: string) => {
  const t = (toolName || "").toLowerCase();
  if (t.includes("claude")) {
    return {
      badge: "bg-purple-500/20 text-purple-400 border-purple-500/20",
      border: "hover:border-purple-500/50",
    };
  }
  if (t.includes("bash") || t.includes("shell")) {
    return {
      badge: "bg-slate-500/20 text-slate-300 border-slate-500/20",
      border: "hover:border-slate-500/50",
    };
  }
  // Default: gemini / blue
  return {
    badge: "bg-blue-500/20 text-blue-400 border-blue-500/20",
    border: "hover:border-blue-500/50",
  };
};

/**
 * Returns a Tailwind background color class for a context
 * usage progress bar based on the percentage filled.
 */
export const getProgressColor = (pct: number): string => {
  if (pct > 80) return "bg-red-500";
  if (pct > 50) return "bg-amber-500";
  return "bg-green-500";
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
  if (secs <= 0) return "";
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
