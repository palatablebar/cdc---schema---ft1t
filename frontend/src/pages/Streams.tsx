import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MetricStrip } from '../components/common/MetricStrip';
import { PanelHead } from '../components/common/PanelHead';
import { StatusPill } from '../components/common/StatusPill';
import { EmptyState } from '../components/common/EmptyState';
import { STREAM_STATUS } from '../constants/cdc';
import { useStreamStore } from '../stores/streamStore';
import { formatCount, formatShortTime } from '../utils/format';

/** 事件流看板：每条流一行，左侧色条表示健康度，右侧是水位线与速率。 */
export const StreamsPage = () => {
  const board = useStreamStore((state) => state.board);
  const loading = useStreamStore((state) => state.loading);
  const error = useStreamStore((state) => state.error);
  const loadBoard = useStreamStore((state) => state.loadBoard);
  const selectStream = useStreamStore((state) => state.selectStream);
  const navigate = useNavigate();

  useEffect(() => {
    void loadBoard();
  }, [loadBoard]);

  const totals = board?.totals;

  return (
    <div>
      <PanelHead
        title="变更流看板"
        sub="上游 binlog → 归并 → 数仓；左侧色条是健康度，琥珀色代表有积压或待处理拒绝"
        actions={
          <button className="btn small" onClick={() => void loadBoard()}>
            刷新快照
          </button>
        }
      />

      {error ? <div className="notice danger">{error}</div> : null}

      <MetricStrip
        items={[
          { label: '在线变更流', value: totals ? String(totals.stream_count) : '—', note: '登记在册' },
          {
            label: '事件总量',
            value: totals ? formatCount(totals.event_count) : '—',
            note: '含重复投递',
          },
          {
            label: '待处理拒绝',
            value: totals ? String(totals.pending_rejected) : '—',
            tone: totals && totals.pending_rejected > 0 ? 'amber' : 'ok',
            note: '需重放或忽略',
          },
          {
            label: '历史运行',
            value: board ? `${board.run_stats.succeeded_runs}/${board.run_stats.total_runs}` : '—',
            note: board ? `均值 ${board.run_stats.avg_duration_ms} ms` : '',
          },
        ]}
      />

      <div className="section">
        <div className="section-label">
          <span>流清单</span>
        </div>

        {loading && !board ? (
          <div className="faint tiny">加载中…</div>
        ) : board && board.streams.length === 0 ? (
          <EmptyState
            title="还没有登记任何变更流"
            hint={
              <>
                用 <code>POST /api/streams</code> 登记源库源表，或执行 <code>docker compose exec -T backend python -m scripts.seed_demo</code> 灌入演示数据。
              </>
            }
          />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 34 }} />
                <th>流 / 源表</th>
                <th>状态</th>
                <th className="num">水位线 LSN</th>
                <th className="num">最新 LSN</th>
                <th className="num">积压</th>
                <th className="num">事件</th>
                <th>最近运行</th>
              </tr>
            </thead>
            <tbody>
              {board?.streams.map((stream, index) => {
                const tone = STREAM_STATUS[stream.status].tone;
                return (
                  <tr
                    key={stream.id}
                    className="row-click stagger"
                    style={{ animationDelay: `${index * 26}ms` }}
                    onClick={() => {
                      selectStream(stream.id);
                      navigate('/events');
                    }}
                  >
                    <td>
                      <span className={`status-bar ${tone}`} />
                    </td>
                    <td>
                      <div className="mono">{stream.name}</div>
                      <div className="tiny faint">
                        {stream.source_db}.{stream.source_table} · PK {stream.pk_column}
                      </div>
                    </td>
                    <td>
                      <StatusPill label={stream.status_label} tone={tone} />
                    </td>
                    <td className="num">{stream.watermark_display}</td>
                    <td className="num">{stream.max_lsn_display}</td>
                    <td className="num" style={{ color: stream.lag > 0 ? 'var(--color-warn)' : undefined }}>
                      {stream.lag}
                    </td>
                    <td className="num">
                      {formatCount(stream.summary.event_total)}
                      <div className="tiny faint">
                        +{stream.summary.by_op.insert} / ~{stream.summary.by_op.update} / -{stream.summary.by_op.delete}
                      </div>
                    </td>
                    <td className="tiny">
                      {stream.summary.last_run ? (
                        <>
                          <span className="mono">{stream.summary.last_run.upserted_count} 行</span>
                          <div className="faint">
                            {stream.summary.last_run.status} · {formatShortTime(stream.summary.last_run.finished_at)}
                          </div>
                        </>
                      ) : (
                        <span className="faint">从未运行</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="section">
        <div className="section-label">
          <span>今日口径</span>
        </div>
        <div className="split-even">
          <div className="panel">
            <div className="panel-head-sm">为什么需要归并</div>
            <div className="panel-body tiny muted">
              Kafka 至少一次投递 + binlog 位点回退，会出现同一条事件被投递两次、且到达顺序与 LSN 顺序不一致。
              归并算法按 LSN 稳定排序后再按主键落账，重复事件只计数不重复累加金额。
            </div>
          </div>
          <div className="panel">
            <div className="panel-head-sm">schema 漂移怎么处理</div>
            <div className="panel-body tiny muted">
              上游加列/改类型后，先提交新的 SchemaVersion，再用兼容判定得到 full/backward/forward/breaking，
              最后生成迁移 SQL 与回滚脚本。破坏性变更必须双写 + 回填 + 切读。
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
