from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except (ImportError, RuntimeError, OSError):  # pragma: no cover
    # RuntimeError: CUDA init / driver mismatch; OSError: missing shared lib
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False
else:
    _TORCH_AVAILABLE = True

logger = logging.getLogger(__name__)


@dataclass
class WorldModelConfig:
    """Configuration for the MuZero-style world model."""

    state_dim: int = 256
    hidden_dim: int = 512
    action_dim: int = 64
    num_layers: int = 4
    reward_scale: float = 1.0


class RepresentationNetwork(nn.Module if nn is not None else object):
    """Encodes raw observations into a compact latent state.

    Architecture: linear projection → LayerNorm → ReLU (repeated) → state_dim output.
    The observation dimension is fixed to state_dim * 4 to allow the model to be
    built without knowing the exact sensor/token count at construction time.
    """

    def __init__(self, config: WorldModelConfig) -> None:
        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "RepresentationNetwork requires PyTorch, but it is not available in this runtime."
            )
        super().__init__()
        obs_dim = config.state_dim * 4  # Canonical observable width
        self.config = config

        layers: List[nn.Module] = []
        in_dim = obs_dim
        for _ in range(config.num_layers - 1):
            layers += [
                nn.Linear(in_dim, config.hidden_dim),
                nn.LayerNorm(config.hidden_dim),
                nn.ReLU(inplace=True),
            ]
            in_dim = config.hidden_dim
        layers.append(nn.Linear(in_dim, config.state_dim))
        layers.append(nn.LayerNorm(config.state_dim))

        self.net = nn.Sequential(*layers)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        """Encode observation to latent state.

        Args:
            obs: Tensor of shape (batch, obs_dim).  If obs_dim differs from
                 the expected width it is linearly interpolated to match.

        Returns:
            Latent state tensor of shape (batch, state_dim).
        """
        expected = self.config.state_dim * 4
        if obs.shape[-1] != expected:
            # Pad or truncate on the last dimension to match expected width
            if obs.shape[-1] < expected:
                pad = expected - obs.shape[-1]
                obs = F.pad(obs, (0, pad))
            else:
                obs = obs[..., :expected]
        return self.net(obs)


class DynamicsNetwork(nn.Module if nn is not None else object):
    """Predicts the next latent state and immediate reward given state + action.

    The action is represented as a one-hot (or soft) vector of length action_dim
    and concatenated with the latent state before being fed through the MLP.
    Two separate linear heads decode (next_state, reward).
    """

    def __init__(self, config: WorldModelConfig) -> None:
        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "DynamicsNetwork requires PyTorch, but it is not available in this runtime."
            )
        super().__init__()
        in_dim = config.state_dim + config.action_dim

        trunk_layers: List[nn.Module] = []
        d = in_dim
        for _ in range(config.num_layers - 1):
            trunk_layers += [
                nn.Linear(d, config.hidden_dim),
                nn.LayerNorm(config.hidden_dim),
                nn.ReLU(inplace=True),
            ]
            d = config.hidden_dim

        self.trunk = nn.Sequential(*trunk_layers)
        self.state_head = nn.Linear(config.hidden_dim, config.state_dim)
        self.reward_head = nn.Linear(config.hidden_dim, 1)
        self.state_norm = nn.LayerNorm(config.state_dim)
        self.config = config

    def forward(
        self,
        state: torch.Tensor,
        action_vec: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Predict next state and reward.

        Args:
            state:      Latent state (batch, state_dim).
            action_vec: Action encoding (batch, action_dim).

        Returns:
            (next_state, reward) each of shape (batch, state_dim) and (batch, 1).
        """
        x = torch.cat([state, action_vec], dim=-1)
        h = self.trunk(x)
        next_state = self.state_norm(self.state_head(h))
        reward = self.reward_head(h)
        return next_state, reward


class PredictionNetwork(nn.Module if nn is not None else object):
    """Policy and value heads operating on the latent state.

    Returns raw logits over the action vocabulary (to be softmax-ed externally)
    and a scalar value estimate.
    """

    def __init__(self, config: WorldModelConfig) -> None:
        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "PredictionNetwork requires PyTorch, but it is not available in this runtime."
            )
        super().__init__()
        self.config = config

        trunk_layers: List[nn.Module] = []
        d = config.state_dim
        for _ in range(max(config.num_layers - 2, 1)):
            trunk_layers += [
                nn.Linear(d, config.hidden_dim),
                nn.LayerNorm(config.hidden_dim),
                nn.ReLU(inplace=True),
            ]
            d = config.hidden_dim

        self.trunk = nn.Sequential(*trunk_layers)
        self.policy_head = nn.Linear(config.hidden_dim, config.action_dim)
        self.value_head = nn.Linear(config.hidden_dim, 1)

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Compute policy logits and value.

        Args:
            state: Latent state (batch, state_dim).

        Returns:
            (policy_logits, value) of shapes (batch, action_dim) and (batch, 1).
        """
        h = self.trunk(state)
        policy_logits = self.policy_head(h)
        value = torch.tanh(self.value_head(h))
        return policy_logits, value


class MuZeroWorldModel(nn.Module if nn is not None else object):
    """MuZero-style world model combining representation, dynamics, and prediction.

    This implements the three core MuZero functions:
      h: observation → latent state          (RepresentationNetwork)
      g: (state, action) → (state', reward)  (DynamicsNetwork)
      f: state → (policy, value)             (PredictionNetwork)

    Planning is performed by unrolling g for ``horizon`` steps, collecting
    predicted rewards, policies, and values at each step.
    """

    def __init__(self, config: WorldModelConfig) -> None:
        if not _TORCH_AVAILABLE:
            raise RuntimeError(
                "MuZeroWorldModel requires PyTorch, but it is not available in this runtime."
            )
        super().__init__()
        self.config = config
        self.representation = RepresentationNetwork(config)
        self.dynamics = DynamicsNetwork(config)
        self.prediction = PredictionNetwork(config)

    def represent(self, obs: torch.Tensor) -> torch.Tensor:
        """Map raw observation to latent state h(o).

        Args:
            obs: Raw observation tensor (batch, obs_dim).

        Returns:
            Latent state (batch, state_dim).
        """
        return self.representation(obs)

    def step(
        self,
        state: torch.Tensor,
        action_idx: int,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """One model step: (state, action) → (next_state, reward, policy_logits, value).

        Args:
            state:      Current latent state (batch, state_dim).
            action_idx: Integer index of the chosen action.

        Returns:
            Tuple of (next_state, reward, policy_logits, value).
        """
        batch = state.shape[0]
        action_vec = torch.zeros(batch, self.config.action_dim, device=state.device)
        action_idx = int(action_idx) % self.config.action_dim
        action_vec[:, action_idx] = 1.0

        next_state, reward = self.dynamics(state, action_vec)
        policy_logits, value = self.prediction(next_state)
        return next_state, reward, policy_logits, value

    def plan(self, initial_obs: torch.Tensor, horizon: int = 5) -> List[Dict]:
        """Unroll the world model for planning without gradient accumulation.

        For each step the greedy action (highest policy logit) is chosen and
        the model is advanced one step.  Returns a trajectory of observations.

        Args:
            initial_obs: Raw observation (1, obs_dim) or (batch, obs_dim).
            horizon:     Number of model steps to look ahead.

        Returns:
            List of dicts, one per step, containing:
                step, state, reward, policy, value, action_idx.
        """
        self.eval()
        trajectory: List[Dict] = []

        with torch.no_grad():
            state = self.represent(initial_obs)

            for t in range(horizon):
                policy_logits, value = self.prediction(state)
                action_idx = int(policy_logits.argmax(dim=-1)[0].item())

                next_state, reward, next_policy_logits, next_value = self.step(state, action_idx)

                step_info = {
                    "step": t,
                    "state": state.detach().cpu(),
                    "reward": float(reward[0, 0].item()) * self.config.reward_scale,
                    "policy": F.softmax(policy_logits[0], dim=-1).cpu().tolist(),
                    "value": float(value[0, 0].item()),
                    "action_idx": action_idx,
                }
                trajectory.append(step_info)
                state = next_state

        return trajectory

    def compute_loss(self, batch: Dict) -> Dict[str, torch.Tensor]:
        """Compute MuZero training losses over an unrolled trajectory.

        Expected keys in ``batch``:
          - "observations":    (B, obs_dim)
          - "actions":         (B, K) integer action indices for K unroll steps
          - "target_rewards":  (B, K)
          - "target_values":   (B, K)
          - "target_policies": (B, K, action_dim)

        Returns:
            Dict with scalar tensors: "reward_loss", "value_loss",
            "policy_loss", "consistency_loss", "total_loss".
        """
        observations: torch.Tensor = batch["observations"]
        actions: torch.Tensor = batch["actions"]  # (B, K)
        target_rewards: torch.Tensor = batch["target_rewards"]  # (B, K)
        target_values: torch.Tensor = batch["target_values"]  # (B, K)
        target_policies: torch.Tensor = batch["target_policies"]  # (B, K, action_dim)

        B, K = actions.shape
        device = observations.device

        # Encode initial observation
        state = self.represent(observations)

        reward_losses: List[torch.Tensor] = []
        value_losses: List[torch.Tensor] = []
        policy_losses: List[torch.Tensor] = []
        consistency_losses: List[torch.Tensor] = []
        prev_state = state

        for k in range(K):
            action_idx_k = actions[:, k]  # (B,)
            # Construct action vectors for the whole batch
            action_vec = torch.zeros(B, self.config.action_dim, device=device)
            for b in range(B):
                idx = int(action_idx_k[b].item()) % self.config.action_dim
                action_vec[b, idx] = 1.0

            next_state, reward = self.dynamics(state, action_vec)
            policy_logits, value = self.prediction(state)

            # Reward loss: MSE between predicted and target reward
            reward_loss = F.mse_loss(reward.squeeze(-1), target_rewards[:, k])

            # Value loss: MSE between predicted and target value
            value_loss = F.mse_loss(value.squeeze(-1), target_values[:, k])

            # Policy loss: cross-entropy against target policy distribution
            log_probs = F.log_softmax(policy_logits, dim=-1)
            target_pol = target_policies[:, k, :]
            policy_loss = -(target_pol * log_probs).sum(dim=-1).mean()

            # Consistency loss: next state should be consistent across steps
            if k > 0:
                consistency_loss = F.mse_loss(state, prev_state.detach())
                consistency_losses.append(consistency_loss)

            reward_losses.append(reward_loss)
            value_losses.append(value_loss)
            policy_losses.append(policy_loss)
            prev_state = next_state
            state = next_state

        reward_loss_total = torch.stack(reward_losses).mean()
        value_loss_total = torch.stack(value_losses).mean()
        policy_loss_total = torch.stack(policy_losses).mean()
        consistency_loss_total = (
            torch.stack(consistency_losses).mean()
            if consistency_losses
            else torch.tensor(0.0, device=device)
        )

        total_loss = (
            reward_loss_total + value_loss_total + policy_loss_total + 0.5 * consistency_loss_total
        )

        return {
            "reward_loss": reward_loss_total,
            "value_loss": value_loss_total,
            "policy_loss": policy_loss_total,
            "consistency_loss": consistency_loss_total,
            "total_loss": total_loss,
        }
