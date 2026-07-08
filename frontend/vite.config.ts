import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const proxyTarget = process.env.VITE_BACKEND_TARGET || `http://127.0.0.1:${process.env.VITE_BACKEND_PORT || '8100'}`

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/login': {
        target: proxyTarget,
        changeOrigin: true,
        bypass: (req) => {
          if (req.method === 'GET') {
            return '/index.html'
          }
        },
      },
      '/verify': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/cookies': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/delivery-rules': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/system-settings': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/logs': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/users': {
        target: proxyTarget,
        changeOrigin: true,
      },
      // 管理员API - 前端有 /admin/* 路由，需要区分浏览器访问和 API 请求
      '/admin': {
        target: proxyTarget,
        changeOrigin: true,
        bypass: (req) => {
          // 浏览器直接访问（Accept 包含 text/html）时，让前端路由处理
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '/risk-control-logs': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/qrcode': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/generate-captcha': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/verify-captcha': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/send-verification-code': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/registration-status': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/login-info-status': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/geetest': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/register': {
        target: proxyTarget,
        changeOrigin: true,
        bypass: (req) => {
          // 浏览器直接访问时返回前端页面，只有 POST 请求才代理到后端
          if (req.method === 'GET' && req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '/itemReplays': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/item-reply': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/default-replies': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/ai-reply-settings': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/ai-reply-test': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/password-login': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/qr-login': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/keywords-export': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/keywords-import': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/upload-image': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/default-reply': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/static': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/backup': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/project-stats': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/change-password': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/change-admin-password': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/check-default-password': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/logout': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/user-settings': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/search': {
        target: proxyTarget,
        changeOrigin: true,
      },
      // 商品管理 - 前端有 /items 路由，需要区分浏览器访问和 API 请求
      '/items': {
        target: proxyTarget,
        changeOrigin: true,
        bypass: (req) => {
          // 只有浏览器直接访问 /items 路径时才返回前端页面
          // API 请求通常是 /items/xxx 或带有 application/json
          const isApiRequest = req.url !== '/items' ||
            req.headers.accept?.includes('application/json') ||
            req.headers['content-type']?.includes('application/json')
          if (!isApiRequest && req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 卡券管理 - 前端有 /cards 路由
      '/cards': {
        target: proxyTarget,
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 通知渠道 - 前端有 /notification-channels 路由
      '/notification-channels': {
        target: proxyTarget,
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 消息通知 - 前端有 /message-notifications 路由
      '/message-notifications': {
        target: proxyTarget,
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 关键词 - 前端有 /keywords 路由
      '/keywords': {
        target: proxyTarget,
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers.accept?.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      // 订单 API - 后端路径是 /api/orders
      '/api/orders': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    // 资源放在 assets 目录，通过 base 配置让引用路径为 /static/assets/
    assetsDir: 'assets',
  },
  // 只在生产构建时使用 /static/ 作为 base，开发模式使用 /
  base: command === 'build' ? '/static/' : '/',
}))
