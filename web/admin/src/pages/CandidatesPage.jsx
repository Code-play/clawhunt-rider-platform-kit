import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Button, Card, Col, Input, Rate, Row, Select, Space, Table, Tag, Typography } from 'antd';
import { LockOutlined, ReloadOutlined } from '@ant-design/icons';
import * as api from '../api/client.js';
import {
  SOURCE_LABEL,
  formatDateTime,
  intentText,
  statusMeta,
} from '../lib/utils.js';

const STATUS_LIST = [
  { value: 'new', label: '新线索' },
  { value: 'collecting', label: '收集中' },
  { value: 'complete', label: '资料完整' },
  { value: 'booked', label: '已预约' },
  { value: 'interviewed', label: '已面试' },
  { value: 'hired', label: '已入职' },
  { value: 'rejected', label: '已结束' },
  { value: 'handoff', label: '已转人工' },
];

const PAGE_SIZE = 8;

export default function CandidatesPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [loading, setLoading] = useState(true);
  const [stations, setStations] = useState([]);
  const [keyword, setKeyword] = useState('');
  const [filters, setFilters] = useState({
    q: '',
    status: '',
    source_channel: '',
    station_id: '',
    intent_level: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listCandidates({
        ...filters,
        page,
        page_size: pageSize,
      });
      setRows(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      message.error(err.message || '候选人列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [filters, page, pageSize, message]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api
      .listStations()
      .then((res) => setStations(res.stations || []))
      .catch(() => setStations([]));
  }, []);

  const sourceOptions = useMemo(
    () => Object.entries(SOURCE_LABEL).map(([value, label]) => ({ value, label })),
    [],
  );
  const stationOptions = useMemo(
    () => stations.map((s) => ({ value: s.id, label: s.name })),
    [stations],
  );

  const applyKeyword = (value) => {
    setPage(1);
    setFilters((prev) => ({ ...prev, q: value.trim() }));
  };

  const patchFilter = (key) => (value) => {
    setPage(1);
    setFilters((prev) => ({ ...prev, [key]: value || '' }));
  };

  const reset = () => {
    setKeyword('');
    setPage(1);
    setFilters({ q: '', status: '', source_channel: '', station_id: '', intent_level: '' });
  };

  const columns = [
    {
      title: '候选人',
      dataIndex: 'name_masked',
      width: 120,
      render: (value, record) => (
        <Space direction="vertical" size={0}>
          <b>{value || '未填写'}</b>
          <span className="mono muted">{record.id}</span>
        </Space>
      ),
    },
    {
      title: '手机号（默认掩码）',
      dataIndex: 'phone_masked',
      width: 170,
      render: (value) => (
        <Space size={6}>
          <LockOutlined style={{ color: '#8c8c8c' }} />
          <span className="mono">{value || '未填写'}</span>
        </Space>
      ),
    },
    {
      title: '来源渠道',
      dataIndex: 'source_channel',
      width: 120,
      render: (value) => SOURCE_LABEL[value] || value || '-',
    },
    {
      title: '意向站点',
      dataIndex: 'station_name',
      width: 120,
      render: (value) => value || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value) => {
        const meta = statusMeta(value);
        return <Tag color={meta.color}>{meta.text}</Tag>;
      },
    },
    {
      title: '意向度',
      dataIndex: 'intent_level',
      width: 160,
      render: (value) => (
        <Space size={4}>
          <Rate disabled value={value || 0} count={5} style={{ fontSize: 12 }} />
          <span className="muted">{intentText(value)}</span>
        </Space>
      ),
    },
    {
      title: '建档时间',
      dataIndex: 'created_at',
      width: 150,
      render: (value) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" onClick={() => navigate(`/candidates/${record.id}`)}>
          查看详情
        </Button>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <Card size="small">
        <div className="list-head">
          <div>
            <Typography.Title level={5} style={{ margin: 0 }}>
              我的候选人
            </Typography.Title>
            <Typography.Text type="secondary">
              共 {total} 人 · 手机号默认掩码，完整号码需在详情页填写理由后查看，且只显示一次
            </Typography.Text>
          </div>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={load}>
              刷新
            </Button>
          </Space>
        </div>

        <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
          <Col xs={24} md={8} lg={7}>
            <Input.Search
              allowClear
              enterButton="搜索"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={(value) => applyKeyword(value)}
              placeholder="搜索姓名 / 手机号 / 站点"
              onClear={() => applyKeyword('')}
            />
          </Col>
          <Col xs={12} md={4} lg={3}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="状态"
              options={STATUS_LIST}
              value={filters.status || undefined}
              onChange={patchFilter('status')}
            />
          </Col>
          <Col xs={12} md={4} lg={3}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="来源渠道"
              options={sourceOptions}
              value={filters.source_channel || undefined}
              onChange={patchFilter('source_channel')}
            />
          </Col>
          <Col xs={12} md={4} lg={3}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="意向站点"
              options={stationOptions}
              value={filters.station_id || undefined}
              onChange={patchFilter('station_id')}
            />
          </Col>
          <Col xs={12} md={4} lg={3}>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder="意向度"
              options={[
                { value: '5', label: '高（5 星）' },
                { value: '4', label: '较高（4 星）' },
                { value: '3', label: '中（3 星）' },
                { value: '2', label: '低（≤2 星）' },
                { value: '1', label: '低（≤2 星）' },
              ]}
              value={filters.intent_level || undefined}
              onChange={patchFilter('intent_level')}
            />
          </Col>
          <Col xs={24} md={4} lg={2}>
            <Button block onClick={reset}>
              重置
            </Button>
          </Col>
        </Row>
      </Card>

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={rows}
          loading={loading}
          scroll={{ x: 1100 }}
          onRow={(record) => ({
            onClick: () => navigate(`/candidates/${record.id}`),
            style: { cursor: 'pointer' },
          })}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: [8, 10, 20],
            showTotal: (t) => `共 ${t} 条`,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage);
              setPageSize(nextSize);
            },
          }}
        />
      </Card>

      <p className="card-note">
        列表仅展示掩码字段；点击行进入详情可更正 AI 建档字段（需填修改原因并留痕）、查看完整手机号（需填理由并写审计）或执行面试动作。
      </p>
    </div>
  );
}
