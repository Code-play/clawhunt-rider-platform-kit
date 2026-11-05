import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// H5 求职者端。base 用相对路径，便于任意静态目录下直接打开。
export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  build: { outDir: 'dist', sourcemap: false },
});
