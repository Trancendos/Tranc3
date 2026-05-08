# src/bio_neural/neuromorphic.py (COMPLETE)

# ============================================================
# FULL SPIKING NEURAL NETWORK
# ============================================================
class SpikingNeuralNetwork(nn.Module):
    """
    Full SNN for neuromorphic processing
    Multi-layer spiking network with STDP learning
    """

    def __init__(self, input_size: int = 768, hidden_sizes: List[int] = [512, 256],
                 output_size: int = 768, timesteps: int = 20):
        super().__init__()
        self.timesteps = timesteps
        
        # Build layers
        sizes = [input_size] + hidden_sizes + [output_size]
        self.layers = nn.ModuleList([
            SpikingLayer(sizes[i], sizes[i+1])
            for i in range(len(sizes) - 1)
        ])
        
        # STDP learning
        self.stdp = STDPLearning()
        
        # Spike rate tracker
        self.spike_rates: List[float] = []
        
        logger.info(f"SNN initialized: {sizes}")

    def forward(self, x: torch.Tensor, use_stdp: bool = False) -> Dict[str, torch.Tensor]:
        """
        Forward pass through SNN over multiple timesteps
        """
        B, T, H = x.shape
        
        # Encode input as spike trains
        spike_trains = self._rate_encode(x)
        
        # Initialize states
        states = [(None, None) for _ in self.layers]
        
        # Accumulate outputs
        all_spikes = []
        layer_spike_rates = []
        
        for t in range(self.timesteps):
            current_input = spike_trains[:, t % T, :]
            
            for i, layer in enumerate(self.layers):
                mem, syn = states[i]
                spikes, new_mem, new_syn = layer(current_input, mem, syn)
                states[i] = (new_mem, new_syn)
                
                # STDP weight update
                if use_stdp and t > 0:
                    layer.weights.data = self.stdp.update_weights(
                        layer.weights.data,
                        current_input.mean(0, keepdim=True),
                        spikes.mean(0, keepdim=True)
                    )
                
                current_input = spikes
            
            all_spikes.append(current_input)
            layer_spike_rates.append(current_input.mean().item())
        
        # Aggregate spike trains
        output_spikes = torch.stack(all_spikes, dim=1)
        avg_output = output_spikes.float().mean(dim=1)
        
        # Track spike rates
        avg_rate = float(np.mean(layer_spike_rates))
        self.spike_rates.append(avg_rate)
        
        return {
            'output': avg_output,
            'spike_trains': output_spikes,
            'spike_rate': avg_rate,
            'energy_estimate': self._estimate_energy(layer_spike_rates)
        }

    def _rate_encode(self, x: torch.Tensor) -> torch.Tensor:
        """Rate encoding: convert continuous values to spike trains"""
        B, T, H = x.shape
        normalized = torch.sigmoid(x)
        spikes = torch.bernoulli(normalized.clamp(0, 1))
        return spikes

    def _estimate_energy(self, spike_rates: List[float]) -> float:
        """Estimate energy consumption (pJ per spike)"""
        energy_per_spike = 0.1  # pJ (neuromorphic hardware estimate)
        total_spikes = sum(spike_rates) * self.timesteps
        return total_spikes * energy_per_spike

    def get_neuromorphic_stats(self) -> Dict:
        """Get neuromorphic processing statistics"""
        return {
            'timesteps': self.timesteps,
            'num_layers': len(self.layers),
            'avg_spike_rate': np.mean(self.spike_rates) if self.spike_rates else 0.0,
            'total_neurons': sum(l.output_size for l in self.layers),
            'stdp_enabled': True,
            'energy_efficient': True
        }

# ============================================================
# NEUROMORPHIC PROCESSOR (Top-level)
# ============================================================
class NeuromorphicProcessor:
    """
    Top-level neuromorphic processing interface
    Bridges classical AI with spiking neural networks
    """

    def __init__(self, config):
        hidden_size = getattr(config, 'hidden_size', 768)
        self.snn = SpikingNeuralNetwork(
            input_size=hidden_size,
            hidden_sizes=[512, 256],
            output_size=hidden_size,
            timesteps=20
        )
        self.enabled = True
        logger.info("NeuromorphicProcessor initialized")

    def process(self, x: torch.Tensor, learn: bool = False) -> Dict:
        """Process input through neuromorphic SNN"""
        if not self.enabled:
            return {'output': x, 'spike_rate': 0.0, 'energy_estimate': 0.0}
        
        try:
            return self.snn(x, use_stdp=learn)
        except Exception as e:
            logger.warning(f"Neuromorphic processing failed: {e}")
            return {'output': x, 'spike_rate': 0.0, 'energy_estimate': 0.0}

    def get_stats(self) -> Dict:
        return self.snn.get_neuromorphic_stats()