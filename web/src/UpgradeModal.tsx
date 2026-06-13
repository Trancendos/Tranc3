import React from 'react'

interface Props {
    onClose: () => void
    onUpgrade: (tier: string) => void
}

const TIERS = [
    { id: 'pro', name: 'Pro', price: '£29/mo', limit: '1,000 req/hr', features: ['All personalities', 'All languages', 'Quantum attention', 'Consciousness Φ score', 'WebSocket streaming'] },
    { id: 'business', name: 'Business', price: '£149/mo', limit: '10,000 req/hr', features: ['Everything in Pro', 'White-label', 'Priority support', 'Custom personality profiles', 'Usage analytics dashboard'] },
]

export default function UpgradeModal({ onClose, onUpgrade }: Props) {
    return (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
            <div className="bg-gray-900 rounded-2xl p-6 max-w-lg w-full border border-gray-700 shadow-2xl">
                <div className="flex justify-between items-start mb-4">
                    <div>
                        <h2 className="text-xl font-bold text-white">Rate limit reached</h2>
                        <p className="text-gray-400 text-sm mt-1">Upgrade to continue chatting</p>
                    </div>
                    <button aria-label="Close" onClick={onClose} className="text-gray-500 hover:text-white text-xl">✕</button>
                </div>

                <div className="grid grid-cols-2 gap-4 mb-4">
                    {TIERS.map(tier => (
                        <div key={tier.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700 hover:border-blue-500 transition-colors">
                            <div className="text-white font-bold">{tier.name}</div>
                            <div className="text-blue-400 text-lg font-bold mt-1">{tier.price}</div>
                            <div className="text-gray-400 text-xs mt-1">{tier.limit}</div>
                            <ul className="mt-3 space-y-1">
                                {tier.features.map(f => (
                                    <li key={f} className="text-gray-300 text-xs flex items-center gap-1">
                                        <span className="text-green-400">✓</span> {f}
                                    </li>
                                ))}
                            </ul>
                            <button onClick={() => onUpgrade(tier.id)}
                                className="w-full mt-4 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 rounded-lg transition-colors">
                                Upgrade to {tier.name}
                            </button>
                        </div>
                    ))}
                </div>

                <p className="text-center text-gray-600 text-xs">
                    Secure payment via Stripe · Cancel anytime
                </p>
            </div>
        </div>
    )
}
