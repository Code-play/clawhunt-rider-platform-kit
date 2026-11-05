import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  App,
  Button,
  Card,
  Col,
  Form,
  InputNumber,
  Modal,
  Progress,
  Row,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import { EditOutlined, EnvironmentOutlined, ReloadOutlined } from '@ant-design/icons';
import * as api from '../api/client.js';

export default function StationsPage() {
  const { message } = App.useApp();
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listStations();
      setStations(res.stations || []);
    } catch (err) {
      message.error(err.message || '站点加载失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    load();
  }, [load]);

  const stats = useMemo(() => {
    const totalQuota = stations.reduce((sum, s) => sum + s.open_quota, 0);
    const totalBooked = stations.reduce((sum, s) => sum + s.booked, 0);
    const totalRemaining = stations.reduce((sum, s) => sum + s.remaining, 0);
    const fullCount = stations.filter((s) => s.status === 'full').length;
    return { totalQuota, totalBooked, totalRemaining, fullCount };
  }, [stations]);

  const openEdit = (station) => {
    setEditing(station);
    form.setFieldsValue({ open_quota: station.open_quota });
  };

  const saveQuota = async () => {
    let values;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSaving(true);
    try {
      await api.updateStationQuota(editing.id, values.open_quota);
      message.success(`已更新「${editing.name}」在招名额为 ${values.open_quota}`);
      setEditing(null);
      await load();
    } catch (err) {
      message.error(err.message || '名额更新失败');
    } finally {
      setSaving(false);
    }
  };

  const columns = [
    {
      title: '站点',
      dataIndex: 'name',
      width: 210,
      render: (value, record) => (
        <Space direction="vertical" size={0}>
          <Space size={6}>
            <EnvironmentOutlined style={{ color: '#1677ff' }} />
            <b>{value}</b>
          </Space>
          <span className="muted">{record.address}</span>
        </Space>
      ),
    },
    { title: '区域', dataIndex: 'area', width: 110 },
    {
      title: '在招名额',
      dataIndex: 'open_quota',
      width: 110,
      sorter: (a, b) => a.open_quota - b.open_quota,
      render: (value) => <b>{value}</b>,
    },
    { title: '已约', dataIndex: 'booked', width: 90 },
    {
      title: '剩余名额',
      dataIndex: 'remaining',
      width: 200,
      render: (value, record) => {
        const percent = record.open_quota
          ? Math.min(100, Math.round((record.booked / record.open_quota) * 100))
          : 0;
        return (
          <Space direction="vertical" size={2} style={{ width: '100%' }}>
            <Space size={8}>
              <b style={{ color: value > 0 ? '#1677ff' : '#ff4d4f' }}>{value}</b>
              <span className="muted">
                已约 {record.booked}/{record.open_quota}
              </span>
            </Space>
            <Progress
              percent={percent}
              size="small"
              status={value === 0 ? 'exception' : 'normal'}
              showInfo={false}
            />
          </Space>
        );
      },
    },
    { title: '今日到访', dataIndex: 'today_visits', width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value) =>
        value === 'full' ? <Tag color="red">名额已满</Tag> : <Tag color="green">在招</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) => (
        <Button icon={<EditOutlined />} onClick={() => openEdit(record)}>
          调整名额
        </Button>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="在招名额合计" value={stats.totalQuota} suffix="人" />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="已约名额" value={stats.totalBooked} suffix="人" />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="剩余名额"
              value={stats.totalRemaining}
              suffix="人"
              valueStyle={{ color: stats.totalRemaining > 0 ? '#1677ff' : '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="满员站点" value={stats.fullCount} suffix="个" />
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        title={
          <Space>
            <EnvironmentOutlined />
            站点与名额管理
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={load}>
            刷新
          </Button>
        }
      >
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          名额调整会实时影响 H5 端站点推荐卡展示的「在招人数」；已约 / 剩余按当前预约统计。
        </Typography.Paragraph>
        {loading ? (
          <Skeleton active paragraph={{ rows: 6 }} />
        ) : (
          <Table
            rowKey="id"
            size="middle"
            columns={columns}
            dataSource={stations}
            pagination={false}
            scroll={{ x: 1000 }}
          />
        )}
      </Card>

      <Modal
        open={Boolean(editing)}
        title={`调整在招名额 · ${editing ? editing.name : ''}`}
        onCancel={() => setEditing(null)}
        onOk={saveQuota}
        okText="保存名额"
        cancelText="取消"
        confirmLoading={saving}
        destroyOnClose
      >
        <Form form={form} layout="vertical" requiredMark>
          <Form.Item
            name="open_quota"
            label="在招名额（0-99）"
            rules={[{ required: true, message: '请输入在招名额' }]}
          >
            <InputNumber min={0} max={99} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          {editing ? (
            <Typography.Text type="secondary">
              当前：在招 {editing.open_quota} 人，已约 {editing.booked} 人，剩余 {editing.remaining} 人。
              名额调低到已约人数以下时，剩余按 0 展示。
            </Typography.Text>
          ) : null}
        </Form>
      </Modal>
    </div>
  );
}
