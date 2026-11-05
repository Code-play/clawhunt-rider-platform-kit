import { useEffect, useState } from 'react';
import { isOffline } from '../api/client.js';

/** 统一的网络状态：真实 online/offline 事件 + 演示用模拟断网事件 + 3s 兜底轮询。 */
export function useNetworkStatus() {
  const [offline, setOffline] = useState(() => isOffline());

  useEffect(() => {
    const update = () => setOffline(isOffline());
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    window.addEventListener('rider:netchange', update);
    const timer = window.setInterval(update, 3000);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
      window.removeEventListener('rider:netchange', update);
      window.clearInterval(timer);
    };
  }, []);

  return offline;
}
