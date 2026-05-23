"""
TRANC3 — Inference Engine
Combines the trained model with a personality profile to produce responses.

This is the runtime layer — what runs when someone is actually talking to Tranc3.
The model does the language generation; the personality shapes the behaviour.

Security: Uses safe_torch_load to prevent pickle-based RCE (CVE-2024-48063, CVE-2025-32434)
"""

from typing import Any, Dict, List, Optional

import torch

from ..core.config import InferenceConfig, ModelConfig
from ..core.model import Tranc3Model
from ..core.security import safe_torch_load
from ..core.tokenizer import Tranc3Tokenizer
from ..personality.matrix import PersonalityMatrix, PersonalityProfile


def resolve_device(preference: str = "auto") -> torch.device:
    if preference == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(preference)


class Tranc3Engine:
    """
    The live inference runtime.
    Load once; call generate() for each response.
    """

    def __init__(
        self,
        model_path: str,
        tokenizer_path: str,
        model_config: ModelConfig,
        inference_config: InferenceConfig,
        personality_matrix: PersonalityMatrix,
        active_profile: str = "tranc3-base",
    ):
        self.device = resolve_device(inference_config.device)
        self.inf_cfg = inference_config

        # Load tokenizer
        self.tokenizer = Tranc3Tokenizer(tokenizer_path)

        # Load model securely (prevents pickle-based RCE)
        self.model = Tranc3Model(model_config)
        checkpoint = safe_torch_load(model_path, device=str(self.device))
        state = checkpoint.get("model_state", checkpoint)
        self.model.load_state_dict(state)
        self.model.to(self.device)
        self.model.eval()

        # Verify model integrity (optional, requires known hash)
        # verify_model_integrity(model_path, expected_sha256="...")

        # Personality
        self.matrix = personality_matrix
        self.active_profile: PersonalityProfile = self.matrix.get(active_profile)

        print(f"[Engine] Ready — profile: {self.active_profile.name} | device: {self.device}")

    def switch_profile(self, name: str):
        """Switch personality at runtime without reloading the model."""
        self.active_profile = self.matrix.get(name)
        print(f"[Engine] Profile switched → {name}")

    def generate(
        self,
        conversation_history: List[Dict[str, str]],
        user_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate a response given a conversation history.

        Args:
            conversation_history: list of {"role": "user"|"assistant", "content": "..."}
            user_context: optional dict of contextual info (name, mood, etc.)

        Returns:
            str: the model's response
        """
        system_prompt = self.active_profile.build_system_prompt(user_context)

        input_ids = self.tokenizer.format_conversation(
            system_prompt=system_prompt,
            turns=conversation_history,
            add_generation_prompt=True,
        )

        input_tensor = torch.tensor([input_ids], dtype=torch.long, device=self.device)

        # Use profile's generation params, falling back to inference config defaults
        p = self.active_profile
        output = self.model.generate(
            input_tensor,
            max_new_tokens=p.max_new_tokens,
            temperature=p.temperature,
            top_k=p.top_k,
            top_p=p.top_p,
            repetition_penalty=p.repetition_penalty,
        )

        # Decode only the newly generated tokens
        new_tokens = output[0][len(input_ids) :].tolist()
        response = self.tokenizer.decode(new_tokens, skip_special=True)
        return response.strip()


# ------------------------------------------------------------------
# Simple CLI for local testing
# ------------------------------------------------------------------


def run_cli(engine: Tranc3Engine):
    print(
        f"\nTranc3 [{engine.active_profile.name}] — type 'exit' to quit, "
        f"'switch <profile>' to change personality\n"
    )

    history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break

        if not user_input:
            continue

        if user_input.lower() == "exit":
            break

        if user_input.lower().startswith("switch "):
            profile_name = user_input[7:].strip()
            try:
                engine.switch_profile(profile_name)
                history = []  # clear history on profile switch
                print(f"[Switched to {profile_name}. History cleared.]\n")
            except KeyError as e:
                print(f"[Error: {e}]\n")
            continue

        history.append({"role": "user", "content": user_input})

        response = engine.generate(history)
        history.append({"role": "assistant", "content": response})

        print(f"\nTranc3: {response}\n")
