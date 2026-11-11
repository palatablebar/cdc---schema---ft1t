import { useCallback, useEffect, useState } from 'react';
import { eventApi } from '../api/event';
import { streamApi } from '../api/stream';
import { DiffTable, type DiffRow } from '../components/common/DiffTable';
import { EmptyState } from '../components/common/EmptyState';
import { PanelHead } from '../components/common/PanelHead';
import { StatusPill } from '../components/common/StatusPill';
import { CDC_OP, REJECT_REASON } from '../constants/cdc';
import { useEventFilters } from '../hooks/useEventFilters';
import { useStreamStore } from '../stores/streamStore';
import type { CdcEvent, EventDiff } from '../types/models';
import { errorMessage } from '../utils/errorMessage';
import { formatLsn, formatShortTime } from '../utils/format';

/** 事件浏览：左表格 + 右 before/after 字段级 diff（diff 由后端计算）。 */
export const EventsPage = () => {
  const board = useStreamStore((state) => state.board);
  const selectedStreamId = useStreamStore((state) => state.selectedStreamId);
  const selectStream = useStreamStore((state) => state.selectStream);
  const { filters, setOp, toggleRejected, setOrder, setPage } = useEventFilters();

  const [events, setEvents] = useState<CdcEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<EventDiff | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [stats, setStats] = useState<{ arrival_inversions: number; duplicate_rows: number } | null>(null);

  const stream = board?.streams.find((item) => item.id === selectedStreamId) ?? board?.streams[0] ?? null;

  const load = useCallback(async () => {
    if (!stream) return;
    setLoading(true);
    setError(null);
    try {
      const response = await streamApi.events(stream.id, {
        op: filters.op,
        only_rejected: filters.onlyRejected,
        order: filters.order,
        offset: filters.page * filters.limit,
        limit: filters.limit,
      });
      setEvents(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [stream?.id, filters.op, filters.onlyRejected, filters.order, filters.page, filters.limit]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!stream) return;
    void streamApi
      .arrivalStats(stream.id)
      .then((value) => setStats({ arrival_inversions: value.arrival_inversions, duplicate_rows: value.duplicate_rows }))
      .catch(() => setStats(null));
  }, [stream?.id]);

  const openEvent = async (eventId: string) => {
    setDetailError(null);
    try {
      setSelected(await eventApi.diff(eventId));
    } catch (err) {
      setDetailError(errorMessage(err));
    }
  };

  const diffRows: DiffRow[] = selected
    ? [
        ...selected.changed.map((item) => ({ field: item.field, before: item.before, after: item.after, kind: 'changed' })),
        ...selected.added.map((item) => ({ field: item.field, before: '∅', after: item.after, kind: 'added' })),
        ...selected.removed.map((item) => ({ field: item.field, before: item.before, after: '∅', kind: 'removed' })),
      ]
    : [];

  const pageCount = Math.max(1, Math.ceil(total / filters.limit));

  return (
    <div>
      <PanelHead
        title="事件浏览"
        sub={
          stream
            ? `${stream.name} · ${stream.source_table} · 水位线 ${formatLsn(stream.watermark_lsn)}`
            : '选择一个变更流'
        }
        actions={
          <select
            className="select"
            value={stream?.id ?? ''}
            onChange={(event) => selectStream(event.target.value)}
          >
            {(board?.streams ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}（{item.source_table}）
              </option>
            ))}
          </select>
        }
      />

      <div className="form-row" style={{ marginBottom: 12 }}>
        <div className="chip-row">
          <button className={`chip${filters.op === '' ? ' on' : ''}`} onClick={() => setOp('')}>
            全部 op
          </button>
          {(['insert', 'update', 'delete'] as const).map((op) => (
            <button key={op} className={`chip${filters.op === op ? ' on' : ''}`} onClick={() => setOp(op)}>
              {CDC_OP[op].label}
            </button>
          ))}
        </div>
        <div className="chip-row">
          <button className={`chip${filters.onlyRejected ? ' on' : ''}`} onClick={toggleRejected}>
            只看被拒绝
          </button>
          <button
            className={`chip${filters.order === 'lsn' ? ' on' : ''}`}
            onClick={() => setOrder('lsn')}
            title="按 LSN 升序（归并算法使用的顺序）"
          >
            LSN 序
          </button>
          <button
            className={`chip${filters.order === 'arrival' ? ' on' : ''}`}
            onClick={() => setOrder('arrival')}
            title="按收到顺序（会出现 LSN 逆序）"
          >
            到达序
          </button>
        </div>
        <span className="tiny faint" style={{ marginLeft: 'auto' }}>
          {stats ? (
            <>
              到达逆序 <span className="mono">{stats.arrival_inversions}</span> · 重复投递{' '}
              <span className="mono">{stats.duplicate_rows}</span>
            </>
          ) : (
            '统计数据加载中'
          )}
        </span>
      </div>

      {error ? <div className="notice danger">{error}</div> : null}

      <div className="split">
        <div className="panel">
          <div className="panel-head-sm">
            事件表
            <span style={{ marginLeft: 'auto' }} className="mono">
              {filters.page * filters.limit + (events.length ? 1 : 0)}-{filters.page * filters.limit + events.length} /{' '}
              {total}
            </span>
          </div>
          {loading && events.length === 0 ? (
            <div className="panel-body faint tiny">加载中…</div>
          ) : events.length === 0 ? (
            <div className="panel-body">
              <EmptyState
                title="当前筛选下没有事件"
                hint="清掉 op 过滤或取消「只看被拒绝」再试；也可以切换到达序看看投递顺序。"
                action={
                  <button className="btn small" onClick={() => { setOp(''); if (filters.onlyRejected) toggleRejected(); }}>
                    重置筛选
                  </button>
                }
              />
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th className="num">LSN</th>
                  <th>op</th>
                  <th>主键</th>
                  <th className="num">到达序号</th>
                  <th>拒绝原因</th>
                  <th>收到时间</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr
                    key={event.id}
                    className="row-click"
                    onClick={() => void openEvent(event.id)}
                    style={{ opacity: selected?.event.id === event.id ? 1 : undefined }}
                  >
                    <td className="num">{event.lsn_display}</td>
                    <td>
                      <StatusPill label={event.op_label} tone={CDC_OP[event.op].tone} />
                    </td>
                    <td className="mono tiny">{event.pk_value ?? <span className="faint">∅ 主键缺失</span>}</td>
                    <td className="num">{event.received_seq}</td>
                    <td>
                      {event.reject_reason ? (
                        <StatusPill
                          label={REJECT_REASON[event.reject_reason].label}
                          tone={REJECT_REASON[event.reject_reason].tone}
                        />
                      ) : (
                        <span className="faint tiny">—</span>
                      )}
                    </td>
                    <td className="tiny faint">{formatShortTime(event.received_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="form-row" style={{ padding: '8px 10px', justifyContent: 'flex-end' }}>
            <button className="btn small" disabled={filters.page === 0} onClick={() => setPage(filters.page - 1)}>
              上一页
            </button>
            <span className="tiny faint mono">
              {filters.page + 1}/{pageCount}
            </span>
            <button
              className="btn small"
              disabled={filters.page + 1 >= pageCount}
              onClick={() => setPage(filters.page + 1)}
            >
              下一页
            </button>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head-sm">单事件 diff（后端计算）</div>
          <div className="panel-body">
            {detailError ? <div className="notice danger">{detailError}</div> : null}
            {!selected ? (
              <EmptyState title="左侧点一行事件" hint="会展示 before / after 的字段级差异，以及该事件是否被拒绝。" />
            ) : (
              <>
                <div className="form-row" style={{ marginBottom: 10, gap: 10 }}>
                  <span className="mono tiny">LSN {selected.event.lsn_display}</span>
                  <StatusPill label={selected.event.op_label} tone={CDC_OP[selected.event.op].tone} />
                  <span className="mono tiny faint">pk={selected.event.pk_value ?? '∅'}</span>
                  <span className="tiny faint" style={{ marginLeft: 'auto' }}>
                    变更 {selected.summary.changed} · 新增 {selected.summary.added} · 移除 {selected.summary.removed}
                  </span>
                </div>
                {selected.event.reject_detail ? (
                  <div className="notice danger" style={{ marginBottom: 10 }}>
                    {selected.event.reject_detail}
                  </div>
                ) : null}
                <DiffTable rows={diffRows} emptyText="该事件 before 与 after 完全一致（只有位点变化）" />
                <div className="section-label" style={{ marginTop: 16 }}>
                  <span>未变化字段</span>
                </div>
                <div className="tiny faint mono">
                  {selected.unchanged.length === 0 ? '—' : selected.unchanged.map((item) => item.field).join(', ')}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
