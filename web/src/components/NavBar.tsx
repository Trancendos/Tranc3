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
  { path: '/',              label: 'Chat',         icon: <MessageSquare size={18} aria-hidden="true" /> },
  { path: '/dashboard',    label: 'Dashboard',    icon: <LayoutDashboard size={18} aria-hidden="true" /> },
  { path: '/spark',        label: 'The Spark',    icon: <Zap size={18} aria-hidden="true" /> },
  { path: '/status',       label: 'Status',       icon: <Activity size={18} aria-hidden="true" /> },
  { path: '/notifications',label: 'Alerts',       icon: <Bell size={18} aria-hidden="true" /> },
  { path: '/storage',      label: 'Storage',      icon: <Database size={18} aria-hidden="true" /> },
  { path: '/search',       label: 'Search',       icon: <Search size={18} aria-hidden="true" /> },
  { path: '/queue',        label: 'Queue',        icon: <ListTodo size={18} aria-hidden="true" /> },
  { path: '/admin',        label: 'Admin',        icon: <Shield size={18} aria-hidden="true" /> },
  { path: '/workers',      label: 'Workers',      icon: <Server size={18} aria-hidden="true" /> },
  { path: '/settings',     label: 'Settings',     icon: <Settings size={18} aria-hidden="true" /> },
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
      aria-label="Main navigation"
      className={`flex flex-col h-full bg-gray-900 border-r border-gray-700 transition-all duration-200 ${
        collapsed ? 'w-14' : 'w-52'
      }`}
    >
      {/* Logo / collapse toggle */}
      <div className="flex items-center justify-between px-3 py-4 border-b border-gray-700">
        {!collapsed && (
          <span className="text-white font-bold text-sm tracking-widest select-none" aria-hidden="true">
            TRANC3
          </span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          aria-expanded={!collapsed}
          aria-controls="sidebar-nav-list"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="text-gray-400 hover:text-white transition-colors ml-auto rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 focus-visible:ring-offset-gray-900 p-0.5"
        >
          {collapsed
            ? <ChevronRight size={16} aria-hidden="true" />
            : <ChevronLeft  size={16} aria-hidden="true" />}
        </button>
      </div>

      {/* Nav items */}
      <ul id="sidebar-nav-list" role="list" className="flex-1 py-2 overflow-y-auto space-y-0.5 px-1">
        {NAV_ITEMS.map((item) => {
          const active = location.pathname === item.path
          return (
            <li key={item.path}>
              <button
                onClick={() => navigate(item.path)}
                aria-current={active ? 'page' : undefined}
                aria-label={collapsed ? item.label : undefined}
                title={collapsed ? item.label : undefined}
                className={`w-full flex items-center gap-3 px-2 py-2.5 text-sm rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                  active
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                }`}
              >
                <span className="flex-shrink-0" aria-hidden="true">{item.icon}</span>
                {!collapsed && <span>{item.label}</span>}
                {!collapsed && item.badge && (
                  <span
                    aria-label={`${item.badge} unread`}
                    className="ml-auto text-xs bg-red-500 text-white rounded-full px-1.5 py-0.5 tabular-nums"
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            </li>
          )
        })}
      </ul>

      {/* User footer */}
      {username && (
        <div className="border-t border-gray-700 p-2">
          <div className="flex items-center gap-2 px-1">
            <div
              className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center flex-shrink-0"
              aria-hidden="true"
            >
              <User size={14} className="text-white" aria-hidden="true" />
            </div>
            {!collapsed && (
              <span className="text-gray-300 text-xs truncate flex-1" title={username}>
                {username}
              </span>
            )}
            {onLogout && (
              <button
                onClick={onLogout}
                aria-label="Sign out"
                title="Sign out"
                className="text-gray-500 hover:text-red-400 transition-colors flex-shrink-0 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 p-0.5"
              >
                <LogOut size={14} aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}
