type Tone = 'default' | 'amber' | 'danger' | 'ok';

export interface Metric {
  label: string;
  value: string;
  note?: string;
  tone?: Tone;
}

const toneClass = (tone: Tone | undefined): string => {
  if (tone === 'amber') return 'metric-value is-amber';
  if (tone === 'danger') return 'metric-value is-danger';
  if (tone === 'ok') return 'metric-value is-ok';
  return 'metric-value';
};

/** 横向指标条：一个边框包住，内部靠 1px 竖线分隔（不是卡片组）。 */
export const MetricStrip = ({ items }: { items: Metric[] }) => (
  <div className="metric-strip">
    {items.map((item) => (
      <div className="metric" key={item.label}>
        <span className="metric-label">{item.label}</span>
        <span className={toneClass(item.tone)}>{item.value}</span>
        {item.note ? <span className="metric-note">{item.note}</span> : null}
      </div>
    ))}
  </div>
);
