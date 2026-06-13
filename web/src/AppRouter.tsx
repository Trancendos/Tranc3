import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ChatView from './ChatView'
import TrancendosDashboard from './trancendos/Dashboard'

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatView />} />
        <Route path="/dashboard" element={<TrancendosDashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
