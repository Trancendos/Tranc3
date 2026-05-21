"""
TRANC3 — Tokenizer
BPE tokenizer built on SentencePiece. Runs entirely locally.
Train once on your corpus; the model file is yours permanently.

Special tokens:
  <pad>  : padding
  <bos>  : beginning of sequence
  <eos>  : end of sequence
  <unk>  : unknown token
  <sys>  : system/personality prompt boundary
  <usr>  : user turn boundary
  <ast>  : assistant turn boundary
"""

import os
import tempfile
from pathlib import Path
from typing import List

import sentencepiece as spm

SPECIAL_TOKENS = {
    "pad_token": "<pad>",  # nosec B105 — false positive: not a password

    "bos_token": "<bos>",  # nosec B105 — false positive: not a password

    "eos_token": "<eos>",  # nosec B105 — false positive: not a password

    "unk_token": "<unk>",  # nosec B105 — false positive: not a password

    "sys_token": "<sys>",  # nosec B105 — false positive: not a password

    "usr_token": "<usr>",  # nosec B105 — false positive: not a password

    "ast_token": "<ast>",  # nosec B105 — false positive: not a password

}

PAD_ID = 0
BOS_ID = 1
EOS_ID = 2
UNK_ID = 3
SYS_ID = 4
USR_ID = 5
AST_ID = 6


class Tranc3Tokenizer:
    def __init__(self, model_path: str):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Tokenizer model not found at {model_path}.\n"
                f"Run: python scripts/train_tokenizer.py --data_dir data/raw"
            )
        self.sp = spm.SentencePieceProcessor()
        self.sp.load(model_path)
        self.vocab_size = self.sp.get_piece_size()

    # ------------------------------------------------------------------
    # Core encode / decode
    # ------------------------------------------------------------------

    def encode(
        self,
        text: str,
        add_bos: bool = True,
        add_eos: bool = True,
    ) -> List[int]:
        ids = self.sp.encode(text, out_type=int)
        if add_bos:
            ids = [BOS_ID] + ids
        if add_eos:
            ids = ids + [EOS_ID]
        return ids

    def decode(self, ids: List[int], skip_special: bool = True) -> str:
        special_ids = set(range(7)) if skip_special else set()
        filtered = [i for i in ids if i not in special_ids]
        return self.sp.decode(filtered)

    # ------------------------------------------------------------------
    # Conversation formatting
    # ------------------------------------------------------------------

    def format_conversation(
        self,
        system_prompt: str,
        turns: List[dict],  # [{"role": "user"|"assistant", "content": "..."}]
        add_generation_prompt: bool = True,
    ) -> List[int]:
        """
        Encodes a full conversation with role boundaries.
        Format: <sys> system <usr> user turn <ast> assistant turn ...
        """
        ids = []

        # System prompt
        if system_prompt:
            ids += [SYS_ID] + self.sp.encode(system_prompt, out_type=int)

        for turn in turns:
            if turn["role"] == "user":
                ids += [USR_ID] + self.sp.encode(turn["content"], out_type=int)
            elif turn["role"] == "assistant":
                ids += [AST_ID] + self.sp.encode(turn["content"], out_type=int) + [EOS_ID]

        if add_generation_prompt:
            ids += [AST_ID]

        return ids

    def __len__(self):
        return self.vocab_size


# ------------------------------------------------------------------
# Tokenizer training (run once)
# ------------------------------------------------------------------

def train_tokenizer(
    data_dir: str,
    output_path: str = "models/tokenizer.model",
    vocab_size: int = 32_000,
    character_coverage: float = 0.9995,
):
    """
    Trains a BPE tokenizer on all .txt files in data_dir.
    Only needs to be run once per dataset.
    """
    data_files = list(Path(data_dir).glob("**/*.txt"))
    if not data_files:
        raise FileNotFoundError(f"No .txt files found in {data_dir}")

    # Write file list for sentencepiece
    file_list_path = os.path.join(tempfile.gettempdir(), "tranc3_tokenizer_input.txt")  # nosec B108 — temp dir for tokenizer cache
    with open(file_list_path, "w") as f:
        for p in data_files:
            f.write(str(p) + "\n")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    prefix = output_path.replace(".model", "")

    print(f"Training tokenizer on {len(data_files)} files → vocab_size={vocab_size}")

    # Build special tokens string for sentencepiece
    ",".join(SPECIAL_TOKENS.values())

    spm.SentencePieceTrainer.train(
        input=",".join(str(p) for p in data_files),
        model_prefix=prefix,
        vocab_size=vocab_size,
        model_type="bpe",
        character_coverage=character_coverage,
        pad_id=PAD_ID,
        bos_id=BOS_ID,
        eos_id=EOS_ID,
        unk_id=UNK_ID,
        user_defined_symbols="<sys>,<usr>,<ast>",
        input_sentence_size=5_000_000,
        shuffle_input_sentence=True,
    )

    print(f"Tokenizer saved to {output_path}")
    return Tranc3Tokenizer(output_path)
