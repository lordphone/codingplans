/** TTFT from benchmark seconds — matches directory / provider cards. */
export function formatTtftSeconds(seconds: number | null): string {
  if (seconds == null || Number.isNaN(seconds)) {
    return '—';
  }
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)} ms`;
  }
  return `${seconds.toFixed(2)} s`;
}
