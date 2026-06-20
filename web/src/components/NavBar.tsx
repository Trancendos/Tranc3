import React, { useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import {
  MessageSquare, LayoutDashboard, Zap, Activity, Bell,
  Database, Search, ListTodo, Settings, ChevronLeft,
  ChevronRight, LogOut, User, Shield, Server, GitBranch,
  CheckSquare, Cpu, Bot, Globe, FlaskConical, BarChart3, Network
} from 'lucide-react'

interface NavItem {
  path: string
  label: string
  icon: React.ReactNode
  badge?: string
  group?: string
}

const NAV_ITEMS: NavItem[] = [
  // Core
  { path: '/',               label: 'Chat',          icon: <MessageSquare size={18} aria-hidden="true" />, group: 'core' },
  { path: '/dashboard',     label: 'Dashboard',     icon: <LayoutDashboard size={18} aria-hidden="true" />, group: 'core' },
  { path: '/spark',         label: 'The Spark',     icon: <Zap size={18} aria-hidden="true" />, group: 'core' },
  // Platform
  { path: '/grid',          label: 'Digital Grid',  icon: <GitBranch size={18} aria-hidden="true" />, group: 'platform' },
  { path: '/ai-providers',  label: 'AI Providers',  icon: <Bot size={18} aria-hidden="true" />, group: 'platform' },
  { path: '/workers',       label: 'Workers',       icon: <Cpu size={18} aria-hidden="true" />, group: 'platform' },
  { path: '/services',      label: 'Services',      icon: <Globe size={18} aria-hidden="true" />, group: 'platform' },
  // Ops
  { path: '/status',        label: 'Status',        icon: <Activity size={18} aria-hidden="true" />, group: 'ops' },
  { path: '/notifications', label: 'Alerts',        icon: <Bell size={18} aria-hidden="true" />, group: 'ops' },
  { path: '/queue',         label: 'Queue',         icon: <ListTodo size={18} aria-hidden="true" />, group: 'ops' },
  { path: '/compliance',    label: 'Compliance',    icon: <CheckSquare size={18} aria-hidden="true" />, group: 'ops' },
  { path: '/audit',         label: 'Audit Log',     icon: <Shield size={18} aria-hidden="true" />, group: 'ops' },
  // Data
  { path: '/storage',       label: 'Storage',       icon: <Database size={18} aria-hidden="true" />, group: 'data' },
  { path: '/search',        label: 'Search',        icon: <Search size={18} aria-hidden="true" />, group: 'data' },
  { path: '/the-lab',       label: 'The Lab',       icon: <FlaskConical size={18} aria-hidden="true" />, group: 'data' },
  { path: '/the-dutchy',   label: 'The Dutchy',    icon: <BarChart3 size={18} aria-hidden="true" />, group: 'data' },
  // AI
  { path: '/turings-hub',  label: "Turing's Hub",  icon: <Cpu size={18} aria-hidden="true" />, group: 'ai' },
  { path: '/deep-agents',  label: 'Deep Agents',   icon: <Network size={18} aria-hidden="true" />, group: 'ai' },
  // Config
  { path: '/admin',         label: 'Admin',         icon: <Shield size={18} aria-hidden="true" />, group: 'config' },
  { path: '/settings',      label: 'Settings',      icon: <Settings size={18} aria-hidden="true" />, group: 'config' },
]

const GROUP_LABELS: Record<string, string> = {
  core: 'Core',
  platform: 'Platform',
  ops: 'Operations',
  data: 'Data',
  ai: 'AI Entities',
  config: 'Config',
}

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
      <ul id="sidebar-nav-list" role="list" className="flex-1 py-2 overflow-y-auto px-1">
        {(() => {
          let lastGroup = ''
          return NAV_ITEMS.map((item) => {
            const active = location.pathname === item.path
            const showGroupHeader = !collapsed && item.group && item.group !== lastGroup
            if (item.group) lastGroup = item.group
            return (
              <React.Fragment key={item.path}>
                {showGroupHeader && (
                  <li aria-hidden="true">
                    <p className="px-2 pt-3 pb-1 text-xs font-semibold uppercase tracking-widest text-gray-600 select-none">
                      {GROUP_LABELS[item.group!] ?? item.group}
                    </p>
                  </li>
                )}
                <li>
                  <button
                    onClick={() => navigate(item.path)}
                    aria-current={active ? 'page' : undefined}
                    aria-label={collapsed ? item.label : undefined}
                    title={collapsed ? item.label : undefined}
                    className={`w-full flex items-center gap-3 px-2 py-2 text-sm rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                      active
                        ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-900/50'
                        : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                    }`}
                  >
                    <span className="flex-shrink-0" aria-hidden="true">{item.icon}</span>
                    {!collapsed && <span className="truncate">{item.label}</span>}
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
              </React.Fragment>
            )
          })
        })()}
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
