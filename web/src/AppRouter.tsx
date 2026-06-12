import React, { useState, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ChatView from './ChatView'
import TrancendosDashboard from './trancendos/Dashboard'
import ComplianceDashboard from './pages/ComplianceDashboard'
import UxShowcasePage from './pages/UxShowcasePage'

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatView />} />
        <Route path="/dashboard" element={<TrancendosDashboard />} />
        <Route path="/compliance" element={<ComplianceDashboard />} />
        <Route path="/ux-showcase" element={<UxShowcasePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
