/** 展示/脱敏/时间等纯函数工具（H5 端不出现任何完整敏感值）。 */

export function maskPhone(phone) {
  if (!phone) return '';
  const digits = String(phone).replace(/\D/g, '');
  if (digits.length === 11) return `${digits.slice(0, 3)}****${digits.slice(7)}`;
  if (digits.length > 4) return `${digits.slice(0, 2)}****${digits.slice(-2)}`;
  return '****';
}

export function maskName(name) {
  if (!name) return '';
  const chars = Array.from(String(name));
  if (chars.length === 1) return `${chars[0]}*`;
  if (chars.length === 2) return `${chars[0]}*`;
  return `${chars[0]}${'*'.repeat(chars.length - 1)}`;
}

export function formatDateTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

export function formatDate(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 出生年月（YYYY-MM）→ 周岁；解析失败返回 null。 */
export function ageFromBirthYm(birthYm) {
  if (!birthYm) return null;
  const m = String(birthYm).match(/^(\d{4})-(\d{2})$/);
  if (!m) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  if (month < 1 || month > 12) return null;
  const now = new Date();
  let age = now.getFullYear() - year;
  if (now.getMonth() + 1 < month) age -= 1;
  return age;
}

/** 固定的站点坐标距离（H5 不采集精确定位，避免过度收集；用区域中心做近似）。 */
export function distanceKm(a, b) {
  const R = 6371;
  const toRad = (v) => (v * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return Math.round(2 * R * Math.asin(Math.sqrt(h)) * 10) / 10;
}

export function slotLabel(slotStart) {
  if (!slotStart) return '';
  const d = new Date(slotStart.replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return slotStart;
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()];
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}月${d.getDate()}日 ${week} ${pad(d.getHours())}:${pad(
    d.getMinutes(),
  )}`;
}

export function jobTypeText(v) {
  return { fulltime: '全职', parttime: '兼职', undecided: '还没想好' }[v] || v || '-';
}

export function hasEbikeText(v) {
  if (v === true) return '有';
  if (v === false) return '没有';
  return '-';
}

export function statusText(v) {
  return (
    {
      new: '新线索',
      collecting: '收集中',
      complete: '资料完整',
      booked: '已预约',
      interviewed: '已面试',
      hired: '已入职',
      rejected: '已结束',
      handoff: '已转人工',
    }[v] || v || '-'
  );
}
