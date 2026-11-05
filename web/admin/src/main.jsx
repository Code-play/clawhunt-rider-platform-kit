import ReactDOM from 'react-dom/client';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import 'antd/dist/reset.css';
import './styles.css';
import App from './App.jsx';

dayjs.locale('zh-cn');

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
