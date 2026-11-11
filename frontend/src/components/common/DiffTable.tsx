import { displayValue } from '../../utils/format';

export interface DiffRow {
  field: string;
  before: unknown;
  after: unknown;
  kind?: string;
}

interface Props {
  rows: DiffRow[];
  beforeLabel?: string;
  afterLabel?: string;
  emptyText?: string;
}

/** 字段级 diff 表：事件 before/after 与 schema 字段变更共用这一个组件。 */
export const DiffTable = ({ rows, beforeLabel = 'before', afterLabel = 'after', emptyText = '没有差异' }: Props) => {
  if (rows.length === 0) {
    return <div className="faint tiny">{emptyText}</div>;
  }
  return (
    <table className="diff-table">
      <thead>
        <tr>
          <th style={{ width: '30%' }}>字段</th>
          <th style={{ width: '32%' }}>{beforeLabel}</th>
          <th style={{ width: '32%' }}>{afterLabel}</th>
          {rows.some((row) => row.kind) ? <th style={{ width: '6%' }} /> : null}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={`${row.field}-${index}`} className="stagger" style={{ animationDelay: `${index * 18}ms` }}>
            <td className="diff-field">{row.field}</td>
            <td className="diff-before">{displayValue(row.before)}</td>
            <td className="diff-after">{displayValue(row.after)}</td>
            {rows.some((item) => item.kind) ? <td className="diff-kind">{row.kind ?? ''}</td> : null}
          </tr>
        ))}
      </tbody>
    </table>
  );
};
