use aeonmind_core::adaptive::{AdaptiveConfig, AdaptiveMetaLearner};
use criterion::{black_box, criterion_group, criterion_main, Criterion};

fn bench_adaptive_step(c: &mut Criterion) {
    let config = AdaptiveConfig::default();
    let mut learner = AdaptiveMetaLearner::new(config);
    let gradient = vec![0.1f64; 10];
    c.bench_function("adaptive_step", |b| {
        b.iter(|| learner.step(black_box(&gradient)))
    });
}

criterion_group!(benches, bench_adaptive_step);
criterion_main!(benches);
