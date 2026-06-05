import React, { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  MessageSquare, LayoutDashboard, Zap, Activity, Bell,
  Database, Search, ListTodo, Settings, ChevronLeft,
  ChevronRight, LogOut, User, Shield, Server
} from 'lucide-react'

interface NavItem {
  path: string
  label: string
  icon: React.ReactNode
  badge?: string
}

const NAV_ITEMS: NavItem[] = [
  { path: '/',           label: 'Chat',        icon: <MessageSquare size={18} /> },
  { path: '/dashboard',  label: 'Dashboard',   icon: <LayoutDashboard size={18} /> },
  { path: '/spark',      label: 'The Spark',   icon: <Zap size={18} /> },
  { path: '/status',     label: 'Status',      icon: <Activity size={18} /> },
  { path: '/notifications', label: 'Alerts',   icon: <Bell size={18} /> },
  { path: '/storage',    label: 'Storage',     icon: <Database size={18} /> },
  { path: '/search',     label: 'Search',      icon: <Search size={18} /> },
  { path: '/queue',      label: 'Queue',       icon: <ListTodo size={18} /> },
  { path: '/admin',      label: 'Admin',       icon: <Shield size={18} /> },
  { path: '/workers',    label: 'Workers',     icon: <Server size={18} /> },
  { path: '/settings',   label: 'Settings',    icon: <Settings size={18} /> },
]

interface NavBarProps {
  username?: string
  onLogout?: () => void
}

export default function NavBar({ username, onLogout }: NavBarProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  return (
    <nav
      className={`flex flex-col h-full bg-gray-900 border-r border-gray-700 transition-all duration-200 ${
        collapsed ? 'w-14' : 'w-52'
      }`}
    >
      {/* Logo */}
      <div className="flex items-center justify-between px-3 py-4 border-b border-gray-700">
        {!collapsed && (
          <span className="text-white font-bold text-sm tracking-widest">TRANC3</span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-gray-400 hover:text-white transition-colors ml-auto"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      {/* Nav items */}
      <div className="flex-1 py-2 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const active = location.pathname === item.path
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm transition-colors ${
                active
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`}
              title={collapsed ? item.label : undefined}
            >
              <span className="flex-shrink-0">{item.icon}</span>
              {!collapsed && <span>{item.label}</span>}
              {!collapsed && item.badge && (
                <span className="ml-auto text-xs bg-red-500 text-white rounded-full px-1.5 py-0.5">
                  {item.badge}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* User footer */}
      {username && (
        <div className="border-t border-gray-700 p-3">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center flex-shrink-0">
              <User size={14} className="text-white" />
            </div>
            {!collapsed && (
              <span className="text-gray-300 text-xs truncate flex-1">{username}</span>
            )}
            {onLogout && (
              <button
                onClick={onLogout}
                className="text-gray-500 hover:text-red-400 transition-colors flex-shrink-0"
                title="Sign out"
              >
                <LogOut size={14} />
              </button>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}
