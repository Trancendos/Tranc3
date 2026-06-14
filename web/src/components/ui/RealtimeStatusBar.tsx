import React, { useEffect, useState } from 'react'
import { useWebSocket } from '../../hooks/useWebSocket'

const WS_URL = 'ws://localhost:8004'

interface HeartbeatMessage {
  type?: string
  active_agents?: number
  timestamp?: string
}

function isHeartbeat(msg: unknown): msg is HeartbeatMessage {
  return typeof msg === 'object' && msg !== null
}

export default function RealtimeStatusBar() {
  const { connected, lastMessage, error } = useWebSocket(WS_URL)
  const [lastHeartbeat, setLastHeartbeat] = useState<Date | null>(null)
  const [activeAgents, setActiveAgents] = useState<number | null>(null)

  useEffect(() => {
    if (!isHeartbeat(lastMessage)) return
    setLastHeartbeat(new Date())
    if (typeof lastMessage.active_agents === 'number') {
      setActiveAgents(lastMessage.active_agents)
    }
  }, [lastMessage])

  const dotColor = error
    ? 'bg-red-500'
    : connected
    ? 'bg-green-500'
    : 'bg-yellow-500'

  const statusLabel = error ? 'Error' : connected ? 'Connected' : 'Reconnecting…'

  const heartbeatText = lastHeartbeat
    ? lastHeartbeat.toLocaleTimeString()
    : '—'

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 hidden md:flex items-center gap-4 px-4 py-1.5 bg-gray-950 border-t border-gray-800 text-xs text-gray-500 select-none">
      {/* WS status */}
      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${dotColor} ${connected ? 'animate-pulse' : ''}`} />
        <span className="text-gray-400">{statusLabel}</span>
      </div>

      <span className="text-gray-700">|</span>

      {/* Last heartbeat */}
      <div className="flex items-center gap-1">
        <span>Heartbeat:</span>
        <span className="text-gray-400">{heartbeatText}</span>
      </div>

      {activeAgents !== null && (
        <>
          <span className="text-gray-700">|</span>
          <div className="flex items-center gap-1">
            <span>Agents:</span>
            <span className="text-cyan-400 font-medium">{activeAgents}</span>
          </div>
        </>
      )}

      <span className="ml-auto text-gray-700 font-mono">The Nexus · ws://localhost:8004</span>
    </div>
  )
}
