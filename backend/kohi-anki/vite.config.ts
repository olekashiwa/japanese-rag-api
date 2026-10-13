import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base: './' — сборка работает и с локального файла, и из подпапки проекта.
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    open: false,
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
});
