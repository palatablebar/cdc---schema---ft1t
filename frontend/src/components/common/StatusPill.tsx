type Tone = 'ok' | 'amber' | 'warn' | 'danger' | 'forward' | 'muted';

interface Props {
  label: string;
  tone: Tone;
  running?: boolean;
  title?: string;
}

/** 状态徽标：方角 + 左侧色点；running 时色点呼吸（唯一动效之一）。 */
export const StatusPill = ({ label, tone, running = false, title }: Props) => (
  <span className={`pill ${tone}${running ? ' running' : ''}`} title={title ?? label}>
    {label}
  </span>
);
