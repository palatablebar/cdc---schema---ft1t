/** 展示层格式化（不做业务计算；LSN 排序、归并都在后端）。 */
export const formatLsn = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—';
  return String(value).padStart(12, '0');
};

export const formatCount = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-US').format(value);
};

export const formatMs = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—';
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(2)} s`;
};

export const formatTime = (value: string | null | undefined): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}:${pad(date.getSeconds())}`;
};

export const formatShortTime = (value: string | null | undefined): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

/** 值展示：null/undefined 用占位符，对象转 JSON，长文本截断。 */
export const displayValue = (value: unknown, max = 60): string => {
  if (value === null || value === undefined) return '∅';
  if (typeof value === 'object') return JSON.stringify(value);
  const text = String(value);
  return text.length > max ? `${text.slice(0, max)}…` : text;
};

export const formatDurationText = (from: string | null, to: string | null): string => {
  if (!from || !to) return '—';
  const start = new Date(from).getTime();
  const end = new Date(to).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return '—';
  return formatMs(Math.max(0, end - start));
};
