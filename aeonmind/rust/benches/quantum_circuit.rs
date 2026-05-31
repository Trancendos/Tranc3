use aeonmind_core::quantum::{QuantumCircuitConfig, QuantumDecisionCircuit};
use criterion::{black_box, criterion_group, criterion_main, Criterion};

fn bench_quantum_execute(c: &mut Criterion) {
    let config = QuantumCircuitConfig::default();
    let circuit = QuantumDecisionCircuit::new(config);
    let input = vec![0.5f64; 4];
    c.bench_function("quantum_execute", |b| {
        b.iter(|| circuit.execute(Some(black_box(&input))))
    });
}

criterion_group!(benches, bench_quantum_execute);
criterion_main!(benches);
