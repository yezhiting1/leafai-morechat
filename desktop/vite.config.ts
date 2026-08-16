import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// '@product' resolves to the built-in default (empty). An alternate build
// can set COW_PRODUCT_DIR to point at another module instead.
const productDir =
  process.env.COW_PRODUCT_DIR || path.resolve(__dirname, 'src/renderer/src/product/default')

// When '@product' points outside this project, its files can't resolve shared
// deps from their own tree. Alias the shared runtime deps to this project's
// node_modules so an out-of-tree product module imports the same instances.
const nodeModules = path.resolve(__dirname, 'node_modules')
const sharedDepAliases = process.env.COW_PRODUCT_DIR
  ? {
      react: path.join(nodeModules, 'react'),
      'react-dom': path.join(nodeModules, 'react-dom'),
      'react/jsx-runtime': path.join(nodeModules, 'react/jsx-runtime'),
      'react-router-dom': path.join(nodeModules, 'react-router-dom'),
      'lucide-react': path.join(nodeModules, 'lucide-react'),
    }
  : {}

export default defineConfig({
  plugins: [react()],
  root: path.resolve(__dirname, 'src/renderer'),
  base: './',
  publicDir: path.resolve(__dirname, '../channel/web/static'),
  build: {
    outDir: path.resolve(__dirname, 'dist/renderer'),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src/renderer/src'),
      '@product': productDir,
      ...sharedDepAliases,
    },
  },
})
