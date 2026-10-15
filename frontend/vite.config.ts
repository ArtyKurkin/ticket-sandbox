import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  build: {
    outDir: '../static/frontend',
    emptyOutDir: true,
    manifest: 'manifest.json',
    rollupOptions: { input: { readiness: 'src/main.tsx', achievements: 'src/achievements/main.tsx', roadmap: 'src/roadmap/main.tsx', notifications: 'src/notifications/main.tsx' } },
  },
});
