import { StatusPill } from './StatusPill';
import { displayValue } from '../../utils/format';
import type { PublishDetail } from '../../types/models';

interface Props {
  publish: PublishDetail | null | undefined;
  rowsBefore: number | null | undefined;
  rowsAfter: number | null | undefined;
}

/**
 * 数仓发布面板：把「运行成功」与「真的写进目标表」区分开。
 * - 发布成功：展示入库前后行数、LSN 守卫统计、目标表实际内容；
 * - gate 阻塞：整窗未发布，逐条列出阻塞字段（event/LSN/pk/字段/原因）。
 */
export const TargetPublishPanel = ({ publish, rowsBefore, rowsAfter }: Props) => {
  if (!publish) {
    return (
      <div className="section">
        <div className="section-label">
          <span>数仓目标表</span>
        </div>
        <div className="panel">
          <div className="panel-body tiny faint">本次运行没有发布信息（历史运行或尚未进入发布阶段）。</div>
        </div>
      </div>
    );
  }

  return (
    <div className="section">
      <div className="section-label">
        <span>数仓目标表{publish.target_table ? ` · ${publish.target_table}` : ''}</span>
      </div>

      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            {publish.published ? (
              <StatusPill label="已发布到目标表" tone="ok" />
            ) : (
              <StatusPill label="整窗未发布" tone="danger" />
            )}
            <span className="tiny faint">{publish.detail}</span>
          </div>

          <table className="table" style={{ marginTop: 12 }}>
            <tbody>
              <tr>
                <td>入库前目标表行数</td>
                <td className="num">{rowsBefore ?? '—'}</td>
              </tr>
              <tr>
                <td>入库后目标表行数</td>
                <td className="num">{rowsAfter ?? '—'}</td>
              </tr>
              {publish.published ? (
                <>
                  <tr>
                    <td>LSN 守卫生效 upsert（新位点写入）</td>
                    <td className="num">{publish.guarded_upserts ?? 0}</td>
                  </tr>
                  <tr>
                    <td>重复 / 迟到旧事件被跳过的 upsert</td>
                    <td className="num" style={{ color: 'var(--color-amber)' }}>
                      {publish.stale_upserts_skipped ?? 0}
                    </td>
                  </tr>
                  <tr>
                    <td>LSN 守卫生效 delete</td>
                    <td className="num">{publish.guarded_deletes ?? 0}</td>
                  </tr>
                  <tr>
                    <td>旧位点 delete 被跳过</td>
                    <td className="num">{publish.stale_deletes_skipped ?? 0}</td>
                  </tr>
                </>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {!publish.published && publish.blocking_fields.length > 0 ? (
        <div className="panel">
          <div className="panel-head-sm">
            阻塞字段（{publish.blocking_fields.length}）— 任一不兼容即整窗不发布，目标表保持发布前内容
          </div>
          <div className="panel-body">
            <table className="table">
              <thead>
                <tr>
                  <th className="num">LSN</th>
                  <th>主键</th>
                  <th>阻塞字段</th>
                  <th>原因</th>
                  <th>期望类型</th>
                  <th>实际类型</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {publish.blocking_fields.map((item, index) => (
                  <tr key={`${item.event_id}-${item.field}-${index}`}>
                    <td className="num">{item.lsn}</td>
                    <td className="mono tiny">{item.pk ?? '—'}</td>
                    <td className="mono tiny">{item.field}</td>
                    <td>
                      <span className="pill danger">{item.reason_label}</span>
                    </td>
                    <td className="tiny faint">{item.expected_type ?? '—'}</td>
                    <td className="tiny faint">{item.actual_type ?? '—'}</td>
                    <td className="tiny">{item.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {publish.published ? (
        <div className="panel">
          <div className="panel-head-sm">
            目标表实际内容（{publish.row_count_after ?? publish.target_rows?.length ?? 0} 行
            {publish.target_snapshot_truncated ? '，仅展示前 500 行' : ''}）
          </div>
          <div className="panel-body">
            {publish.target_rows && publish.target_rows.length > 0 ? (
              <TargetContentTable rows={publish.target_rows} columns={publish.target_columns} />
            ) : (
              <div className="faint tiny">目标表当前为空（窗口内事件全部被删除或拒绝）。</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
};

const TargetContentTable = ({
  rows,
  columns,
}: {
  rows: Array<Record<string, unknown>>;
  columns?: string[];
}) => {
  const cols = columns && columns.length > 0 ? columns : Object.keys(rows[0] ?? {});
  return (
    <table className="table">
      <thead>
        <tr>
          {cols.map((col) => (
            <th key={col} className={col === '_merge_lsn' ? 'num' : undefined}>
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            {cols.map((col) => (
              <td
                key={col}
                className={col === '_merge_lsn' ? 'num' : 'tiny mono'}
                style={col === '_merge_lsn' ? { color: 'var(--color-amber)' } : undefined}
              >
                {displayValue(row[col], 80)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
};
