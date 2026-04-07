import type { PlanPerformanceDayPoint } from './plan.models';

export interface MetricSparklineGeom {
  pathD: string;
  dots: Array<{ cx: number; cy: number }>;
  yMin: number | null;
  yMax: number | null;
  hasData: boolean;
}

const W = 100;
const H = 36;
const PAD_L = 2;
const PAD_R = 2;
const PAD_T = 4;
const PAD_B = 6;

/**
 * Line + dots in viewBox coordinates (0..100 x 0..36). Skips null days; breaks path across gaps.
 */
export function buildMetricSparkline(
  series: PlanPerformanceDayPoint[],
  valueKey: 'avgTps' | 'avgTtftS'
): MetricSparklineGeom {
  const n = series.length;
  if (n === 0) {
    return { pathD: '', dots: [], yMin: null, yMax: null, hasData: false };
  }

  const values = series.map(p => p[valueKey]).filter((v): v is number => v != null && !Number.isNaN(v));
  if (values.length === 0) {
    return { pathD: '', dots: [], yMin: null, yMax: null, hasData: false };
  }

  let yMin = Math.min(...values);
  let yMax = Math.max(...values);
  if (yMin === yMax) {
    const pad = yMin === 0 ? 1 : Math.abs(yMin) * 0.08;
    yMin -= pad;
    yMax += pad;
  }

  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;
  const xAt = (i: number) => PAD_L + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);

  const normY = (v: number) => {
    const t = (v - yMin) / (yMax - yMin);
    return PAD_T + (1 - t) * plotH;
  };

  const parts: string[] = [];
  const dots: Array<{ cx: number; cy: number }> = [];

  let segment: { i: number; v: number }[] = [];
  const flush = () => {
    if (segment.length === 0) return;
    const d = segment
      .map((s, idx) => {
        const x = xAt(s.i);
        const y = normY(s.v);
        dots.push({ cx: x, cy: y });
        return `${idx === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(' ');
    parts.push(d);
    segment = [];
  };

  for (let i = 0; i < n; i++) {
    const v = series[i][valueKey];
    if (v != null && !Number.isNaN(v)) {
      segment.push({ i, v });
    } else {
      flush();
    }
  }
  flush();

  return {
    pathD: parts.join(' '),
    dots,
    yMin,
    yMax,
    hasData: true
  };
}
