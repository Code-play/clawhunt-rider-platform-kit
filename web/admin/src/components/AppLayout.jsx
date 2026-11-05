import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { App, Avatar, Dropdown, Layout, Menu, Space, Tag, Typography } from 'antd';
import {
  ApiOutlined,
  CalendarOutlined,
  DashboardOutlined,
  EnvironmentOutlined,
  LogoutOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useAuth } from '../state/AuthContext.jsx';
import Watermark from './Watermark.jsx';
import { API_MODE } from '../api/client.js';

const { Header, Sider, Content } = Layout;

const MENU_ITEMS = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '指标看板' },
  { key: '/candidates', icon: <TeamOutlined />, label: '我的候选人' },
  { key: '/schedule', icon: <CalendarOutlined />, label: '面试日程' },
  { key: '/stations', icon: <EnvironmentOutlined />, label: '站点与名额' },
];

const TITLES = {
  '/dashboard': '指标看板（驾驶舱示意）',
  '/candidates': '我的候选人',
  '/schedule': '面试日程',
  '/stations': '站点与名额管理',
};

export default function AppLayout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { modal } = App.useApp();

  const selected = useMemo(() => {
    if (location.pathname.startsWith('/candidates')) return '/candidates';
    return location.pathname;
  }, [location.pathname]);

  const title = location.pathname.startsWith('/candidates/')
    ? '候选人详情'
    : TITLES[selected] || '骑手招聘工作台';

  const menu = {
    items: [
      {
        key: 'profile',
        label: (
          <div className="user-card">
            <div className="user-name">{user ? user.name : '未登录'}</div>
            <div className="user-meta">
              工号 {user ? user.employee_no : '-'} · {user ? user.role : ''}
            </div>
          </div>
        ),
        disabled: true,
      },
      { type: 'divider' },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
    ],
    onClick: ({ key }) => {
      if (key === 'logout') {
        modal.confirm({
          title: '确认退出登录？',
          content: '退出后需要重新登录才能访问候选人信息。',
          okText: '退出',
          cancelText: '取消',
          onOk: logout,
        });
      }
    },
  };

  return (
    <Layout className="admin-layout">
      <Sider width={228} className="admin-sider" breakpoint="lg" collapsedWidth={0}>
        <div className="sider-brand">
          <span className="sider-logo">骑</span>
          <div>
            <div className="sider-title">骑手招聘工作台</div>
            <div className="sider-sub">招聘专员端 · 骨架演示</div>
          </div>
        </div>
        <Menu
          mode="inline"
          theme="dark"
          selectedKeys={[selected]}
          items={MENU_ITEMS}
          onClick={({ key }) => navigate(key)}
        />
        <div className="sider-foot">
          <ApiOutlined /> {API_MODE === 'mock' ? '内置 mock 模式' : '真后端模式'}
        </div>
      </Sider>

      <Layout>
        <Header className="admin-header">
          <Typography.Title level={4} className="header-title">
            {title}
          </Typography.Title>
          <Space size="middle">
            {API_MODE === 'mock' ? <Tag color="blue">MOCK 数据</Tag> : <Tag color="green">API 模式</Tag>}
            <Tag color="orange">手机号默认掩码</Tag>
            <Dropdown menu={menu} trigger={['click']} placement="bottomRight">
              <Space className="header-user" size={8}>
                <Avatar size={30} icon={<UserOutlined />} style={{ background: '#1677ff' }} />
                <span className="header-user-name">{user ? user.name : ''}</span>
                <span className="header-user-no">{user ? user.employee_no : ''}</span>
              </Space>
            </Dropdown>
          </Space>
        </Header>

        <Content className="admin-content">{children}</Content>
      </Layout>

      <Watermark user={user} />
    </Layout>
  );
}
