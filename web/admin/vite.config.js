import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 招聘专员工作台 / 驾驶舱。base 用相对路径，便于静态托管。
export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5174, strictPort: true },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1600,
  },
});
