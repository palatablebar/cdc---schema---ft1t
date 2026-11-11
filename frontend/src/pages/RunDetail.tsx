import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { runApi } from '../api/run';
import { MetricStrip } from '../components/common/MetricStrip';
import { PanelHead } from '../components/common/PanelHead';
import { StatusPill } from '../components/common/StatusPill';
import { EmptyState } from '../components/common/EmptyState';
import { RUN_STATUS } from '../constants/cdc';
import { useRunPolling } from '../hooks/useRunPolling';
import type { MergeRun } from '../types/models';
import { errorMessage } from '../utils/errorMessage';
import { displayValue, formatLsn, formatMs, formatTime } from '../utils/format';

/** 运行结果页：轮询到终态后展示计数、金额守恒校验、落账行、冲突与重复明细。 */
export const RunDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const [initial, setInitial] = useState<MergeRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { run, isRunning } = useRunPolling(initial);

  useEffect(() => {
    if (!id) return;
    runApi
      .get(id)
      .then(setInitial)
      .catch((err) => setError(errorMessage(err)));
  }, [id]);

  if (error) {
    return (
      <div>
        <PanelHead title="运行详情" />
        <div className="notice danger">{error}</div>
        <p style={{ marginTop: 12 }}>
          <Link className="btn small" to="/runs">
            返回运行列表
          </Link>
        </p>
      </div>
    );
  }

  if (!run) {
    return (
      <div>
        <PanelHead title="运行详情" />
        <div className="faint tiny">加载中…</div>
      </div>
    );
  }

  const result = run.result;
  const counts = result?.counts;

  return (
    <div>
      <PanelHead
        title={`归并运行 ${run.id.slice(0, 8)}`}
        sub={`${run.stream_name ?? ''} · 窗口 ${run.window_start_lsn} → ${run.window_end_lsn} · ${formatTime(run.created_at)}`}
        actions={
          <>
            <span data-testid="run-status">
              <StatusPill
                label={run.status_label}
                tone={RUN_STATUS[run.status].tone}
                running={RUN_STATUS[run.status].running}
              />
            </span>
            <Link className="btn small" to="/runs">
              返回列表
            </Link>
          </>
        }
      />

      {isRunning ? (
        <div className="notice" style={{ marginBottom: 12 }}>
          worker 正在处理这条窗口：按 LSN 排序 → 去重 → 应用变更 → 金额校验。页面每 1.2s 自动刷新。
        </div>
      ) : null}

      {run.error_message ? <div className="notice danger" style={{ marginBottom: 12 }}>{run.error_message}</div> : null}

      <MetricStrip
        items={[
          { label: '收到事件', value: String(run.received_count), note: '含重复投递' },
          { label: '处理事件', value: String(run.processed_count), note: 'insert+update+delete' },
          {
            label: '重复丢弃',
            value: String(run.duplicate_count),
            tone: run.duplicate_count > 0 ? 'amber' : 'ok',
            note: '同 (lsn, pk) 只算一次',
          },
          {
            label: '拒绝',
            value: String(run.rejected_count),
            tone: run.rejected_count > 0 ? 'danger' : 'ok',
            note: '进拒绝队列',
          },
          { label: '落账行', value: String(run.upserted_count), tone: 'ok', note: '窗口结束时的最终行数' },
          { label: '耗时', value: formatMs(run.duration_ms), note: result?.executed_by === 'worker' ? 'worker 执行' : 'seed 历史运行' },
        ]}
      />

      <div className="section">
        <div className="section-label">
          <span>水位线与幂等</span>
        </div>
        <div className="split-even">
          <div className="panel">
            <div className="panel-head-sm">位点推进</div>
            <div className="panel-body tiny">
              <div>
                运行前水位线 <span className="mono">{formatLsn(run.watermark_before)}</span>
              </div>
              <div style={{ marginTop: 6 }}>
                运行后水位线 <span className="mono" style={{ color: 'var(--color-amber)' }}>{formatLsn(run.watermark_after)}</span>
              </div>
              <div style={{ marginTop: 6 }} className="faint">
                窗口内有空洞时水位线停在空洞前一个 LSN；本次空洞：
                {result?.gap === null || result?.gap === undefined ? '无' : <span className="mono"> {result.gap}</span>}
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head-sm">幂等判定</div>
            <div className="panel-body tiny">
              <div>
                {run.idempotent ? (
                  <span className="pill ok">幂等 ✓ 与历史同窗口运行 digest 一致</span>
                ) : (
                  <span className="pill muted">首次窗口结果</span>
                )}
              </div>
              <div style={{ marginTop: 8 }} className="faint">
                digest <span className="code-inline">{run.result_digest ?? '—'}</span>
              </div>
              <div style={{ marginTop: 6 }} className="faint">
                同一窗口重复运行会得到相同 digest，可用于验证「重复投递不会让金额翻倍」。
              </div>
            </div>
          </div>
        </div>
      </div>

      {counts ? (
        <div className="section">
          <div className="section-label">
            <span>算法输出明细</span>
          </div>
          <div className="split-even">
            <div className="panel">
              <div className="panel-head-sm">
                操作计数
              </div>
              <table className="table">
                <tbody>
                  <tr><td>insert（新增行）</td><td className="num">{counts.inserted}</td></tr>
                  <tr><td>update（更新行）</td><td className="num">{counts.updated}</td></tr>
                  <tr><td>delete（tombstone）</td><td className="num">{counts.deleted}</td></tr>
                  <tr><td>rebuilt（删除后重建）</td><td className="num">{counts.rebuilt}</td></tr>
                  <tr><td>before 与当前行不一致（conflict）</td><td className="num">{counts.conflicted}</td></tr>
                  <tr>
                    <td>金额守恒校验</td>
                    <td className="num">
                      {result?.amount_audit.checked ?? 0} 项 / 不一致 {result?.amount_audit.mismatched ?? 0}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="panel">
              <div className="panel-head-sm">重复投递明细</div>
              <div className="panel-body">
                {result?.duplicates.length ? (
                  <table className="table">
                    <thead>
                      <tr>
                        <th className="num">LSN</th>
                        <th>主键</th>
                        <th>保留来源</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.duplicates.map((item) => (
                        <tr key={`${item.lsn}-${item.pk}`}>
                          <td className="num">{item.lsn}</td>
                          <td className="mono tiny">{item.pk}</td>
                          <td className="mono tiny faint">{item.kept_from?.slice(0, 8) ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="faint tiny">窗口内没有重复投递。</div>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="section">
        <div className="section-label">
          <span>落账行（{result?.rows.length ?? 0}）</span>
        </div>
        {!result ? (
          <EmptyState title="结果还没生成" hint="等待 worker 完成；若状态是 failed，先看上面的错误信息。" />
        ) : result.rows.length === 0 ? (
          <EmptyState title="窗口内没有可落账的行" hint="可能全部被拒绝或全部是删除操作。" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>主键</th>
                <th className="num">最后 LSN</th>
                <th>op</th>
                <th>重建</th>
                <th>最终值</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, index) => (
                <tr key={row.pk} className="stagger" style={{ animationDelay: `${index * 12}ms` }}>
                  <td className="mono tiny">{row.pk}</td>
                  <td className="num">{formatLsn(row.last_lsn)}</td>
                  <td className="tiny">{row.op}</td>
                  <td className="tiny faint">{row.rebuilt ? '是' : '否'}</td>
                  <td className="tiny mono" style={{ maxWidth: 560, wordBreak: 'break-all' }}>
                    {displayValue(row.values, 160)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
