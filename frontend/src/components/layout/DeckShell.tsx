import type { ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import { useStreamStore } from '../../stores/streamStore';
import { ROLE_LABEL } from '../../constants/cdc';

const NAV = [
  { to: '/streams', label: '变更流看板', key: 'streams' },
  { to: '/events', label: '事件浏览', key: 'events' },
  { to: '/runs', label: '归并运行', key: 'runs' },
  { to: '/rejected', label: '拒绝与重放', key: 'rejected' },
  { to: '/schema', label: 'schema 演进', key: 'schema' },
];

/** 值班管制台外壳：左侧导航 + 顶部条 + 底部值班事实。无卡片、无阴影、无圆角。 */
export const DeckShell = ({ children }: { children: ReactNode }) => {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const board = useStreamStore((state) => state.board);
  const navigate = useNavigate();
  const location = useLocation();

  const hint = (key: string): string => {
    if (!board) return '';
    if (key === 'streams') return String(board.totals.stream_count);
    if (key === 'events') return String(board.totals.event_count);
    if (key === 'runs') return board.totals.active_runs > 0 ? `${board.totals.active_runs}▶` : '·';
    if (key === 'rejected') return String(board.totals.pending_rejected);
    if (key === 'schema') return 'v1/v2';
    return '';
  };

  const activeKey = NAV.find((item) => location.pathname.startsWith(item.to))?.key ?? 'streams';

  return (
    <div className="shell">
      <div className="brand">
        <span className="brand-mark">⇄</span>
        <div>
          <div className="brand-name">cdcmerge</div>
          <span className="brand-tag">北岸生活 · 数据平台</span>
        </div>
      </div>

      <div className="topbar">
        <span className="topbar-title">CDC 增量合并与 schema 演进工作台</span>
        <span className="topbar-spacer" />
        <div className="topbar-actor">
          <span className="pill muted" title="当前角色">
            {user ? ROLE_LABEL[user.role] : '未登录'}
          </span>
          <span className="mono tiny">{user?.email ?? ''}</span>
          <button
            className="btn small"
            onClick={() => {
              logout();
              navigate('/login', { replace: true });
            }}
          >
            退出
          </button>
        </div>
      </div>

      <nav className="nav">
        <div className="nav-label">值班席位</div>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <span>{item.label}</span>
            <span className="nav-hint">{hint(item.key)}</span>
          </NavLink>
        ))}
        <div className="nav-foot">
          <span>
            事件合计 <span className="mono">{board?.totals.event_count ?? '—'}</span>
          </span>
          <span>
            待处理拒绝 <span className="mono">{board?.totals.pending_rejected ?? '—'}</span>
          </span>
          <span>
            成功率{' '}
            <span className="mono">
              {board && board.run_stats.total_runs > 0
                ? `${Math.round((board.run_stats.succeeded_runs / board.run_stats.total_runs) * 100)}%`
                : '—'}
            </span>
          </span>
          <span className="faint">航线 {activeKey}</span>
        </div>
      </nav>

      <main className="main">{children}</main>
    </div>
  );
};
