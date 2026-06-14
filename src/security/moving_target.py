"""Moving target defense: rotating endpoints, secrets, and decoy infrastructure."""

from __future__ import annotations

import hashlib
import secrets
import time


class MovingTargetDefense:
    def __init__(self, rotation_interval_seconds: int = 3600) -> None:
        self._rotation_interval = rotation_interval_seconds
        self._current_epoch: int = 0
        self._path_mapping: dict[str, str] = {}
        self._master_seed: bytes = secrets.token_bytes(32)
        self._jwt_secret: bytes = self._generate_epoch_secret(0)
        self._decoy_paths: set[str] = set()
        self._last_rotation: float = time.time()
        self._decoy_paths = self._generate_decoy_paths(self._current_epoch)

    def _generate_epoch_secret(self, epoch: int) -> bytes:
        return hashlib.sha256(
            b"tranc3-mtd-" + epoch.to_bytes(8, "big") + self._master_seed
        ).digest()

    def _obfuscate_path(self, canonical: str, epoch: int) -> str:
        version = epoch % 9 + 1
        digest = hashlib.sha256((canonical + str(epoch)).encode()).hexdigest()[:8]
        return f"/api/v{version}/{digest}"

    def _generate_decoy_paths(self, epoch: int) -> set[str]:
        decoys: set[str] = set()
        for i in range(10):
            seed = f"decoy-{epoch}-{i}"
            digest = hashlib.sha256(seed.encode()).hexdigest()[:8]
            version = (epoch + i) % 9 + 1
            decoys.add(f"/api/v{version}/decoy-{digest}")
        return decoys

    def rotate(self) -> dict:
        self._current_epoch += 1
        self._jwt_secret = self._generate_epoch_secret(self._current_epoch)

        new_mapping: dict[str, str] = {}
        for canonical in self._path_mapping:
            new_mapping[canonical] = self._obfuscate_path(canonical, self._current_epoch)
        self._path_mapping = new_mapping

        self._decoy_paths = self._generate_decoy_paths(self._current_epoch)
        self._last_rotation = time.time()

        return {
            "epoch": self._current_epoch,
            "rotated_at": self._last_rotation,
            "paths_remapped": len(self._path_mapping),
            "decoy_paths_generated": len(self._decoy_paths),
        }

    def should_rotate(self) -> bool:
        return time.time() - self._last_rotation > self._rotation_interval

    def maybe_rotate(self) -> dict | None:
        if self.should_rotate():
            return self.rotate()
        return None

    def resolve_path(self, obfuscated_path: str) -> str | None:
        for canonical, obfuscated in self._path_mapping.items():
            if obfuscated == obfuscated_path:
                return canonical
        return None

    def is_decoy(self, path: str) -> bool:
        return path in self._decoy_paths

    def get_jwt_secret(self) -> bytes:
        return self._jwt_secret

    def register_canonical_path(self, canonical: str) -> str:
        obfuscated = self._obfuscate_path(canonical, self._current_epoch)
        self._path_mapping[canonical] = obfuscated
        return obfuscated

    def status(self) -> dict:
        now = time.time()
        seconds_until_next = max(
            0.0,
            self._rotation_interval - (now - self._last_rotation),
        )
        return {
            "epoch": self._current_epoch,
            "last_rotation": self._last_rotation,
            "path_count": len(self._path_mapping),
            "decoy_count": len(self._decoy_paths),
            "seconds_until_next_rotation": round(seconds_until_next, 1),
        }
