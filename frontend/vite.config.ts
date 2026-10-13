import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  build: {
    outDir: '../static/frontend',
    emptyOutDir: true,
    manifest: 'manifest.json',
    rollupOptions: { input: 'src/main.tsx' },
  },
});
