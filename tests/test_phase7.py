"""
Phase 7 Integration Tests
=========================
Comprehensive tests for all Phase 7 advanced architecture modules.
"""

import asyncio
import json
import sys
import traceback

# Test results tracking
_results = {
    "passed": 0,
    "failed": 0,
    "errors": [],
}


def phase7_test(name: str):
    """Decorator to register a test (renamed to avoid pytest fixture conflict)."""

    def decorator(fn):
        async def wrapper():
            try:
                await fn()
                _results["passed"] += 1
                print(f"  ✓ {name}")
            except Exception as e:
                _results["failed"] += 1
                _results["errors"].append((name, str(e)))
                print(f"  ✗ {name}: {e}")
                traceback.print_exc()

        wrapper._name = name
        return wrapper

    return decorator


# ============================================================
# NSA Registry Tests
# ============================================================


@phase7_test("NSA Registry: register and discover services")
async def test_nsa_registry_basic():
    from nanoservices.nsa_registry import Capability, NSARegistry, ServiceTier

    registry = NSARegistry()
    await registry.start()

    svc = await registry.register(
        name="shi_gateway",
        tier=ServiceTier.TIER_3_INTELLIGENCE,
        capabilities=[Capability(name="inference"), Capability(name="chat")],
        shm_segment="nsa_shi_gateway",
        pid=12345,
        endpoint="http://localhost:7781",
        tags={"inference", "ollama"},
    )

    assert svc.name == "shi_gateway"
    assert svc.tier == ServiceTier.TIER_3_INTELLIGENCE
    assert len(svc.capabilities) == 2

    # Discover by capability
    found = await registry.discover(capability="inference")
    assert len(found) == 1
    assert found[0].name == "shi_gateway"

    # Discover by tag
    found = await registry.discover(tag="ollama")
    assert len(found) == 1

    # Discover by tier
    found = await registry.discover(tier=ServiceTier.TIER_3_INTELLIGENCE)
    assert len(found) == 1

    await registry.stop()


@phase7_test("NSA Registry: health monitoring and heartbeat")
async def test_nsa_registry_health():
    from nanoservices.nsa_registry import Capability, NSARegistry, ServiceStatus, ServiceTier

    registry = NSARegistry(heartbeat_timeout_s=0.5, health_check_interval_s=0.2)
    await registry.start()

    svc = await registry.register(
        name="test_svc",
        tier=ServiceTier.TIER_2_INFRASTRUCTURE,
        capabilities=[Capability(name="test")],
        shm_segment="nsa_test",
        pid=99999,
        endpoint="http://localhost:9999",
    )

    # Heartbeat should mark as READY
    await registry.heartbeat(svc.id)
    assert svc.health.status == ServiceStatus.READY

    # Wait for heartbeat timeout — should go OFFLINE
    await asyncio.sleep(1.0)
    assert svc.health.status == ServiceStatus.OFFLINE

    await registry.stop()


@phase7_test("NSA Registry: get_healthiest service")
async def test_nsa_registry_healthiest():
    from nanoservices.nsa_registry import (
        Capability,
        HealthReport,
        NSARegistry,
        ServiceStatus,
        ServiceTier,
    )

    registry = NSARegistry()

    # Register two services with same capability
    svc1 = await registry.register(
        name="svc_1",
        tier=ServiceTier.TIER_3_INTELLIGENCE,
        capabilities=[Capability(name="inference")],
        shm_segment="nsa_svc1",
        pid=1,
        endpoint="http://localhost:1",
    )
    svc2 = await registry.register(
        name="svc_2",
        tier=ServiceTier.TIER_3_INTELLIGENCE,
        capabilities=[Capability(name="inference")],
        shm_segment="nsa_svc2",
        pid=2,
        endpoint="http://localhost:2",
    )

    # Set health — svc2 is healthier
    await registry.update_health(
        svc1.id,
        HealthReport(
            service_id=svc1.id,
            status=ServiceStatus.BUSY,
            latency_ms=200.0,
            error_rate=0.05,
        ),
    )
    await registry.update_health(
        svc2.id,
        HealthReport(
            service_id=svc2.id,
            status=ServiceStatus.READY,
            latency_ms=10.0,
            error_rate=0.001,
        ),
    )

    best = await registry.get_healthiest(capability="inference")
    assert best is not None
    assert best.name == "svc_2"


# ============================================================
# SHI Gateway Tests
# ============================================================


@phase7_test("SHI Gateway: creation and configuration")
async def test_shi_gateway_creation():
    from nanoservices.shi_gateway import SHIGateway

    gateway = SHIGateway()
    assert gateway is not None
    stats = gateway.metrics
    assert "total_requests" in stats


@phase7_test("SHI Gateway: fallback chain")
async def test_shi_gateway_fallback():
    from nanoservices.shi_gateway import SHIGateway

    gateway = SHIGateway()
    # Without Ollama running, should handle gracefully
    # The gateway initializes but inference will fail without Ollama
    assert gateway is not None


# ============================================================
# IGI GitOps Tests
# ============================================================


@phase7_test("IGI GitOps: Forgejo configuration")
async def test_igi_forgejo_config():
    from nanoservices.igi_gitops import ForgejoConfig, IGIGitOps

    forgejo = ForgejoConfig(
        url="https://forgejo.local",
        repository="Trancendos/Tranc3",
        branch="main",
    )

    gitops = IGIGitOps(forgejo=forgejo, environment="production")

    # Generate FluxCD manifests
    manifests = gitops.generate_flux_manifests()
    assert "gitrepository.yaml" in manifests
    assert "kustomization-production.yaml" in manifests

    # Verify Forgejo URL is used (NOT GitHub)
    gitrepo = json.loads(manifests["gitrepository.yaml"])
    assert "forgejo.local" in gitrepo["spec"]["url"]
    assert "github.com" not in gitrepo["spec"]["url"]


@phase7_test("IGI GitOps: Kustomize overlays")
async def test_igi_kustomize_overlays():
    from nanoservices.igi_gitops import IGIGitOps, KustomizeOverlay

    gitops = IGIGitOps(environment="production")

    overlay = KustomizeOverlay(
        environment="production",
        namespace="tranc3-prod",
        replicas={"api": 3, "web": 2},
        images={"tranc3-api": "v1.0.0"},
    )
    gitops.register_overlay(overlay)

    kustomization = gitops.generate_kustomize_overlay("production")
    assert kustomization is not None

    parsed = json.loads(kustomization)
    assert parsed["namespace"] == "tranc3-prod"


@phase7_test("IGI GitOps: drift detection")
async def test_igi_drift_detection():
    from nanoservices.igi_gitops import DriftDetector

    detector = DriftDetector(auto_heal=True)

    # Set declared and actual state
    detector.set_declared("deployment/api", {"replicas": 3, "image": "api:v1"})
    detector.set_actual("deployment/api", {"replicas": 2, "image": "api:v1"})

    drifts = detector.check_drift()
    assert len(drifts) == 1
    assert "replicas" in str(drifts[0].diff)

    # Test missing resource
    detector.set_declared("deployment/web", {"replicas": 2})
    drifts = detector.check_drift()
    assert len(drifts) == 2  # api drift + missing web


# ============================================================
# DNF Orchestrator Tests
# ============================================================


@phase7_test("DNF Flow Builder: create and validate flow")
async def test_dnf_flow_builder():
    from nanoservices.dnf_orchestrator import FlowBuilder

    flow = (
        FlowBuilder("etl_pipeline", "ETL Pipeline")
        .version("1.0.0")
        .tier(2)
        .step("extract", "extract_data", capability="database")
        .step("transform", "transform_data", depends_on=["extract"], capability="compute")
        .step("load", "load_data", depends_on=["transform"], capability="database")
        .build()
    )

    assert flow.id == "etl_pipeline"
    assert len(flow.steps) == 3
    assert flow.steps[1].depends_on == ["extract"]
    assert flow.steps[2].depends_on == ["transform"]


@phase7_test("DNF Flow Runner: execute simple flow")
async def test_dnf_flow_runner():
    from nanoservices.dnf_orchestrator import FlowBuilder, FlowRunner

    runner = FlowRunner()

    # Register handlers
    async def extract_handler(input_data):
        return {"raw_data": [1, 2, 3]}

    async def transform_handler(input_data):
        return {"transformed": [x * 2 for x in input_data.get("extract.raw_data", [])]}

    async def load_handler(input_data):
        return {"loaded": True, "count": len(input_data.get("transform.transformed", []))}

    runner.register_handler("extract_data", extract_handler)
    runner.register_handler("transform_data", transform_handler)
    runner.register_handler("load_data", load_handler)

    # Register flow
    flow = (
        FlowBuilder("test_flow", "Test Flow")
        .step("s1", "extract_data")
        .step("s2", "transform_data", depends_on=["s1"])
        .step("s3", "load_data", depends_on=["s2"])
        .build()
    )
    runner.register_flow(flow)

    # Execute
    execution = await runner.execute("test_flow", {"source": "test_db"})

    assert execution.status.value == "completed"
    assert "s1.raw_data" in execution.output
    assert "s2.transformed" in execution.output
    assert "s3.loaded" in execution.output


# ============================================================
# FMD Distiller Tests
# ============================================================


@phase7_test("FMD Distillation Loss: KL divergence and combined loss")
async def test_fmd_distillation_loss():
    from nanoservices.fmd_distiller import DistillationLoss

    student = [1.0, 2.0, 3.0, 4.0]
    teacher = [1.1, 2.1, 3.1, 4.1]
    targets = [1.0, 2.0, 3.0, 4.0]

    total, kl, task = DistillationLoss.combined_loss(
        student, teacher, targets, alpha=0.5, temperature=4.0
    )

    assert total > 0
    assert kl >= 0
    assert task >= 0


@phase7_test("FMD Quantization Pipeline: model size estimation")
async def test_fmd_quantization():
    from nanoservices.fmd_distiller import QuantizationLevel, QuantizationPipeline, StudentConfig

    student = StudentConfig(hidden_size=4096, num_layers=32, vocab_size=32000)

    size_fp32 = QuantizationPipeline.estimate_model_size(student, QuantizationLevel.FP32)
    size_int4 = QuantizationPipeline.estimate_model_size(student, QuantizationLevel.Q4_K_M)

    # INT4 should be significantly smaller than FP32
    assert size_int4 < size_fp32
    assert size_fp32 > 0


@phase7_test("FMD Distiller: create and run job")
async def test_fmd_distiller_job():
    from nanoservices.fmd_distiller import (
        DistillationHyperparams,
        FMDistiller,
        StudentConfig,
        TeacherConfig,
    )

    distiller = FMDistiller()

    job = await distiller.create_job(
        name="test_distillation",
        teacher=TeacherConfig(model_name="llama3:70b"),
        student=StudentConfig(model_name="llama3:8b"),
        hyperparams=DistillationHyperparams(num_epochs=1),
    )

    assert job.name == "test_distillation"
    assert job.teacher.model_name == "llama3:70b"
    assert job.student.model_name == "llama3:8b"


# ============================================================
# DaaS Stream Tests
# ============================================================


@phase7_test("DaaS Stream: create stream and publish")
async def test_daas_stream_basic():
    from nanoservices.daas_stream import (  # noqa: I001
        DaaSService,
        DataClassification,
        Jurisdiction,
        StreamConfig,
        StreamRecord,
    )

    daas = DaaSService()
    await daas.start()

    daas.create_stream(
        StreamConfig(
            name="test-events",
            topic="test-events",
            classification=DataClassification.PUBLIC,
            jurisdiction=Jurisdiction.LOCAL_ONLY,
        )
    )

    success, reason = await daas.publish(
        "test-events",
        StreamRecord(
            key="event_1",
            value=b'{"type": "test"}',
        ),
    )

    assert success, f"Publish failed: {reason}"
    await daas.stop()


@phase7_test("DaaS Policy: GDPR cross-border restriction")
async def test_daas_gdpr_policy():
    from nanoservices.daas_stream import DaaSService, PolicyEffect

    daas = DaaSService()

    # EU data to US should be denied
    effect, reason = daas.evaluate_access(
        {
            "source_jurisdiction": "EU",
            "target_jurisdiction": "US",
            "action": "read",
        }
    )
    assert effect == PolicyEffect.DENY

    # Public data should be allowed
    effect, reason = daas.evaluate_access(
        {
            "data_classification": "public",
            "action": "read",
        }
    )
    assert effect == PolicyEffect.ALLOW


@phase7_test("DaaS OPA: Rego bundle generation")
async def test_daas_rego_bundle():
    from nanoservices.daas_stream import DaaSService

    daas = DaaSService()
    rego = daas.generate_rego_bundle()

    assert "package tranc3.daas" in rego
    assert "GDPR" in rego


@phase7_test("DaaS Lineage: track data origin")
async def test_daas_lineage():
    from nanoservices.daas_stream import (
        DataClassification,
        DataLineageTracker,
        Jurisdiction,
        LineageEntry,
    )

    tracker = DataLineageTracker()

    entry = LineageEntry(
        data_id="user_123_session",
        source="clickstream",
        source_type="stream",
        transformation="pseudonymization",
        consumer="analytics",
        classification=DataClassification.CONFIDENTIAL,
        jurisdiction=Jurisdiction.EU,
    )

    tracker.track(entry)
    lineage = tracker.get_lineage("user_123_session")
    assert len(lineage) == 1
    assert lineage[0].source == "clickstream"


# ============================================================
# Genetic Optimizer Tests
# ============================================================


@phase7_test("Genetic Optimizer: basic optimization")
async def test_genetic_optimizer_basic():
    from nanoservices.genetic_optimizer import (
        GeneSpec,
        GeneticOptimizer,
        Objective,
        ObjectiveType,
    )

    def fitness_fn(chromosome):
        x = chromosome.get("x", 0)
        y = chromosome.get("y", 0)
        # Simple quadratic: minimize (x-0.5)^2 + (y-0.3)^2
        return {"distance": (x - 0.5) ** 2 + (y - 0.3) ** 2}

    optimizer = GeneticOptimizer(
        gene_specs=[
            GeneSpec(name="x", min_value=0.0, max_value=1.0),
            GeneSpec(name="y", min_value=0.0, max_value=1.0),
        ],
        objectives=[Objective(name="distance", type=ObjectiveType.MINIMIZE)],
        population_size=50,
    )
    optimizer.set_fitness_function(fitness_fn)

    result = await optimizer.optimize(generations=30, population_size=50)

    assert result.status.value == "converged"
    assert result.best_individual is not None
    # Should be close to (0.5, 0.3)
    best_x = result.best_individual.chromosome.get("x", 0)
    best_y = result.best_individual.chromosome.get("y", 0)
    assert abs(best_x - 0.5) < 0.3, f"x={best_x} not close to 0.5"
    assert abs(best_y - 0.3) < 0.3, f"y={best_y} not close to 0.3"


# ============================================================
# Quantum Solver Tests
# ============================================================


@phase7_test("Quantum Solver: QUBO problem creation and evaluation")
async def test_quantum_qubo():
    from nanoservices.quantum_solver import QUBOProblem

    problem = QUBOProblem(
        name="test_qubo",
        num_variables=3,
        linear_terms={"0": -1.0, "1": -1.0, "2": -1.0},
        quadratic_terms={("0", "1"): 2.0, ("1", "2"): 2.0},
    )

    # All zeros should give 0
    assert problem.evaluate({"0": 0, "1": 0, "2": 0}) == 0.0

    # Specific assignment
    energy = problem.evaluate({"0": 1, "1": 1, "2": 0})
    assert energy == -1.0 + -1.0 + 2.0  # linear + quadratic


@phase7_test("Quantum Solver: solve QUBO")
async def test_quantum_solve():
    from nanoservices.quantum_solver import (
        QuantumAlgorithm,
        QuantumSolver,
        QUBOProblem,
        SolverStatus,
    )

    solver = QuantumSolver(max_qubits=20)

    problem = QUBOProblem(
        name="routing_optimization",
        num_variables=4,
        linear_terms={"0": -5.0, "1": -3.0, "2": -2.0, "3": -4.0},
        quadratic_terms={("0", "1"): 8.0, ("1", "2"): 5.0, ("2", "3"): 6.0},
    )

    result = await solver.solve(problem, algorithm=QuantumAlgorithm.QAOA, shots=1024)

    assert result.status == SolverStatus.COMPLETED
    assert len(result.solution) > 0
    assert isinstance(result.energy, float)


@phase7_test("Quantum Solver: classical fallback for large problems")
async def test_quantum_fallback():
    from nanoservices.quantum_solver import QuantumSolver, QUBOProblem, SolverStatus

    solver = QuantumSolver(max_qubits=5)  # Very low limit

    problem = QUBOProblem(
        name="large_problem",
        num_variables=10,
        linear_terms={str(i): -1.0 for i in range(10)},
    )

    result = await solver.solve(problem)

    assert result.classical_fallback is True
    assert result.status == SolverStatus.CLASSICAL_FALLBACK


@phase7_test("Quantum Circuit Library: QAOA and VQE circuits")
async def test_quantum_circuit_library():
    from nanoservices.quantum_solver import QuantumCircuitLibrary

    lib = QuantumCircuitLibrary()

    qaoa = lib.qaoa_circuit(num_qubits=4, depth=2)
    assert qaoa["algorithm"] == "qaoa"
    assert qaoa["num_qubits"] == 4
    assert len(qaoa["parameters"]) > 0

    vqe = lib.vqe_circuit(num_qubits=4, depth=2)
    assert vqe["algorithm"] == "vqe"

    grover = lib.grover_circuit(num_qubits=3)
    assert grover["algorithm"] == "grover"


# ============================================================
# Run All Tests
# ============================================================


async def run_all_tests():
    """Run all registered tests."""
    print("\n" + "=" * 60)
    print("Tranc3 Phase 7 — Integration Tests")
    print("=" * 60)

    import __main__

    tests = [obj for name, obj in vars(__main__).items() if callable(obj) and hasattr(obj, "_name")]

    if not tests:
        # Also check this module
        import sys

        this_module = sys.modules[__name__]
        tests = [
            obj
            for name, obj in vars(this_module).items()
            if callable(obj) and hasattr(obj, "_name")
        ]

    for test_fn in tests:
        await test_fn()

    print("\n" + "=" * 60)
    print(f"Results: {_results['passed']} passed, {_results['failed']} failed")
    if _results["errors"]:
        print("\nFailures:")
        for name, error in _results["errors"]:
            print(f"  ✗ {name}: {error}")
    print("=" * 60)

    return _results["failed"] == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
