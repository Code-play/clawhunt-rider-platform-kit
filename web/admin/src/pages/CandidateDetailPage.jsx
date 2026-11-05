import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Progress,
  Row,
  Select,
  Skeleton,
  Space,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import {
  ArrowLeftOutlined,
  CheckCircleTwoTone,
  CloseCircleTwoTone,
  EditOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import * as api from '../api/client.js';
import DetokenizeModal from '../components/DetokenizeModal.jsx';
import {
  HEALTH_LABEL,
  JOB_TYPE_LABEL,
  SOURCE_LABEL,
  formatDateTime,
  intentText,
  statusMeta,
} from '../lib/utils.js';

const LEVEL_META = {
  recommend: { text: '建议面试', color: 'green', scoreColor: '#52c41a' },
  follow: { text: '可跟进', color: 'gold', scoreColor: '#faad14' },
  reject: { text: '暂不建议', color: 'red', scoreColor: '#ff4d4f' },
};

const ACTION_META = {
  confirm_interview: {
    title: '确认面试',
    reasonLabel: '确认理由（必填，写入留痕）',
    placeholder: '例如：电话沟通确认可到岗，安排本周面试',
    okText: '确认并生成日程',
  },
  handoff: {
    title: '转人工跟进',
    reasonLabel: '转人工原因（必填，写入留痕）',
    placeholder: '例如：候选人咨询住宿问题，需人工说明',
    okText: '转人工',
  },
  reject: {
    title: '标记不合适',
    reasonLabel: '不合适理由（必填，写入留痕）',
    placeholder: '例如：通勤距离过远，到岗时间不匹配',
    okText: '确认标记不合适',
  },
};

function toFormValues(detail) {
  return {
    name: '',
    phone: '',
    birth_ym: detail.birth_ym || '',
    area_text: detail.area_text || '',
    job_type: detail.job_type || undefined,
    has_ebike: detail.has_ebike == null ? undefined : detail.has_ebike,
    start_text: detail.start_text || '',
    experience_text: detail.experience_text || '',
    health_cert: detail.health_cert || undefined,
    station_id: detail.station_id || undefined,
  };
}

export default function CandidateDetailPage() {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [actionForm] = Form.useForm();

  const [detail, setDetail] = useState(null);
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editReason, setEditReason] = useState('');
  const [actionType, setActionType] = useState('');
  const [actionSubmitting, setActionSubmitting] = useState(false);
  const [detokOpen, setDetokOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [candidate, stationRes] = await Promise.all([
        api.getCandidate(candidateId),
        api.listStations().catch(() => ({ stations: [] })),
      ]);
      setDetail(candidate);
      setStations(stationRes.stations || []);
      form.setFieldsValue(toFormValues(candidate));
    } catch (err) {
      message.error(err.message || '候选人详情加载失败');
    } finally {
      setLoading(false);
    }
  }, [candidateId, form, message]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    let values;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    if (!detail) return;
    const diff = {};
    ['birth_ym', 'area_text', 'job_type', 'has_ebike', 'start_text', 'experience_text', 'health_cert', 'station_id'].forEach(
      (key) => {
        if (values[key] !== undefined && values[key] !== detail[key]) diff[key] = values[key];
      },
    );
    if (values.name && values.name.trim()) diff.name = values.name.trim();
    if (values.phone && values.phone.trim()) diff.phone = values.phone.trim();

    if (Object.keys(diff).length === 0) {
      message.info('没有检测到字段修改');
      return;
    }
    if (!editReason.trim()) {
      message.warning('保存修改必须填写修改原因（用于留痕）');
      return;
    }
    setSaving(true);
    try {
      const updated = await api.patchCandidate(candidateId, {
        fields: diff,
        reason: editReason.trim(),
      });
      setDetail(updated);
      form.setFieldsValue(toFormValues(updated));
      setEditReason('');
      message.success('已保存更正并写入修改留痕');
    } catch (err) {
      message.error(err.message || '保存失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  const openAction = (type) => {
    setActionType(type);
    actionForm.resetFields();
  };

  const submitAction = async () => {
    let values;
    try {
      values = await actionForm.validateFields();
    } catch {
      return;
    }
    setActionSubmitting(true);
    try {
      const payload = { action: actionType, reason: values.reason };
      if (actionType === 'confirm_interview') payload.slot_start = values.slot_start;
      const updated = await api.runCandidateAction(candidateId, payload);
      setDetail(updated);
      setActionType('');
      actionForm.resetFields();
      message.success(
        actionType === 'confirm_interview'
          ? '已确认面试并生成日程'
          : actionType === 'handoff'
            ? '已转人工跟进'
            : '已标记不合适',
      );
    } catch (err) {
      message.error(err.message || '操作失败，请稍后重试');
    } finally {
      setActionSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="page-stack">
        <Skeleton active paragraph={{ rows: 4 }} />
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    );
  }

  if (!detail) {
    return (
      <Alert
        type="error"
        showIcon
        message="候选人不存在或加载失败"
        action={<Button onClick={() => navigate('/candidates')}>返回列表</Button>}
      />
    );
  }

  const status = statusMeta(detail.status);
  const qualification = detail.qualification || { level: 'follow', score: 0, rules: [], suggestion: '' };
  const levelMeta = LEVEL_META[qualification.level] || LEVEL_META.follow;
  const slotOptions = (detail.interview_slots || [])
    .filter((slot) => slot.available)
    .map((slot) => ({ value: slot.slot_start, label: slot.label }));
  const actionMeta = ACTION_META[actionType] || ACTION_META.handoff;

  return (
    <div className="page-stack">
      <Card size="small">
        <div className="detail-head">
          <Space size={12} wrap align="center">
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/candidates')}>
              返回列表
            </Button>
            <span className="detail-name">{detail.name_masked}</span>
            <Tag color={status.color}>{status.text}</Tag>
            <Tag color="blue">{SOURCE_LABEL[detail.source_channel] || detail.source_channel}</Tag>
            <Tag>意向度：{intentText(detail.intent_level)}</Tag>
            <Tag color="purple">AI 建档</Tag>
          </Space>
          <Space wrap>
            <Button icon={<SafetyCertificateOutlined />} onClick={() => setDetokOpen(true)}>
              查看完整手机号
            </Button>
            <Button type="primary" onClick={() => openAction('confirm_interview')}>
              确认面试
            </Button>
            <Button onClick={() => openAction('handoff')}>转人工跟进</Button>
            <Button danger onClick={() => openAction('reject')}>
              标记不合适
            </Button>
          </Space>
        </div>
        <Descriptions
          size="small"
          column={{ xs: 1, md: 2, xl: 4 }}
          style={{ marginTop: 12 }}
          items={[
            { key: 'phone', label: '手机号', children: <span className="mono">{detail.phone_masked}</span> },
            { key: 'station', label: '意向站点', children: detail.station_name || '-' },
            { key: 'area', label: '跑单区域', children: detail.area_text || '-' },
            { key: 'created', label: '建档时间', children: formatDateTime(detail.created_at) },
          ]}
        />
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card
            size="small"
            title={
              <Space>
                AI 建档字段
                <Tag color="blue">可更正</Tag>
              </Space>
            }
            extra={
              <Space>
                <Button
                  onClick={() => {
                    form.setFieldsValue(toFormValues(detail));
                    setEditReason('');
                  }}
                >
                  还原
                </Button>
                <Button type="primary" icon={<EditOutlined />} loading={saving} onClick={save}>
                  保存更正
                </Button>
              </Space>
            }
          >
            <Form form={form} layout="vertical" requiredMark={false}>
              <Row gutter={[12, 0]}>
                <Col xs={24} md={8}>
                  <Form.Item name="name" label="姓名（更正时填写，留空不改）">
                    <Input placeholder={`当前：${detail.name_masked}`} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item
                    name="phone"
                    label="手机号（更正时填写，留空不改）"
                    rules={[{ pattern: /^1\d{10}$/, message: '请输入 11 位手机号' }]}
                  >
                    <Input placeholder={`当前：${detail.phone_masked}`} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="birth_ym" label="出生年月">
                    <Input placeholder="YYYY-MM" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="area_text" label="跑单区域">
                    <Input placeholder="如 浦东新区" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="job_type" label="工作类型">
                    <Select
                      placeholder="请选择"
                      options={Object.entries(JOB_TYPE_LABEL).map(([value, label]) => ({
                        value,
                        label,
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="has_ebike" label="是否有电动车">
                    <Select
                      placeholder="请选择"
                      options={[
                        { value: true, label: '有' },
                        { value: false, label: '没有' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="start_text" label="可到岗时间">
                    <Input placeholder="如 明天 / 本周内" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="health_cert" label="健康证">
                    <Select
                      placeholder="请选择"
                      options={Object.entries(HEALTH_LABEL).map(([value, label]) => ({
                        value,
                        label,
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="station_id" label="意向站点">
                    <Select
                      placeholder="请选择"
                      options={stations.map((s) => ({ value: s.id, label: s.name }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24}>
                  <Form.Item name="experience_text" label="配送经验">
                    <Input.TextArea rows={2} placeholder="如 2 年外卖配送经验" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="修改原因（保存前必填，写入留痕）" required>
                <Input.TextArea
                  rows={2}
                  value={editReason}
                  onChange={(e) => setEditReason(e.target.value)}
                  maxLength={200}
                  showCount
                  placeholder="例如：电话沟通后补充真实跑单区域"
                />
              </Form.Item>
            </Form>
            <Alert
              type="info"
              showIcon
              message="所有字段修改都会记录「改前 → 改后 + 原因 + 操作人 + 时间」，见右侧留痕。"
            />
          </Card>

          <Card size="small" title="资格初筛建议（AI 辅助）" style={{ marginTop: 16 }}>
            <div className="qual-head">
              <Tag color={levelMeta.color} style={{ fontSize: 14, padding: '2px 10px' }}>
                {levelMeta.text}
              </Tag>
              <Progress
                percent={qualification.score}
                size="small"
                strokeColor={levelMeta.scoreColor}
                style={{ flex: 1, minWidth: 160 }}
              />
              <span className="muted">综合得分 {qualification.score}</span>
            </div>
            <Alert
              style={{ margin: '10px 0' }}
              type={
                qualification.level === 'recommend'
                  ? 'success'
                  : qualification.level === 'follow'
                    ? 'warning'
                    : 'error'
              }
              showIcon
              message={qualification.suggestion}
            />
            <List
              size="small"
              dataSource={qualification.rules}
              renderItem={(rule) => (
                <div className="rule-row">
                  <span>
                    {rule.pass ? (
                      <CheckCircleTwoTone twoToneColor="#52c41a" />
                    ) : (
                      <CloseCircleTwoTone twoToneColor="#ff4d4f" />
                    )}{' '}
                    {rule.rule}
                  </span>
                  <span className="muted">{rule.note}</span>
                </div>
              )}
            />
            <p className="card-note">AI 初筛仅为辅助建议，最终以招聘专员判断与站点面试结论为准。</p>
          </Card>

          <Card size="small" title="对话摘要（AI）" style={{ marginTop: 16 }}>
            <Typography.Paragraph>{detail.conversation_summary}</Typography.Paragraph>
            <Space wrap>
              {(detail.conversation_key_points || []).map((point) => (
                <Tag key={point}>{point}</Tag>
              ))}
            </Space>
            <Collapse
              ghost
              style={{ marginTop: 8 }}
              items={[
                {
                  key: 'transcript',
                  label: `查看完整对话（AI 转写，共 ${(detail.transcript || []).length} 条）`,
                  children: (
                    <div className="transcript">
                      {(detail.transcript || []).map((msg, index) => (
                        <div key={`${msg.ts}-${index}`} className={`transcript-row ${msg.role}`}>
                          <span className="transcript-role">{msg.role === 'ai' ? 'AI' : '求职者'}</span>
                          <div className="transcript-bubble">{msg.text}</div>
                        </div>
                      ))}
                    </div>
                  ),
                },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} xl={8}>
          <Card
            size="small"
            title="操作记录与修改留痕"
            extra={<Tag>{detail.audit_log ? detail.audit_log.length : 0} 条</Tag>}
          >
            {detail.audit_log && detail.audit_log.length > 0 ? (
              <Timeline
                items={detail.audit_log.map((item) => ({
                  color: 'blue',
                  children: (
                    <div className="audit-item">
                      <div>
                        <b>{item.field}</b>：{item.from} → {item.to}
                      </div>
                      <div className="muted small">
                        {item.operator} · {formatDateTime(item.at)}
                      </div>
                      <div className="audit-reason">理由：{item.reason}</div>
                    </div>
                  ),
                }))}
              />
            ) : (
              <Empty description="暂无留痕" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>

          <Card size="small" title="授权与合规" style={{ marginTop: 16 }}>
            <Descriptions
              column={1}
              size="small"
              items={[
                { key: 'version', label: '告知书版本', children: detail.consent_version },
                { key: 'at', label: '同意时间', children: formatDateTime(detail.consent_at) },
                {
                  key: 'source',
                  label: '来源渠道',
                  children: SOURCE_LABEL[detail.source_channel] || detail.source_channel,
                },
                { key: 'updated', label: '最近更新', children: formatDateTime(detail.updated_at) },
              ]}
            />
            <Alert
              type="warning"
              showIcon
              style={{ marginTop: 8 }}
              message="完整手机号填写理由后仅展示一次，不写前端缓存。"
            />
          </Card>

          <Card size="small" title="面试安排" style={{ marginTop: 16 }}>
            {detail.interviews && detail.interviews.length > 0 ? (
              <Timeline
                items={detail.interviews.map((interview) => ({
                  children: (
                    <div>
                      <b>{formatDateTime(interview.slot_start)}</b>
                      <div className="muted">
                        {interview.station_name} ·{' '}
                        {interview.status === 'booked'
                          ? '待面试'
                          : interview.status === 'done'
                            ? '已到访'
                            : interview.status === 'no_show'
                              ? '未到访'
                              : '已取消'}
                      </div>
                    </div>
                  ),
                }))}
              />
            ) : (
              <Empty description="暂无面试安排" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      <DetokenizeModal
        open={detokOpen}
        token={detail.phone_token}
        fieldLabel="手机号"
        onClose={() => setDetokOpen(false)}
      />

      <Modal
        open={Boolean(actionType)}
        title={
          <Space>
            {actionMeta.title}
            <Tag color="orange">理由必填</Tag>
          </Space>
        }
        onCancel={() => {
          setActionType('');
          actionForm.resetFields();
        }}
        onOk={submitAction}
        okText={actionMeta.okText}
        cancelText="取消"
        confirmLoading={actionSubmitting}
        okButtonProps={{ danger: actionType === 'reject' }}
        destroyOnClose
      >
        <Form form={actionForm} layout="vertical" requiredMark>
          {actionType === 'confirm_interview' ? (
            <Form.Item
              name="slot_start"
              label="面试时段"
              rules={[{ required: true, message: '请选择面试时段' }]}
            >
              <Select placeholder="选择可约时段" options={slotOptions} />
            </Form.Item>
          ) : null}
          <Form.Item
            name="reason"
            label={actionMeta.reasonLabel}
            rules={[
              { required: true, message: '请填写理由后才能提交' },
              { min: 2, message: '理由至少 2 个字' },
            ]}
          >
            <Input.TextArea rows={3} maxLength={200} showCount placeholder={actionMeta.placeholder} />
          </Form.Item>
          {actionType === 'reject' ? (
            <Space wrap>
              {['通勤距离过远', '到岗时间不匹配', '区域不匹配', '资质/年龄不符'].map((tag) => (
                <Tag
                  key={tag}
                  className="clickable-tag"
                  onClick={() => {
                    const prev = actionForm.getFieldValue('reason') || '';
                    actionForm.setFieldValue('reason', prev ? `${prev}；${tag}` : tag);
                  }}
                >
                  + {tag}
                </Tag>
              ))}
            </Space>
          ) : null}
        </Form>
      </Modal>
    </div>
  );
}
