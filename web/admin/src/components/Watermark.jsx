import { useMemo } from 'react';
import dayjs from 'dayjs';

/**
 * 页面个人水印（姓名 · 工号 · 日期），全局覆盖层、CSS 平铺、pointer-events: none。
 * 不拦截任何点击，也不参与业务数据。
 */
export default function Watermark({ user }) {
  const backgroundImage = useMemo(() => {
    const text = `${(user && user.name) || '未登录'} · ${(user && user.employee_no) || '-'} · ${dayjs().format(
      'YYYY-MM-DD',
    )}`;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="170"><text x="10" y="95" transform="rotate(-24 10 95)" fill="rgba(15,23,42,0.10)" font-size="13" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Microsoft YaHei,sans-serif">${text}</text></svg>`;
    return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
  }, [user]);

  return <div className="watermark-layer" style={{ backgroundImage }} aria-hidden="true" />;
}
