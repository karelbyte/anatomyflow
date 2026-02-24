import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 4000,
          style: {
            background: '#27272a',
            color: '#e4e4e7',
            border: '1px solid #52525b',
          },
          success: { iconTheme: { primary: '#22c55e', secondary: '#e4e4e7' } },
          error: { iconTheme: { primary: '#ef4444', secondary: '#e4e4e7' } },
          loading: { iconTheme: { primary: '#3b82f6', secondary: '#e4e4e7' } },
        }}
      />
    </BrowserRouter>
  </React.StrictMode>,
)
