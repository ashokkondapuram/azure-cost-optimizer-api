const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function formatCeCompactCad(value, currency = 'CAD') {
  const v = Number(value);
  if (!Number.isFinite(v)) return `${currency} —`;
  if (v >= 1_000_000) return `${currency} ${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1000) return `${currency} ${Math.round(v / 1000).toLocaleString('en-US')}K`;
  return `${currency} ${Math.round(v).toLocaleString('en-US')}`;
}

function chartPoints(values, {
  width = 640,
  height = 200,
  padTop = 24,
  padBottom = 20,
  maxVal: maxOverride,
}) {
  if (!values?.length) return null;
  const nums = values.map((v) => (v == null || Number.isNaN(v) ? 0 : Number(v)));
  const maxVal = maxOverride ?? Math.max(...nums, 0.001) * 1.08;
  const chartH = height - padTop - padBottom;
  const count = nums.length;

  const pts = nums.map((val, i) => {
    const x = count <= 1 ? width / 2 : (i / (count - 1)) * width;
    const y = padTop + chartH - (val / maxVal) * chartH;
    return { x, y, val };
  });

  const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const last = pts[pts.length - 1];
  const areaPath = `${linePath} L${last.x.toFixed(1)} ${height - padBottom} L0 ${height - padBottom} Z`;

  const yTicks = [];
  for (let t = 0; t <= 4; t += 1) {
    const val = (maxVal * t) / 4;
    yTicks.push({ val, label: formatCeCompactCad(val) });
  }

  return { linePath, areaPath, pts, last, yTicks, maxVal };
}

export function buildDailyTrendSvg(dailyPoints, forecastPoints = [], { width = 640, height = 200 } = {}) {
  const costs = dailyPoints.map((p) => p.cost);
  const base = chartPoints(costs, { width, height });
  if (!base) return null;

  const allCosts = [...costs];
  if (forecastPoints.length) {
    forecastPoints.forEach((fp) => allCosts.push(fp.cost));
  }

  const combined = chartPoints(allCosts, { width, height });
  const forecastStartIdx = costs.length - 1;
  let forecastPath = '';
  let dividerX = null;

  if (forecastPoints.length && combined) {
    const startPt = combined.pts[forecastStartIdx];
    const forecastPts = [startPt, ...combined.pts.slice(forecastStartIdx + 1)];
    forecastPath = forecastPts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
    dividerX = startPt.x;
  }

  const labels = dailyPoints.map((p) => p.dateLabel);
  if (forecastPoints.length) {
    labels.push(forecastPoints[forecastPoints.length - 1]?.dateLabel || 'Forecast');
  }

  return {
    areaPath: base.areaPath,
    linePath: base.linePath,
    forecastPath,
    dividerX,
    dot: base.last,
    labels: pickAxisLabels(labels),
    yTicks: base.yTicks,
  };
}

export function buildCumulativeSvg(dailyPoints, compareDailyPoints = [], { width = 640, height = 200 } = {}) {
  let running = 0;
  const cumulative = dailyPoints.map((p) => {
    running += p.cost || 0;
    return running;
  });

  let priorRunning = 0;
  const priorCumulative = (compareDailyPoints || []).map((p) => {
    priorRunning += p.cost || 0;
    return priorRunning;
  });

  const maxVal = Math.max(
    cumulative[cumulative.length - 1] || 0,
    priorCumulative[priorCumulative.length - 1] || 0,
    0.001,
  ) * 1.08;

  const current = chartPoints(cumulative, { width, height, maxVal });
  const prior = priorCumulative.length
    ? chartPoints(priorCumulative, { width, height, maxVal })
    : null;

  if (!current) return null;

  const labels = pickAxisLabels(dailyPoints.map((p) => p.dateLabel));

  return {
    areaPath: current.areaPath,
    linePath: current.linePath,
    priorPath: prior?.linePath || '',
    dot: current.last,
    labels,
    yTicks: current.yTicks,
  };
}

export function buildPopSvg(currentPoints, comparePoints, { width = 640, height = 160 } = {}) {
  const current = chartPoints(currentPoints.map((p) => p.cost), { width, height, padTop: 20, padBottom: 16 });
  const prior = chartPoints(comparePoints.map((p) => p.cost), {
    width,
    height,
    padTop: 20,
    padBottom: 16,
    maxVal: current?.maxVal,
  });
  if (!current) return null;

  return {
    currentPath: current.linePath,
    priorPath: prior?.linePath || '',
    labels: pickAxisLabels(currentPoints.map((p) => p.dateLabel)),
  };
}

function pickAxisLabels(labels, max = 5) {
  if (!labels?.length) return [];
  if (labels.length <= max) return labels;
  const step = Math.floor((labels.length - 1) / (max - 1));
  const picked = [];
  for (let i = 0; i < labels.length; i += step) {
    picked.push(labels[i]);
  }
  const last = labels[labels.length - 1];
  if (picked[picked.length - 1] !== last) picked.push(last);
  return picked.slice(0, max);
}

export function buildSpendVelocity(dailyPoints) {
  if (!dailyPoints?.length) return null;

  const byDate = new Map(dailyPoints.map((p) => [p.date, p.cost || 0]));
  const dates = [...byDate.keys()].sort();
  const lastDate = new Date(`${dates[dates.length - 1]}T12:00:00`);

  const mondayOf = (d) => {
    const copy = new Date(d);
    const day = copy.getDay();
    const diff = copy.getDate() - day + (day === 0 ? -6 : 1);
    copy.setDate(diff);
    copy.setHours(0, 0, 0, 0);
    return copy;
  };

  const fmt = (d) => d.toISOString().slice(0, 10);
  const sumBetween = (start, end) => {
    let total = 0;
    dates.forEach((date) => {
      if (date >= start && date <= end) total += byDate.get(date) || 0;
    });
    return total;
  };

  const thisWeekStart = fmt(mondayOf(lastDate));
  const thisWeekTotal = sumBetween(thisWeekStart, dates[dates.length - 1]);

  const lastWeekEnd = new Date(mondayOf(lastDate));
  lastWeekEnd.setDate(lastWeekEnd.getDate() - 1);
  const lastWeekStart = new Date(lastWeekEnd);
  lastWeekStart.setDate(lastWeekStart.getDate() - 6);
  const lastWeekTotal = sumBetween(fmt(lastWeekStart), fmt(lastWeekEnd));

  const priorWeekEnd = new Date(lastWeekStart);
  priorWeekEnd.setDate(priorWeekEnd.getDate() - 1);
  const priorWeekStart = new Date(priorWeekEnd);
  priorWeekStart.setDate(priorWeekStart.getDate() - 6);
  const priorWeekTotal = sumBetween(fmt(priorWeekStart), fmt(priorWeekEnd));

  const thisWeekPct = lastWeekTotal > 0
    ? ((thisWeekTotal - lastWeekTotal) / lastWeekTotal) * 100
    : null;
  const lastWeekPct = priorWeekTotal > 0
    ? ((lastWeekTotal - priorWeekTotal) / priorWeekTotal) * 100
    : null;

  let peakCost = 0;
  let peakDate = dates[0];
  dailyPoints.forEach((p) => {
    if ((p.cost || 0) >= peakCost) {
      peakCost = p.cost || 0;
      peakDate = p.date;
    }
  });
  const peakLabel = peakDate
    ? `${MONTHS[Number(peakDate.slice(5, 7)) - 1]} ${Number(peakDate.slice(8, 10))}`
    : '—';

  return {
    thisWeek: thisWeekTotal,
    lastWeek: lastWeekTotal,
    thisWeekPct,
    lastWeekPct,
    peakCost,
    peakLabel,
  };
}
