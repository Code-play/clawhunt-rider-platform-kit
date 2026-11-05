import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AiFooter, NetBanner } from './ui.jsx';
import { useNetworkStatus } from '../lib/network.js';
import { useRider } from '../state/RiderContext.jsx';

const TITLES = {
  '/': '骑手招募助手',
  '/consent': '告知与同意',
  '/chat': 'AI 招聘对话',
  '/stations': '附近站点',
  '/me': '我的信息',
};

function titleFor(pathname) {
  if (pathname.startsWith('/result/')) return '预约结果';
  if (pathname.startsWith('/book/')) return '选择时段';
  return TITLES[pathname] || '骑手招募助手';
}

/**
 * 全局 Layout：顶栏 + 内容区 + 断网提示 + 固定的 AI 身份标识。
 * 每一屏的「本服务由 AI 提供 · 可随时转人工」只在 AiFooter 里实现一次。
 */
export default function AppLayout({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { hasConsent } = useRider();
  const offline = useNetworkStatus();
  const pathname = location.pathname;
  const isChat = pathname === '/chat';

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="topbar">
          {pathname === '/' ? (
            <span className="brand">
              <span className="brand-mark" aria-hidden="true">
                骑
              </span>
              骑手招募
            </span>
          ) : (
            <button
              type="button"
              className="icon-btn"
              onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/'))}
              aria-label="返回上一页"
            >
              ← 返回
            </button>
          )}
          <span className="topbar-title">{titleFor(pathname)}</span>
          {hasConsent && pathname !== '/me' ? (
            <Link className="text-link" to="/me">
              我的信息
            </Link>
          ) : (
            <span className="topbar-spacer" aria-hidden="true" />
          )}
        </div>
        <NetBanner offline={offline} />
      </header>

      <main className={isChat ? 'page chat-page' : 'page'}>{children}</main>

      <AiFooter />
    </div>
  );
}
