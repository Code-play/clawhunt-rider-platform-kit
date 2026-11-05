/**
 * 轻量 localStorage 封装：所有键统一前缀，便于「撤回授权并删除」时整体清理。
 * 注意：仅存会话/进度/候选人与渠道等非敏感缓存；完整手机号/姓名不落前端存储。
 */
const PREFIX = 'rider.h5.';

export const KEYS = {
  channel: 'channel',
  consent: 'consent',
  candidate: 'candidate',
  session: 'session',
  messages: 'messages',
  progress: 'progress',
  booking: 'booking',
  outbox: 'outbox',
};

export function load(key, fallback = null) {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (raw == null) return fallback;
    return JSON.parse(raw);
  } catch (err) {
    console.warn('[storage] 读取失败，使用默认值:', key, err);
    return fallback;
  }
}

export function save(key, value) {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch (err) {
    console.warn('[storage] 写入失败（可能是隐私模式/配额）:', key, err);
  }
}

export function remove(key) {
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch (err) {
    console.warn('[storage] 删除失败:', key, err);
  }
}

export function clearAll() {
  try {
    Object.keys(window.localStorage)
      .filter((k) => k.startsWith(PREFIX))
      .forEach((k) => window.localStorage.removeItem(k));
  } catch (err) {
    console.warn('[storage] 清理失败:', err);
  }
}

export function uid(prefix = 'id') {
  const rnd =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36);
  return `${prefix}_${rnd}`;
}
