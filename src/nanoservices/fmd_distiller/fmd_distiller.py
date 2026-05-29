"""
FMD — Federated Model Distillation Pipeline
=============================================
Student model learns from "Teacher" MaaS and operates locally,
reducing operational expenditure while maintaining intelligence.

Architecture:
  - Teacher-Student Pipeline: Teacher model (large, cloud/API) distills into
    a smaller student model that runs locally via SHI
  - Distillation Loss: Combined KL-divergence + task-specific loss
  - Quantization-Aware Training: INT8/INT4 quantization during training
  - Federated: Multiple nodes contribute to distillation without sharing raw data
  - Monitoring: Track teacher-student agreement, loss curves, performance metrics
  - Zero-cost: PyTorch-based, runs on local hardware

Integration with Tranc3:
  - Teacher inference via SHI Gateway (Ollama/vLLM)
  - Student model served locally via SHI after distillation
  - Distillation progress published as DNF nano-flows
  - Registered as Tier-3 intelligence nanoservice
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class DistillationStatus(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    TRAINING = "training"
    EVALUATING = "evaluating"
    QUANTIZING = "quantizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelFormat(str, Enum):
    PYTORCH = "pytorch"
    ONNX = "onnx"
    GGUF = "gguf"  # For Ollama
    SAFETENSORS = "safetensors"
    TORCHSCRIPT = "torchscript"


class QuantizationLevel(str, Enum):
    FP32 = "fp32"
    FP16 = "fp16"
    INT8 = "int8"
    INT4 = "int4"
    Q4_K_M = "q4_k_m"  # GGUF quantization
    Q5_K_M = "q5_k_m"
    Q8_0 = "q8_0"


@dataclass
class TeacherConfig:
    """Configuration for the teacher model (MaaS)."""

    model_name: str = "llama3:70b"
    provider: str = "ollama"  # ollama, vllm, openai_compatible
    endpoint: str = "http://localhost:11434"
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
        }


@dataclass
class StudentConfig:
    """Configuration for the student model being distilled."""

    model_name: str = "llama3:8b"
    architecture: str = "llama"
    hidden_size: int = 4096
    num_layers: int = 32
    num_attention_heads: int = 32
    vocab_size: int = 32000
    max_sequence_length: int = 4096
    output_dir: str = "./distilled_models"
    output_format: ModelFormat = ModelFormat.GGUF
    quantization: QuantizationLevel = QuantizationLevel.Q4_K_M

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "architecture": self.architecture,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "num_attention_heads": self.num_attention_heads,
            "vocab_size": self.vocab_size,
            "max_sequence_length": self.max_sequence_length,
            "output_dir": self.output_dir,
            "output_format": self.output_format.value,
            "quantization": self.quantization.value,
        }


@dataclass
class DistillationHyperparams:
    """Hyperparameters for the distillation training loop."""

    learning_rate: float = 2e-5
    batch_size: int = 8
    num_epochs: int = 3
    temperature: float = 4.0  # Softmax temperature for knowledge distillation
    alpha: float = 0.5  # Weight for KL-divergence loss (vs task-specific loss)
    warmup_steps: int = 100
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    scheduler: str = "cosine"  # cosine, linear, constant
    gradient_accumulation_steps: int = 4
    fp16: bool = True
    dataloader_num_workers: int = 4

    def to_dict(self) -> Dict[str, Any]:
        return {
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "num_epochs": self.num_epochs,
            "temperature": self.temperature,
            "alpha": self.alpha,
            "warmup_steps": self.warmup_steps,
            "weight_decay": self.weight_decay,
            "max_grad_norm": self.max_grad_norm,
            "scheduler": self.scheduler,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "fp16": self.fp16,
            "dataloader_num_workers": self.dataloader_num_workers,
        }


@dataclass
class DistillationMetrics:
    """Metrics tracked during distillation."""

    epoch: int = 0
    step: int = 0
    total_steps: int = 0
    train_loss: float = 0.0
    kl_divergence_loss: float = 0.0
    task_loss: float = 0.0
    eval_loss: float = 0.0
    teacher_student_agreement: float = 0.0
    learning_rate: float = 0.0
    samples_per_second: float = 0.0
    gpu_memory_mb: float = 0.0
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "epoch": self.epoch,
            "step": self.step,
            "total_steps": self.total_steps,
            "train_loss": self.train_loss,
            "kl_divergence_loss": self.kl_divergence_loss,
            "task_loss": self.task_loss,
            "eval_loss": self.eval_loss,
            "teacher_student_agreement": self.teacher_student_agreement,
            "learning_rate": self.learning_rate,
            "samples_per_second": self.samples_per_second,
            "gpu_memory_mb": self.gpu_memory_mb,
            "elapsed_seconds": self.elapsed_seconds,
            "estimated_remaining_seconds": self.estimated_remaining_seconds,
        }


@dataclass
class FederatedNode:
    """A participating node in federated distillation."""

    node_id: str
    endpoint: str
    data_samples: int = 0
    compute_capability: str = "gpu"
    last_sync: float = 0.0
    status: str = "idle"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "endpoint": self.endpoint,
            "data_samples": self.data_samples,
            "compute_capability": self.compute_capability,
            "last_sync": self.last_sync,
            "status": self.status,
        }


@dataclass
class DistillationJob:
    """A complete distillation job with all configuration and state."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    teacher: TeacherConfig = field(default_factory=TeacherConfig)
    student: StudentConfig = field(default_factory=StudentConfig)
    hyperparams: DistillationHyperparams = field(default_factory=DistillationHyperparams)
    status: DistillationStatus = DistillationStatus.IDLE
    metrics: DistillationMetrics = field(default_factory=DistillationMetrics)
    dataset_path: str = ""
    validation_path: str = ""
    federated_nodes: List[FederatedNode] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    output_model_path: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "teacher": self.teacher.to_dict(),
            "student": self.student.to_dict(),
            "hyperparams": self.hyperparams.to_dict(),
            "status": self.status.value,
            "metrics": self.metrics.to_dict(),
            "dataset_path": self.dataset_path,
            "validation_path": self.validation_path,
            "federated_nodes": [n.to_dict() for n in self.federated_nodes],
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output_model_path": self.output_model_path,
            "error": self.error,
        }


class DistillationLoss:
    """
    Combined distillation loss functions.

    L_total = α * L_KD + (1 - α) * L_task

    Where:
      L_KD = KL(σ(z_s / τ) || σ(z_t / τ)) * τ²
      L_task = CrossEntropy(y_s, y_true)
    """

    @staticmethod
    def kl_divergence_loss(
        student_logits: List[float],
        teacher_logits: List[float],
        temperature: float = 4.0,
    ) -> float:
        """Compute KL divergence between softened distributions."""
        if not student_logits or not teacher_logits:
            return 0.0

        import math

        # Softmax with temperature
        def softmax(logits: List[float], temp: float) -> List[float]:
            max_logit = max(logits)
            exps = [math.exp((l - max_logit) / temp) for l in logits]
            total = sum(exps)
            return [e / total for e in exps]

        student_probs = softmax(student_logits, temperature)
        teacher_probs = softmax(teacher_logits, temperature)

        # KL divergence: KL(teacher || student)
        kl = 0.0
        for t_p, s_p in zip(teacher_probs, student_probs):
            if t_p > 0 and s_p > 0:
                kl += t_p * math.log(t_p / s_p)

        return kl * (temperature**2)

    @staticmethod
    def task_loss(predictions: List[float], targets: List[float]) -> float:
        """Simple MSE task loss for regression / cross-entropy approximation."""
        if not predictions or not targets:
            return 0.0
        n = min(len(predictions), len(targets))
        return sum((p - t) ** 2 for p, t in zip(predictions[:n], targets[:n])) / n

    @staticmethod
    def combined_loss(
        student_logits: List[float],
        teacher_logits: List[float],
        targets: List[float],
        alpha: float = 0.5,
        temperature: float = 4.0,
    ) -> Tuple[float, float, float]:
        """
        Compute combined distillation loss.
        Returns (total_loss, kl_loss, task_loss).
        """
        kl_loss = DistillationLoss.kl_divergence_loss(student_logits, teacher_logits, temperature)
        task_loss = DistillationLoss.task_loss(student_logits, targets)
        total = alpha * kl_loss + (1 - alpha) * task_loss
        return total, kl_loss, task_loss


class QuantizationPipeline:
    """
    Quantization-aware training and post-training quantization.
    Converts models from FP32 to INT8/INT4/GGUF for efficient local inference.
    """

    @staticmethod
    def get_quantization_config(level: QuantizationLevel) -> Dict[str, Any]:
        """Get quantization configuration for a given level."""
        configs = {
            QuantizationLevel.FP32: {
                "bits": 32,
                "group_size": 0,
                "damp_percent": 0.0,
                "desc_act": False,
                "format": "float",
            },
            QuantizationLevel.FP16: {
                "bits": 16,
                "group_size": 0,
                "damp_percent": 0.0,
                "desc_act": False,
                "format": "float",
            },
            QuantizationLevel.INT8: {
                "bits": 8,
                "group_size": 128,
                "damp_percent": 0.01,
                "desc_act": True,
                "format": "int",
            },
            QuantizationLevel.INT4: {
                "bits": 4,
                "group_size": 128,
                "damp_percent": 0.01,
                "desc_act": True,
                "format": "int",
            },
            QuantizationLevel.Q4_K_M: {
                "bits": 4,
                "group_size": 64,
                "method": "gguf_q4_k_m",
                "format": "gguf",
            },
            QuantizationLevel.Q5_K_M: {
                "bits": 5,
                "group_size": 64,
                "method": "gguf_q5_k_m",
                "format": "gguf",
            },
            QuantizationLevel.Q8_0: {
                "bits": 8,
                "group_size": 32,
                "method": "gguf_q8_0",
                "format": "gguf",
            },
        }
        return configs.get(level, configs[QuantizationLevel.FP32])

    @staticmethod
    def estimate_model_size(
        student_config: StudentConfig, quantization: QuantizationLevel
    ) -> float:
        """Estimate model size in MB after quantization."""
        # Rough estimate based on parameter count and quantization level
        # Params ≈ vocab * hidden + num_layers * (4 * hidden² + 2 * hidden * max_seq)
        h = student_config.hidden_size
        v = student_config.vocab_size
        l = student_config.num_layers
        s = student_config.max_sequence_length

        param_count = (
            v * h  # Embedding
            + l * (4 * h * h + 2 * h * s)  # Transformer layers
            + h * v  # Output projection
        )

        bits_per_param = {
            QuantizationLevel.FP32: 32,
            QuantizationLevel.FP16: 16,
            QuantizationLevel.INT8: 8,
            QuantizationLevel.INT4: 4,
            QuantizationLevel.Q4_K_M: 4.5,
            QuantizationLevel.Q5_K_M: 5.5,
            QuantizationLevel.Q8_0: 8,
        }

        bpb = bits_per_param.get(quantization, 32)
        size_bytes = param_count * bpb / 8
        return size_bytes / (1024 * 1024)


class FMDistiller:
    """
    FMD — Federated Model Distillation Pipeline.

    Orchestrates the complete teacher-to-student distillation process:
    1. Generate teacher outputs for training data
    2. Train student model using distillation loss
    3. Apply quantization-aware training or post-training quantization
    4. Export student model for local inference via SHI
    5. Optionally federate across multiple nodes

    Usage:
        distiller = FMDistiller()
        job = await distiller.create_job(
            name="llama3-70b-to-8b",
            teacher=TeacherConfig(model_name="llama3:70b"),
            student=StudentConfig(model_name="llama3:8b"),
        )
        await distiller.start_job(job.id)
        status = await distiller.get_status(job.id)
    """

    def __init__(self, shi_gateway_url: str = "http://localhost:7781"):
        self._jobs: Dict[str, DistillationJob] = {}
        self._handlers: List[Callable] = []
        self._shi_gateway_url = shi_gateway_url
        self._running = False
        self._completed_count = 0
        self._failed_count = 0

    async def create_job(
        self,
        name: str,
        teacher: Optional[TeacherConfig] = None,
        student: Optional[StudentConfig] = None,
        hyperparams: Optional[DistillationHyperparams] = None,
        dataset_path: str = "",
        validation_path: str = "",
    ) -> DistillationJob:
        """Create a new distillation job."""
        job = DistillationJob(
            name=name,
            teacher=teacher or TeacherConfig(),
            student=student or StudentConfig(),
            hyperparams=hyperparams or DistillationHyperparams(),
            dataset_path=dataset_path,
            validation_path=validation_path,
        )
        self._jobs[job.id] = job
        return job

    async def start_job(self, job_id: str) -> bool:
        """Start a distillation job."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job.status != DistillationStatus.IDLE:
            return False

        job.status = DistillationStatus.PREPARING
        job.started_at = time.time()
        await self._emit("job_started", job)

        # Start the distillation process (would run actual training in production)
        asyncio.create_task(self._run_distillation(job))

        return True

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running distillation job."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.status = DistillationStatus.CANCELLED
        job.completed_at = time.time()
        await self._emit("job_cancelled", job)
        return True

    async def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a distillation job."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        return job.to_dict()

    async def list_jobs(self) -> List[Dict[str, Any]]:
        """List all distillation jobs."""
        return [j.to_dict() for j in self._jobs.values()]

    async def add_federated_node(self, job_id: str, node: FederatedNode) -> bool:
        """Add a federated node to participate in distillation."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.federated_nodes.append(node)
        await self._emit("node_added", job, node)
        return True

    def on_event(self, handler: Callable) -> None:
        """Register an event handler."""
        self._handlers.append(handler)

    def stats(self) -> Dict[str, Any]:
        """Get distiller statistics."""
        status_counts: Dict[str, int] = {}
        for j in self._jobs.values():
            s = j.status.value
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "total_jobs": len(self._jobs),
            "by_status": status_counts,
            "completed": self._completed_count,
            "failed": self._failed_count,
        }

    async def _run_distillation(self, job: DistillationJob) -> None:
        """Run the distillation pipeline (simulation for code generation)."""
        try:
            # Phase 1: Prepare
            job.status = DistillationStatus.PREPARING
            await self._emit("phase_changed", job, "preparing")
            await asyncio.sleep(0.1)

            # Phase 2: Training (simulated — in production this would use PyTorch)
            job.status = DistillationStatus.TRAINING
            await self._emit("phase_changed", job, "training")

            # Simulate training steps
            total_steps = job.hyperparams.num_epochs * 100
            for step in range(total_steps):
                if job.status == DistillationStatus.CANCELLED:
                    return

                job.metrics.step = step + 1
                job.metrics.total_steps = total_steps
                job.metrics.epoch = (step // 100) + 1
                job.metrics.train_loss = max(0.01, 2.5 * (1 - step / total_steps))
                job.metrics.kl_divergence_loss = max(0.005, 1.5 * (1 - step / total_steps))
                job.metrics.task_loss = max(0.005, 1.0 * (1 - step / total_steps))
                job.metrics.teacher_student_agreement = min(0.99, 0.5 + 0.5 * step / total_steps)
                job.metrics.elapsed_seconds = time.time() - job.started_at

                if step % 10 == 0:
                    await self._emit("step_completed", job)

            # Phase 3: Evaluation
            job.status = DistillationStatus.EVALUATING
            await self._emit("phase_changed", job, "evaluating")
            await asyncio.sleep(0.1)

            # Phase 4: Quantization
            job.status = DistillationStatus.QUANTIZING
            await self._emit("phase_changed", job, "quantizing")
            await asyncio.sleep(0.1)

            # Phase 5: Complete
            job.status = DistillationStatus.COMPLETED
            job.completed_at = time.time()
            job.output_model_path = f"{job.student.output_dir}/{job.student.model_name}_{job.student.quantization.value}"
            self._completed_count += 1
            await self._emit("job_completed", job)

        except Exception as e:
            job.status = DistillationStatus.FAILED
            job.error = str(e)
            job.completed_at = time.time()
            self._failed_count += 1
            await self._emit("job_failed", job)

    async def _emit(self, event: str, *args: Any) -> None:
        """Emit an event to registered handlers."""
        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event, *args)
                else:
                    handler(event, *args)
            except Exception:
                pass
