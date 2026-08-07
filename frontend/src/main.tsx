import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import { AuthProvider } from './app/AuthContext'
import { RouterProvider } from './app/router'
import './index.css'

const root = document.getElementById('root')
if (!root) throw new Error('#root 요소를 찾을 수 없습니다.')

createRoot(root).render(
  <StrictMode>
    <RouterProvider>
      <AuthProvider>
        <App />
      </AuthProvider>
    </RouterProvider>
  </StrictMode>,
)
