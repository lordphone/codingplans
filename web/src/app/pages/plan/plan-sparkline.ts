import type { PlanPerformanceDayPoint } from './plan.models';

export interface SparklineSegment {
  linePathD: string;
  areaPathD: string;
}

export interface MetricSparklineGeom {
  segments: SparklineSegment[];
  yMin: number | null;
  yMax: number | null;
  hasData: boolean;
  /** Mean of non-null daily bucket values in the window */
  avgValue: number | null;
}

/** Wider plot reads closer to dashboard cards (OpenRouter-style). */
const W = 320;
const H = 120;
const PAD_L = 4;
const PAD_R = 4;
const PAD_T = 12;
const PAD_B = 8;

const BOTTOM_Y = H - PAD_B;

interface Pt {
  x: number;
  y: number;
}

function catmullRomToBezierPath(points: Pt[]): string {
  if (points.length === 0) {
    return '';
  }
  if (points.length === 1) {
    const p = points[0];
    return `M ${p.x} ${p.y}`;
  }
  let d = `M ${points[0].x} ${points[0].y}`;
  if (points.length === 2) {
    const a = points[0];
    const b = points[1];
    return `${d} L ${b.x} ${b.y}`;
  }
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }
  return d;
}

function areaUnderLine(linePathD: string, first: Pt, last: Pt): string {
  if (!linePathD) {
    return '';
  }
  return `${linePathD} L ${last.x.toFixed(2)} ${BOTTOM_Y} L ${first.x.toFixed(2)} ${BOTTOM_Y} Z`;
}

/**
 * Smooth spline + soft fill region (no axes). One segment per contiguous run of days with data.
 */
export function buildMetricSparkline(
  series: PlanPerformanceDayPoint[],
  valueKey: 'avgTps' | 'avgTtftS'
): MetricSparklineGeom {
  const n = series.length;
  if (n === 0) {
    return { segments: [], yMin: null, yMax: null, hasData: false, avgValue: null };
  }

  const bucketVals = series
    .map(p => p[valueKey])
    .filter((v): v is number => v != null && !Number.isNaN(v));
  if (bucketVals.length === 0) {
    return { segments: [], yMin: null, yMax: null, hasData: false, avgValue: null };
  }

  const avgValue = bucketVals.reduce((s, x) => s + x, 0) / bucketVals.length;

  let yMin = Math.min(...bucketVals);
  let yMax = Math.max(...bucketVals);
  if (yMin === yMax) {
    const pad = yMin === 0 ? 1 : Math.abs(yMin) * 0.06;
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

  const segments: SparklineSegment[] = [];
  let run: { i: number; v: number }[] = [];

  const flush = () => {
    if (run.length === 0) {
      return;
    }
    let pts: Pt[] = run.map(r => ({ x: xAt(r.i), y: normY(r.v) }));
    if (pts.length === 1) {
      const p = pts[0];
      const dx = Math.min(12, plotW * 0.04);
      pts = [
        { x: Math.max(PAD_L, p.x - dx / 2), y: p.y },
        { x: Math.min(W - PAD_R, p.x + dx / 2), y: p.y }
      ];
    }
    const linePathD = catmullRomToBezierPath(pts);
    const first = pts[0];
    const last = pts[pts.length - 1];
    const areaPathD = areaUnderLine(linePathD, first, last);
    segments.push({ linePathD, areaPathD });
    run = [];
  };

  for (let i = 0; i < n; i++) {
    const v = series[i][valueKey];
    if (v != null && !Number.isNaN(v)) {
      run.push({ i, v });
    } else {
      flush();
    }
  }
  flush();

  return {
    segments,
    yMin,
    yMax,
    hasData: segments.length > 0,
    avgValue
  };
}
