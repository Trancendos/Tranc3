import React, { useId } from 'react'
import { useFocusTrap } from './hooks/useFocusTrap'
import { X, CheckCircle } from 'lucide-react'

interface Props {
  onClose: () => void
  onUpgrade: (tier: string) => void
}

const TIERS = [
  {
    id: 'pro',
    name: 'Pro',
    price: '£29/mo',
    limit: '1,000 req/hr',
    features: [
      'All personalities',
      'All languages',
      'Quantum attention',
      'Consciousness Φ score',
      'WebSocket streaming',
    ],
  },
  {
    id: 'business',
    name: 'Business',
    price: '£149/mo',
    limit: '10,000 req/hr',
    features: [
      'Everything in Pro',
      'White-label',
      'Priority support',
      'Custom personality profiles',
      'Usage analytics dashboard',
    ],
  },
]

export default function UpgradeModal({ onClose, onUpgrade }: Props) {
  const titleId = useId()
  const descId  = useId()
  const containerRef = useFocusTrap(true, onClose)

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      aria-hidden="false"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      {/* Dialog */}
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="bg-gray-900 rounded-2xl p-6 max-w-lg w-full border border-gray-700 shadow-2xl"
      >
        {/* Header */}
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 id={titleId} className="text-xl font-bold text-white">
              Rate limit reached
            </h2>
            <p id={descId} className="text-gray-400 text-sm mt-1">
              Upgrade your plan to continue chatting
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close upgrade modal"
            className="text-gray-500 hover:text-white transition-colors rounded-lg p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {/* Tier cards */}
        <div className="grid grid-cols-2 gap-4 mb-4" role="list" aria-label="Upgrade plans">
          {TIERS.map((tier) => (
            <article
              key={tier.id}
              role="listitem"
              aria-label={`${tier.name} plan — ${tier.price}`}
              className="bg-gray-800 rounded-xl p-4 border border-gray-700 hover:border-blue-500 focus-within:border-blue-500 transition-colors flex flex-col"
            >
              <div className="text-white font-bold">{tier.name}</div>
              <div className="text-blue-400 text-lg font-bold mt-1">{tier.price}</div>
              <div className="text-gray-400 text-xs mt-1">{tier.limit}</div>

              <ul aria-label={`${tier.name} features`} className="mt-3 space-y-1 flex-1">
                {tier.features.map((f) => (
                  <li key={f} className="text-gray-300 text-xs flex items-center gap-1.5">
                    <CheckCircle size={11} className="text-green-400 flex-shrink-0" aria-hidden="true" />
                    {f}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => onUpgrade(tier.id)}
                className="w-full mt-4 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-800"
              >
                Upgrade to {tier.name}
              </button>
            </article>
          ))}
        </div>

        <p className="text-center text-gray-600 text-xs">
          Secure payment via Stripe · Cancel anytime
        </p>
      </div>
    </div>
  )
}
