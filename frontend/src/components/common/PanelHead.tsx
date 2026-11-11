import type { ReactNode } from 'react';

interface Props {
  title: string;
  sub?: string;
  actions?: ReactNode;
}

/** 区块标题：主标题 + 次级说明 + 右侧动作，底部 1px 分隔线。 */
export const PanelHead = ({ title, sub, actions }: Props) => (
  <div className="panel-head">
    <h1>{title}</h1>
    {sub ? <span className="sub">{sub}</span> : null}
    {actions ? <div className="actions">{actions}</div> : null}
  </div>
);
