import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PanelHead } from '../components/common/PanelHead';
import { StatusPill } from '../components/common/StatusPill';
import { EmptyState } from '../components/common/EmptyState';
import { MetricStrip } from '../components/common/MetricStrip';
import { RequireRole } from '../components/common/RequireRole';
import { RUN_STATUS } from '../constants/cdc';
import { useAuthStore } from '../stores/authStore';
import { useRunStore } from '../stores/runStore';
import { useStreamStore } from '../stores/streamStore';
import { formatMs, formatLsn, formatShortTime } from '../utils/format';

/** 归并运行：选窗口 → 发起 → 列表里看进度/结果。发起动作在 viewer 下被后端 403 拒绝。 */
export const RunsPage = () => {
  const board = useStreamStore((state) => state.board);
  const selectedStreamId = useStreamStore((state) => state.selectedStreamId);
  const selectStream = useStreamStore((state) => state.selectStream);
  const runs = useRunStore((state) => state.runs);
  const starting = useRunStore((state) => state.starting);
  const error = useRunStore((state) => state.error);
  const loadRuns = useRunStore((state) => state.loadRuns);
  const startRun = useRunStore((state) => state.startRun);
  const canTrigger = useAuthStore((state) => state.can('runs:trigger'));
  const role = useAuthStore((state) => state.user?.role);
  const navigate = useNavigate();

  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');

  const stream = board?.streams.find((item) => item.id === selectedStreamId) ?? board?.streams[0] ?? null;

  useEffect(() => {
    void loadRuns(stream?.id);
  }, [loadRuns, stream?.id]);

  const submit = async () => {
    if (!stream) return;
    const startValue = start.trim() === '' ? null : Number(start);
    const endValue = end.trim() === '' ? null : Number(end);
    const run = await startRun(stream.id, startValue, endValue);
    if (run) navigate(`/runs/${run.id}`);
  };

  return (
    <div>
      <PanelHead
        title="归并运行"
        sub={
          stream
            ? `${stream.name} · 水位线 ${formatLsn(stream.watermark_lsn)} → 最新 ${formatLsn(stream.max_lsn)}`
            : '选择变更流'
        }
        actions={
          <select className="select" value={stream?.id ?? ''} onChange={(event) => selectStream(event.target.value)}>
            {(board?.streams ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        }
      />

      <MetricStrip
        items={[
          { label: '当前角色', value: role ?? '—', note: canTrigger ? '可发起运行' : '只读，发起会被 403' },
          {
            label: '水位线',
            value: stream ? formatLsn(stream.watermark_lsn) : '—',
            note: '最小未处理 LSN 之前',
          },
          {
            label: '积压事件',
            value: stream ? String(stream.lag) : '—',
            tone: stream && stream.lag > 0 ? 'amber' : 'ok',
            note: 'max_lsn - watermark',
          },
          { label: '本流运行次数', value: String(runs.length), note: '按创建时间倒序' },
        ]}
      />

      <div className="section">
        <div className="section-label">
          <span>发起一次归并</span>
        </div>
        <div className="panel">
          <div className="panel-body">
            <div className="form-row">
              <label className="field">
                <span className="field-label">窗口起始 LSN（留空 = 水位线+1）</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  data-testid="window-start"
                  placeholder="1"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                  style={{ width: 220 }}
                />
              </label>
              <label className="field">
                <span className="field-label">窗口结束 LSN（留空 = 最新）</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  data-testid="window-end"
                  placeholder={stream ? String(stream.max_lsn) : '37'}
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                  style={{ width: 220 }}
                />
              </label>
              <RequireRole
                permission="runs:trigger"
                fallback={
                  <div className="notice" style={{ flex: 1 }} data-testid="trigger-guard">
                    当前角色是 <span className="mono">{role}</span>，只能看运行结果。发起归并需要 admin 或 engineer。
                  </div>
                }
              >
                <button
                  className="btn primary"
                  data-testid="trigger-run"
                  onClick={() => void submit()}
                  disabled={starting || !stream}
                >
                  {starting ? '投递中…' : '发起归并'}
                </button>
              </RequireRole>
            </div>
            <p className="tiny faint" style={{ marginTop: 10 }}>
              后台由 Celery worker 执行：按 LSN 排序去重 → 应用 insert/update/delete → 金额守恒校验 → 落账并推进水位线。
              同一窗口重复运行会得到相同 digest，结果页会标记「幂等」。
            </p>
            {error ? <div className="notice danger" style={{ marginTop: 10 }}>{error}</div> : null}
          </div>
        </div>
      </div>

      <div className="section">
        <div className="section-label">
          <span>运行记录</span>
        </div>
        {runs.length === 0 ? (
          <EmptyState title="这条流还没有运行记录" hint="设置窗口后点「发起归并」，或先跑一次 seed 演示数据。" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>运行</th>
                <th>状态</th>
                <th>窗口</th>
                <th className="num">收到</th>
                <th className="num">处理</th>
                <th className="num">重复</th>
                <th className="num">拒绝</th>
                <th className="num">落账行</th>
                <th className="num">耗时</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run, index) => {
                const tone = RUN_STATUS[run.status].tone;
                return (
                  <tr
                    key={run.id}
                    className="row-click stagger"
                    style={{ animationDelay: `${index * 24}ms` }}
                    onClick={() => navigate(`/runs/${run.id}`)}
                  >
                    <td className="mono tiny">{run.id.slice(0, 8)}</td>
                    <td>
                      <StatusPill label={run.status_label} tone={tone} running={RUN_STATUS[run.status].running} />
                    </td>
                    <td className="mono tiny">
                      {run.window_start_lsn} → {run.window_end_lsn}
                    </td>
                    <td className="num">{run.received_count}</td>
                    <td className="num">{run.processed_count}</td>
                    <td className="num" style={{ color: run.duplicate_count > 0 ? 'var(--color-amber)' : undefined }}>
                      {run.duplicate_count}
                    </td>
                    <td className="num" style={{ color: run.rejected_count > 0 ? 'var(--color-danger)' : undefined }}>
                      {run.rejected_count}
                    </td>
                    <td className="num">{run.upserted_count}</td>
                    <td className="num">{formatMs(run.duration_ms)}</td>
                    <td className="tiny faint">{formatShortTime(run.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
