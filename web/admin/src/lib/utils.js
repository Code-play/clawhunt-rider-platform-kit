import dayjs from 'dayjs';

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
  if (chars.length <= 2) return `${chars[0]}*`;
  return `${chars[0]}${'*'.repeat(chars.length - 1)}`;
}

export function formatDateTime(value) {
  if (!value) return '-';
  const d = dayjs(value);
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : String(value);
}

export function formatDate(value) {
  if (!value) return '-';
  const d = dayjs(value);
  return d.isValid() ? d.format('YYYY-MM-DD') : String(value);
}

export function formatSlot(value) {
  if (!value) return '-';
  const d = dayjs(value);
  return d.isValid() ? d.format('MM-DD HH:mm') : String(value);
}

export const STATUS_META = {
  new: { text: '新线索', color: 'default' },
  collecting: { text: '收集中', color: 'processing' },
  complete: { text: '资料完整', color: 'blue' },
  booked: { text: '已预约', color: 'gold' },
  interviewed: { text: '已面试', color: 'cyan' },
  hired: { text: '已入职', color: 'green' },
  rejected: { text: '已结束', color: 'red' },
  handoff: { text: '已转人工', color: 'purple' },
};

export const SOURCE_LABEL = {
  douyin: '抖音短视频',
  wechat: '微信好友',
  moments: '朋友圈广告',
  offline_poster: '线下海报',
  referral: '老骑手推荐',
  direct: '直接访问',
  direct_link: '直接访问',
};

export const JOB_TYPE_LABEL = {
  fulltime: '全职',
  parttime: '兼职',
  undecided: '还没想好',
};

export const HEALTH_LABEL = {
  yes: '有',
  no: '无',
  unsure: '待确认',
};

export function statusMeta(value) {
  return STATUS_META[value] || { text: value || '-', color: 'default' };
}

export function jobTypeText(value) {
  return JOB_TYPE_LABEL[value] || value || '-';
}

export function intentText(level) {
  if (!level) return '-';
  if (level >= 5) return '高';
  if (level === 4) return '较高';
  if (level === 3) return '中';
  return '低';
}

export const FIELD_LABELS = {
  name: '姓名',
  name_token: '姓名',
  name_masked: '姓名',
  phone: '手机号',
  phone_token: '手机号',
  phone_masked: '手机号',
  birth_ym: '出生年月',
  area_text: '跑单区域',
  job_type: '工作类型',
  has_ebike: '是否有电动车',
  start_text: '可到岗时间',
  experience_text: '配送经验',
  health_cert: '健康证',
  station_id: '意向站点',
  status: '状态',
};
