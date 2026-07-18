/*
AeonMind Adaptive Meta-Learning — L-BFGS Optimization.

Implements adaptive hyperparameter tuning with:
    - L-BFGS two-loop recursion for Hessian approximation
    - Adaptive learning rate with momentum
    - Gradient clipping
    - Weight decay regularization
    - History-based curvature estimation

Part of the Tranc3 Infinity Ecosystem.
*/

use serde::{Deserialize, Serialize};

// ─── Configuration ──────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdaptiveConfig {
    pub n_parameters: usize,
    pub learning_rate: f64,
    pub history_size: usize,
    pub bounds: (f64, f64),
    pub adaptive_lr: bool,
    pub momentum: f64,
    pub weight_decay: f64,
    pub gradient_clip: f64,
}

impl Default for AdaptiveConfig {
    fn default() -> Self {
        Self {
            n_parameters: 10,
            learning_rate: 0.01,
            history_size: 10,
            bounds: (-10.0, 10.0),
            adaptive_lr: true,
            momentum: 0.9,
            weight_decay: 0.0001,
            gradient_clip: 5.0,
        }
    }
}

// ─── L-BFGS History Entry ───────────────────────────────────

#[derive(Debug, Clone)]
struct LbfgsEntry {
    s: Vec<f64>, // Parameter difference
    y: Vec<f64>, // Gradient difference
    rho: f64,    // 1 / (y^T s)
}

// ─── Adaptive Step ──────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdaptiveStep {
    pub iteration: usize,
    pub cost: f64,
    pub gradient_norm: f64,
    pub learning_rate: f64,
    pub step_size: f64,
}

// ─── Adaptive Summary ───────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdaptiveSummary {
    pub n_parameters: usize,
    pub learning_rate: f64,
    pub history_size: usize,
    pub iterations: usize,
    pub final_cost: Option<f64>,
}

// ─── Adaptive Meta-Learner ──────────────────────────────────

pub struct AdaptiveMetaLearner {
    config: AdaptiveConfig,
    parameters: Vec<f64>,
    velocity: Vec<f64>,
    history: Vec<LbfgsEntry>,
    prev_gradient: Option<Vec<f64>>,
    iteration: usize,
    current_cost: Option<f64>,
    step_history: Vec<AdaptiveStep>,
}

impl AdaptiveMetaLearner {
    pub fn new(config: AdaptiveConfig) -> Self {
        let mut rng = rand::thread_rng();
        let parameters: Vec<f64> = (0..config.n_parameters)
            .map(|_| {
                let (lo, hi) = config.bounds;
                rand::Rng::gen_range(&mut rng, lo..hi)
            })
            .collect();

        Self {
            velocity: vec![0.0; config.n_parameters],
            history: Vec::new(),
            prev_gradient: None,
            iteration: 0,
            current_cost: None,
            step_history: Vec::new(),
            config,
            parameters,
        }
    }

    pub fn with_parameters(config: AdaptiveConfig, parameters: Vec<f64>) -> Self {
        let n = parameters.len();
        let mut learner = Self::new(AdaptiveConfig {
            n_parameters: n,
            ..config
        });
        learner.parameters = parameters;
        learner
    }

    /// Compute L-BFGS search direction using two-loop recursion.
    pub fn lbfgs_direction(&self, gradient: &[f64]) -> Vec<f64> {
        let mut q = gradient.to_vec();

        // First loop (backwards through history)
        let m = self.history.len();
        let mut alphas = vec![0.0; m];

        for i in (0..m).rev() {
            alphas[i] = self.history[i].rho * dot(&self.history[i].s, &q);
            for (qj, yj) in q.iter_mut().zip(self.history[i].y.iter()) {
                *qj -= alphas[i] * yj;
            }
        }

        // Initial Hessian approximation (scaled identity)
        let gamma = if m > 0 {
            let last = &self.history[m - 1];
            let y_norm_sq = dot(&last.y, &last.y);
            if y_norm_sq > 1e-10 {
                dot(&last.s, &last.y) / y_norm_sq
            } else {
                1.0
            }
        } else {
            1.0
        };

        let mut r: Vec<f64> = q.iter().map(|&v| gamma * v).collect();

        // Second loop (forwards through history)
        for (alpha_i, hist_item) in alphas.iter().zip(self.history.iter()) {
            let beta = hist_item.rho * dot(&hist_item.y, &r);
            for (rj, sj) in r.iter_mut().zip(hist_item.s.iter()) {
                *rj += sj * (alpha_i - beta);
            }
        }

        r
    }

    /// Perform one optimization step.
    pub fn step(&mut self, gradient: &[f64]) -> AdaptiveStep {
        let grad_norm = norm(gradient);

        // Gradient clipping
        let clipped: Vec<f64> = if grad_norm > self.config.gradient_clip {
            gradient
                .iter()
                .map(|&g| g * self.config.gradient_clip / grad_norm)
                .collect()
        } else {
            gradient.to_vec()
        };

        // Compute L-BFGS direction
        let direction = self.lbfgs_direction(&clipped);

        // Snapshot parameters before update so we can compute the true s vector
        let prev_params = self.parameters.clone();

        // Momentum update
        let lr = self.config.learning_rate;
        for (vel, dir) in self.velocity.iter_mut().zip(direction.iter()) {
            *vel = self.config.momentum * *vel - lr * dir;
        }

        // Parameter update with weight decay
        let (lo, hi) = self.config.bounds;
        for (param, vel) in self.parameters.iter_mut().zip(self.velocity.iter()) {
            *param += vel - self.config.weight_decay * *param;
            // Apply bounds
            *param = param.max(lo).min(hi);
        }

        // Update L-BFGS history with true parameter difference x_{k+1} - x_k
        if let Some(ref prev_grad) = self.prev_gradient {
            let s: Vec<f64> = self
                .parameters
                .iter()
                .zip(prev_params.iter())
                .map(|(p_new, p_old)| p_new - p_old)
                .collect();
            let y: Vec<f64> = clipped
                .iter()
                .zip(prev_grad.iter())
                .map(|(&g, &pg)| g - pg)
                .collect();
            let ys = dot(&y, &s);
            if ys > 1e-10 {
                self.history.push(LbfgsEntry {
                    s,
                    y,
                    rho: 1.0 / ys,
                });
                if self.history.len() > self.config.history_size {
                    self.history.remove(0);
                }
            }
        }

        self.prev_gradient = Some(clipped);
        self.iteration += 1;

        // Adaptive learning rate
        if self.config.adaptive_lr {
            self.adapt_learning_rate();
        }

        let step_size = norm(&self.velocity);

        let step = AdaptiveStep {
            iteration: self.iteration,
            cost: self.current_cost.unwrap_or(0.0),
            gradient_norm: grad_norm,
            learning_rate: self.config.learning_rate,
            step_size,
        };
        self.step_history.push(step.clone());
        step
    }

    /// Run full optimization loop.
    pub fn optimize<F, G>(
        &mut self,
        cost_fn: F,
        gradient_fn: G,
        n_iterations: usize,
    ) -> Vec<AdaptiveStep>
    where
        F: Fn(&[f64]) -> f64 + Copy,
        G: Fn(&[f64]) -> Vec<f64> + Copy,
    {
        let mut steps = Vec::new();
        for _ in 0..n_iterations {
            let cost = cost_fn(&self.parameters);
            self.current_cost = Some(cost);
            let gradient = gradient_fn(&self.parameters);
            let step = self.step(&gradient);
            steps.push(step);
        }
        steps
    }

    /// Adapt learning rate based on progress.
    pub fn adapt_learning_rate(&mut self) {
        if self.step_history.len() >= 2 {
            let current = &self.step_history[self.step_history.len() - 1];
            let prev = &self.step_history[self.step_history.len() - 2];

            if current.gradient_norm > prev.gradient_norm * 1.2 {
                self.config.learning_rate *= 0.8;
            } else if current.gradient_norm < prev.gradient_norm * 0.8 {
                self.config.learning_rate = (self.config.learning_rate * 1.05).min(0.1);
            }
            self.config.learning_rate = self.config.learning_rate.max(1e-6);
        }
    }

    /// Get current parameters.
    pub fn parameters_array(&self) -> &[f64] {
        &self.parameters
    }

    /// Get summary.
    pub fn summary(&self) -> AdaptiveSummary {
        AdaptiveSummary {
            n_parameters: self.config.n_parameters,
            learning_rate: self.config.learning_rate,
            history_size: self.config.history_size,
            iterations: self.iteration,
            final_cost: self.current_cost,
        }
    }
}

// ─── Helper Functions ───────────────────────────────────────

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(&x, &y)| x * y).sum()
}

fn norm(v: &[f64]) -> f64 {
    v.iter().map(|x| x * x).sum::<f64>().sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_learner_creation() {
        let config = AdaptiveConfig::default();
        let learner = AdaptiveMetaLearner::new(config);
        assert_eq!(learner.parameters.len(), 10);
    }

    #[test]
    fn test_step() {
        let config = AdaptiveConfig {
            n_parameters: 5,
            ..Default::default()
        };
        let mut learner = AdaptiveMetaLearner::new(config);
        let gradient = vec![0.1; 5];
        let step = learner.step(&gradient);
        assert_eq!(step.iteration, 1);
    }

    #[test]
    fn test_lbfgs_direction() {
        let config = AdaptiveConfig {
            n_parameters: 5,
            ..Default::default()
        };
        let learner = AdaptiveMetaLearner::new(config);
        let gradient = vec![0.5; 5];
        let direction = learner.lbfgs_direction(&gradient);
        assert_eq!(direction.len(), 5);
    }

    #[test]
    fn test_gradient_clipping() {
        let config = AdaptiveConfig {
            n_parameters: 3,
            gradient_clip: 1.0,
            ..Default::default()
        };
        let mut learner = AdaptiveMetaLearner::new(config);
        let gradient = vec![100.0; 3];
        let step = learner.step(&gradient);
        // gradient_norm reports the pre-clip magnitude for convergence monitoring.
        // Input [100, 100, 100] has L2 norm = 100*sqrt(3) ≈ 173.2, well above clip=1.0.
        let expected_norm = (100.0_f64.powi(2) * 3.0).sqrt();
        assert!((step.gradient_norm - expected_norm).abs() < 1e-6);
    }

    #[test]
    fn test_momentum() {
        let config = AdaptiveConfig {
            n_parameters: 3,
            momentum: 0.9,
            ..Default::default()
        };
        let mut learner = AdaptiveMetaLearner::new(config);
        let grad1 = vec![1.0; 3];
        learner.step(&grad1);
        let grad2 = vec![1.0; 3];
        learner.step(&grad2);
        // With momentum, velocity should accumulate
        assert!(learner.velocity.iter().any(|&v| v != 0.0));
    }

    #[test]
    fn test_with_parameters() {
        let config = AdaptiveConfig::default();
        let params = vec![1.0, 2.0, 3.0];
        let learner = AdaptiveMetaLearner::with_parameters(config, params.clone());
        assert_eq!(learner.parameters, params);
    }

    #[test]
    fn test_quadratic_optimization() {
        let config = AdaptiveConfig {
            n_parameters: 3,
            learning_rate: 0.1,
            momentum: 0.0,
            adaptive_lr: false,
            ..Default::default()
        };
        // Use a deterministic starting point to avoid flakiness from random init.
        let mut learner = AdaptiveMetaLearner::with_parameters(config, vec![3.0, -3.0, 3.0]);
        // Minimize f(x) = sum(x_i^2)
        for _ in 0..100 {
            let grad: Vec<f64> = learner.parameters.iter().map(|&x| 2.0 * x).collect();
            learner.step(&grad);
        }
        // Parameters should converge near zero.
        let param_norm: f64 = learner.parameters.iter().map(|x| x * x).sum::<f64>().sqrt();
        assert!(param_norm < 1.0);
    }

    #[test]
    fn test_summary() {
        let config = AdaptiveConfig::default();
        let learner = AdaptiveMetaLearner::new(config);
        let summary = learner.summary();
        assert_eq!(summary.n_parameters, 10);
    }
}
