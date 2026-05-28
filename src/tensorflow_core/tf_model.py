import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# TensorFlow is imported lazily inside each method via _get_tf() so the module
# loads cleanly even when TF is not installed.


def TFAvailable() -> bool:
    """Return True if TensorFlow can be imported in this environment."""
    try:
        return True
    except ImportError:
        return False
    except Exception:
        return False


def _get_tf() -> Any:
    """Lazily import and return the tensorflow module.

    Raises:
        ImportError: If TensorFlow is not installed.
    """
    try:
        import tensorflow as tf

        return tf
    except ImportError as exc:
        raise ImportError(
            "TensorFlow is not installed.  Install it with: pip install tensorflow"
        ) from exc


@dataclass
class TFModelConfig:
    """Configuration shared across all TensorFlow model classes."""

    name: str = "tf_model"
    hidden_dims: List[int] = field(default_factory=lambda: [512, 256, 128])
    output_dim: int = 64
    dropout_rate: float = 0.1
    learning_rate: float = 1e-4
    use_batch_norm: bool = True


class TFSequenceClassifier:
    """Sequence classification model built on Keras (Embedding → LSTM → Dense).

    TensorFlow/Keras is imported lazily so the class is safe to instantiate
    in environments without TF as long as ``build_model`` / ``predict`` are
    not called.

    Attributes:
        config:     Model configuration.
        vocab_size: Vocabulary size for the embedding layer.
        embed_dim:  Embedding vector dimensionality.
        model:      Compiled Keras model (None until ``build_model`` is called).
        optimizer:  Keras optimizer instance.
    """

    def __init__(
        self,
        config: TFModelConfig,
        vocab_size: int = 30000,
        embed_dim: int = 128,
    ) -> None:
        self.config = config
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        self.model: Optional[Any] = None
        self._optimizer: Optional[Any] = None
        self._loss_fn: Optional[Any] = None

    def build_model(self) -> Any:
        """Lazily import TF and construct the Keras model.

        Architecture:
          Embedding(vocab_size, embed_dim)
          → Bidirectional LSTM(hidden_dims[0], return_sequences=True)
          → LSTM(hidden_dims[1])
          → [BatchNorm → Dropout → Dense] × len(hidden_dims[2:])
          → Dense(output_dim, softmax)

        Returns:
            The compiled keras.Model instance.
        """
        tf = _get_tf()

        inputs = tf.keras.Input(shape=(None,), dtype="int32", name="input_ids")

        # Embedding
        x = tf.keras.layers.Embedding(
            input_dim=self.vocab_size,
            output_dim=self.embed_dim,
            mask_zero=True,
            name="embedding",
        )(inputs)

        # Bidirectional LSTM
        x = tf.keras.layers.Bidirectional(
            tf.keras.layers.LSTM(
                self.config.hidden_dims[0],
                return_sequences=True,
                dropout=self.config.dropout_rate,
                recurrent_dropout=0.0,
            ),
            name="bilstm",
        )(x)

        # Second LSTM layer
        lstm_units = self.config.hidden_dims[1] if len(self.config.hidden_dims) > 1 else 128
        x = tf.keras.layers.LSTM(
            lstm_units,
            dropout=self.config.dropout_rate,
            name="lstm_2",
        )(x)

        # Dense tower
        for i, units in enumerate(self.config.hidden_dims[2:], start=2):
            if self.config.use_batch_norm:
                x = tf.keras.layers.BatchNormalization(name=f"bn_{i}")(x)
            x = tf.keras.layers.Dropout(self.config.dropout_rate, name=f"drop_{i}")(x)
            x = tf.keras.layers.Dense(units, activation="relu", name=f"dense_{i}")(x)

        outputs = tf.keras.layers.Dense(
            self.config.output_dim, activation="softmax", name="output"
        )(x)

        self.model = tf.keras.Model(inputs=inputs, outputs=outputs, name=self.config.name)
        self._optimizer = tf.keras.optimizers.Adam(learning_rate=self.config.learning_rate)
        self._loss_fn = tf.keras.losses.SparseCategoricalCrossentropy()

        self.model.compile(
            optimizer=self._optimizer,
            loss=self._loss_fn,
            metrics=["accuracy"],
        )

        logger.info(
            "Built TFSequenceClassifier '%s': %d parameters",
            self.config.name,
            self.model.count_params(),
        )
        return self.model

    def predict(self, input_ids: np.ndarray) -> np.ndarray:
        """Run forward pass and return class probability distributions.

        Args:
            input_ids: Integer token array of shape (batch, seq_len).

        Returns:
            Probability array of shape (batch, output_dim).
        """
        if self.model is None:
            self.build_model()

        try:
            tf = _get_tf()
            tensor_in = tf.constant(input_ids, dtype=tf.int32)
            probs = self.model(tensor_in, training=False)
            return probs.numpy()
        except Exception as exc:
            logger.error("TFSequenceClassifier.predict failed: %s", exc)
            batch = input_ids.shape[0]
            uniform = np.ones((batch, self.config.output_dim), dtype=np.float32)
            return uniform / self.config.output_dim

    def train_step(self, inputs: np.ndarray, labels: np.ndarray) -> Dict[str, float]:
        """Perform one training step with gradient tape.

        Args:
            inputs: Integer token array (batch, seq_len).
            labels: Integer class labels (batch,).

        Returns:
            Dict with "loss" and "accuracy".
        """
        if self.model is None:
            self.build_model()

        try:
            tf = _get_tf()
            x = tf.constant(inputs, dtype=tf.int32)
            y = tf.constant(labels, dtype=tf.int32)

            with tf.GradientTape() as tape:
                logits = self.model(x, training=True)
                loss = self._loss_fn(y, logits)

            grads = tape.gradient(loss, self.model.trainable_variables)  # type: ignore[union-attr]
            self._optimizer.apply_gradients(  # type: ignore[union-attr]
                zip(grads, self.model.trainable_variables, strict=False)  # type: ignore[union-attr]
            )

            # Compute batch accuracy
            preds = tf.argmax(logits, axis=-1, output_type=tf.int32)
            accuracy = float(tf.reduce_mean(tf.cast(tf.equal(preds, y), tf.float32)).numpy())

            return {"loss": float(loss.numpy()), "accuracy": accuracy}

        except Exception as exc:
            logger.error("TFSequenceClassifier.train_step failed: %s", exc)
            return {"loss": float("nan"), "accuracy": 0.0}


class TFReinforcementAgent:
    """Deep Q-Network (DQN) agent implemented with TensorFlow/Keras.

    Features:
      - Online Q-network + frozen target network for stable training.
      - Epsilon-greedy action selection.
      - Huber loss (less sensitive to outliers than MSE).
      - Target network soft-updated via ``tau`` blending.
    """

    _TAU = 0.005  # Soft update coefficient for target network

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        config: TFModelConfig,
    ) -> None:
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.config = config
        self.q_network: Optional[Any] = None
        self.target_network: Optional[Any] = None
        self._optimizer: Optional[Any] = None
        self._loss_fn: Optional[Any] = None
        self._step_count: int = 0

    def build_q_network(self) -> Any:
        """Construct the online and target Q-networks.

        Architecture:
          Dense(hidden_dims[0], relu) → [Dense(h, relu)] * n → Dense(action_dim)

        Returns:
            The online Keras model.
        """
        tf = _get_tf()

        def _make_net(name: str) -> Any:
            model = tf.keras.Sequential(name=name)
            model.add(tf.keras.layers.InputLayer(input_shape=(self.state_dim,)))
            for i, units in enumerate(self.config.hidden_dims):
                model.add(tf.keras.layers.Dense(units, activation="relu", name=f"dense_{i}"))
                if self.config.use_batch_norm:
                    model.add(tf.keras.layers.BatchNormalization(name=f"bn_{i}"))
                if self.config.dropout_rate > 0:
                    model.add(tf.keras.layers.Dropout(self.config.dropout_rate, name=f"drop_{i}"))
            model.add(tf.keras.layers.Dense(self.action_dim, activation=None, name="q_values"))
            return model

        self.q_network = _make_net(f"{self.config.name}_online")
        self.target_network = _make_net(f"{self.config.name}_target")

        # Initialise target network weights from online network
        dummy = tf.zeros((1, self.state_dim))
        self.q_network(dummy)
        self.target_network(dummy)
        self.target_network.set_weights(self.q_network.get_weights())

        self._optimizer = tf.keras.optimizers.Adam(
            learning_rate=self.config.learning_rate, clipnorm=10.0
        )
        self._loss_fn = tf.keras.losses.Huber()

        logger.info(
            "Built DQN Q-network '%s': state_dim=%d, action_dim=%d, params=%d",
            self.config.name,
            self.state_dim,
            self.action_dim,
            self.q_network.count_params(),
        )
        return self.q_network

    def select_action(self, state: np.ndarray, epsilon: float = 0.1) -> int:
        """Epsilon-greedy action selection.

        Args:
            state:   State vector of shape (state_dim,) or (1, state_dim).
            epsilon: Exploration probability.  Decays outside this class.

        Returns:
            Integer action index in [0, action_dim).
        """
        if self.q_network is None:
            self.build_q_network()

        if np.random.rand() < epsilon:
            return int(np.random.randint(0, self.action_dim))

        try:
            tf = _get_tf()
            s = np.array(state, dtype=np.float32)
            if s.ndim == 1:
                s = s[np.newaxis, :]
            q_vals = self.q_network(tf.constant(s), training=False)
            return int(tf.argmax(q_vals, axis=-1).numpy()[0])
        except Exception as exc:
            logger.warning("select_action failed, returning random: %s", exc)
            return int(np.random.randint(0, self.action_dim))

    def train(self, batch: Dict) -> Dict[str, float]:
        """Perform one DQN gradient step.

        Expected keys in ``batch``:
          states       – (B, state_dim)
          actions      – (B,) integer action indices
          rewards      – (B,)
          next_states  – (B, state_dim)
          dones        – (B,) float 0/1 terminal flags
          gamma        – float discount factor (default 0.99)

        Returns:
            Dict with "loss" and "mean_q".
        """
        if self.q_network is None:
            self.build_q_network()

        try:
            tf = _get_tf()

            states = tf.constant(batch["states"], dtype=tf.float32)
            actions = tf.constant(batch["actions"], dtype=tf.int32)
            rewards = tf.constant(batch["rewards"], dtype=tf.float32)
            next_states = tf.constant(batch["next_states"], dtype=tf.float32)
            dones = tf.constant(batch["dones"], dtype=tf.float32)
            gamma: float = batch.get("gamma", 0.99)

            # Compute target Q-values using the frozen target network
            next_q = self.target_network(next_states, training=False)
            max_next_q = tf.reduce_max(next_q, axis=-1)
            targets = rewards + gamma * (1.0 - dones) * max_next_q  # (B,)

            B = states.shape[0]

            with tf.GradientTape() as tape:
                q_vals = self.q_network(states, training=True)  # (B, action_dim)
                # Gather Q-values for the taken actions
                indices = tf.stack([tf.range(B, dtype=tf.int32), actions], axis=1)
                predicted_q = tf.gather_nd(q_vals, indices)  # (B,)
                loss = self._loss_fn(targets, predicted_q)

            grads = tape.gradient(loss, self.q_network.trainable_variables)  # type: ignore[union-attr]
            self._optimizer.apply_gradients(  # type: ignore[union-attr]
                zip(grads, self.q_network.trainable_variables, strict=False)  # type: ignore[union-attr]
            )

            # Soft-update target network: θ_target = τ·θ + (1-τ)·θ_target
            self._step_count += 1
            if self._step_count % 10 == 0:
                online_weights = self.q_network.get_weights()  # type: ignore[union-attr]
                target_weights = self.target_network.get_weights()  # type: ignore[union-attr]
                new_weights = [
                    self._TAU * ow + (1 - self._TAU) * tw
                    for ow, tw in zip(online_weights, target_weights, strict=False)
                ]
                self.target_network.set_weights(new_weights)  # type: ignore[union-attr]

            mean_q = float(tf.reduce_mean(q_vals).numpy())
            return {"loss": float(loss.numpy()), "mean_q": mean_q}

        except Exception as exc:
            logger.error("TFReinforcementAgent.train failed: %s", exc)
            return {"loss": float("nan"), "mean_q": 0.0}
