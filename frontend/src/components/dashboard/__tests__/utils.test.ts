/**
 * Unit tests for dashboard utility functions.
 * All functions are pure — no React rendering needed.
 */

import { describe, it, expect } from 'vitest';
import {
  getContextWindow,
  getToolColors,
  getProgressColor,
  formatDuration,
  getModelPricing,
  estimateCost,
  formatCost,
  formatTokenCount,
} from '../utils';

describe('getContextWindow', () => {
  it('returns default 200k for undefined model', () => {
    expect(getContextWindow()).toBe(200000);
  });

  it('returns 200k for claude-3-5 model', () => {
    expect(getContextWindow('claude-3-5-sonnet')).toBe(200000);
  });

  it('returns 1M for claude-opus-4 model', () => {
    expect(getContextWindow('claude-opus-4-20250514')).toBe(1000000);
  });

  it('returns 2M for gemini-2.5-pro model', () => {
    expect(getContextWindow('gemini-2.5-pro-latest')).toBe(2000000);
  });

  it('falls back to 1M for unknown gemini model', () => {
    expect(getContextWindow('gemini-99-turbo')).toBe(1000000);
  });

  it('falls back to 200k for unknown claude model', () => {
    expect(getContextWindow('claude-99-turbo')).toBe(200000);
  });

  it('expands beyond limit when tokens exceed base', () => {
    // claude-3-5 base is 200k; if usage is 250k, should expand
    const result = getContextWindow('claude-3-5-sonnet', 250000);
    expect(result).toBeGreaterThan(250000);
  });

  it('contracts on very low usage', () => {
    // gemini-2.5-pro base is 2M; usage of 10k should contract
    const result = getContextWindow('gemini-2.5-pro', 10000);
    expect(result).toBeLessThan(2000000);
    expect(result).toBeGreaterThanOrEqual(32000);
  });

  it('returns baseMax when no tokens used', () => {
    expect(getContextWindow('gpt-4o', 0)).toBe(128000);
  });
});

describe('getToolColors', () => {
  it('returns purple for claude', () => {
    const colors = getToolColors('claude');
    expect(colors.badge).toContain('purple');
  });

  it('returns slate for bash', () => {
    const colors = getToolColors('bash');
    expect(colors.badge).toContain('slate');
  });

  it('returns slate for shell', () => {
    const colors = getToolColors('shell');
    expect(colors.badge).toContain('slate');
  });

  it('returns blue (default) for gemini', () => {
    const colors = getToolColors('gemini');
    expect(colors.badge).toContain('blue');
  });

  it('returns blue for undefined tool', () => {
    const colors = getToolColors();
    expect(colors.badge).toContain('blue');
  });
});

describe('getProgressColor', () => {
  it('returns green for low usage (<=50%)', () => {
    expect(getProgressColor(25)).toBe('bg-green-500');
    expect(getProgressColor(50)).toBe('bg-green-500');
  });

  it('returns amber for medium usage (51-80%)', () => {
    expect(getProgressColor(51)).toBe('bg-amber-500');
    expect(getProgressColor(80)).toBe('bg-amber-500');
  });

  it('returns red for high usage (>80%)', () => {
    expect(getProgressColor(81)).toBe('bg-red-500');
    expect(getProgressColor(100)).toBe('bg-red-500');
  });
});

describe('formatDuration', () => {
  it('formats seconds', () => {
    expect(formatDuration(45)).toBe('45s');
  });

  it('formats minutes', () => {
    expect(formatDuration(120)).toBe('2m');
    expect(formatDuration(90)).toBe('1m');
  });

  it('formats hours and minutes', () => {
    expect(formatDuration(3600 + 900)).toBe('1h 15m');
  });

  it('formats days and hours', () => {
    expect(formatDuration(86400 + 7200)).toBe('1d 2h');
  });

  it('returns empty for zero seconds', () => {
    expect(formatDuration(0)).toBe('');
  });

  it('falls back to wall clock from startedAt', () => {
    // Set startedAt to 120 seconds ago
    const twoMinAgo = new Date(Date.now() - 120000).toISOString();
    const result = formatDuration(undefined, twoMinAgo);
    expect(result).toBe('2m');
  });

  it('returns empty for undefined args', () => {
    expect(formatDuration()).toBe('');
  });
});

describe('getModelPricing', () => {
  it('returns pricing for claude-opus-4', () => {
    const p = getModelPricing('claude-opus-4-20250514');
    expect(p).not.toBeNull();
    expect(p!.input).toBe(15);
    expect(p!.output).toBe(75);
  });

  it('returns pricing for gemini-2.5-pro', () => {
    const p = getModelPricing('gemini-2.5-pro-latest');
    expect(p).not.toBeNull();
    expect(p!.input).toBe(1.25);
    expect(p!.output).toBe(10);
  });

  it('returns null for unknown model', () => {
    expect(getModelPricing('unknown-model')).toBeNull();
  });

  it('returns null for undefined', () => {
    expect(getModelPricing()).toBeNull();
  });
});

describe('estimateCost', () => {
  it('calculates cost from input and output tokens', () => {
    // gemini-2.5-flash: $0.15/MTok input, $0.60/MTok output
    const cost = estimateCost('gemini-2.5-flash', 1_000_000, 500_000);
    expect(cost).not.toBeNull();
    // 1M * 0.15 + 0.5M * 0.60 = 0.15 + 0.30 = 0.45
    expect(cost!).toBeCloseTo(0.45, 2);
  });

  it('returns null for unknown model', () => {
    expect(estimateCost('unknown', 1000, 500)).toBeNull();
  });

  it('handles zero tokens', () => {
    const cost = estimateCost('gemini-2.5-flash', 0, 0);
    expect(cost).toBe(0);
  });
});

describe('formatCost', () => {
  it('formats dollars with 2 decimal places', () => {
    expect(formatCost(1.5)).toBe('$1.50');
  });

  it('formats sub-cent with 3 decimal places', () => {
    expect(formatCost(0.005)).toBe('$0.005');
  });

  it('formats zero', () => {
    expect(formatCost(0)).toBe('$0.00');
  });

  it('returns dash for null', () => {
    expect(formatCost(null)).toBe('—');
  });
});

describe('formatTokenCount', () => {
  it('formats millions', () => {
    expect(formatTokenCount(1_500_000)).toBe('1.5M');
  });

  it('formats exact millions without decimal', () => {
    expect(formatTokenCount(2_000_000)).toBe('2M');
  });

  it('formats thousands', () => {
    expect(formatTokenCount(145_000)).toBe('145k');
  });

  it('formats exact thousands without decimal', () => {
    expect(formatTokenCount(1_000)).toBe('1k');
  });

  it('formats small numbers as-is', () => {
    expect(formatTokenCount(500)).toBe('500');
  });
});
