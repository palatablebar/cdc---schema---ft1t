import type { ReactNode } from 'react';

interface Props {
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
}

/** 空状态教学：说明为什么空 + 下一步该做什么，而不是只放一个图标。 */
export const EmptyState = ({ title, hint, action }: Props) => (
  <div className="empty">
    <strong>{title}</strong>
    {hint ? <div className="tiny">{hint}</div> : null}
    {action ? <div style={{ marginTop: 12 }}>{action}</div> : null}
  </div>
);
