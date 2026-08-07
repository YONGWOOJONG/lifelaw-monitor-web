import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 개발 서버는 /api 를 백엔드로 프록시한다.
//
// 설계 §17.4 강제 조항 1 은 **동일 출처 배포**를 요구한다. 프록시를 쓰면
// 브라우저 입장에서 프론트와 API 가 같은 오리진이므로 CORS 가 필요 없고,
// 세션 쿠키가 그대로 전달된다. 운영에서는 리버스 프록시가 같은 역할을 한다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
})
