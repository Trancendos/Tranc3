package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"sync"
	"syscall"
	"time"
)

// bucket is a token-bucket rate limiter for a single key.
type bucket struct {
	mu          sync.Mutex
	tokens      float64
	maxTokens   float64   // burst capacity
	ratePerSec  float64   // refill rate (tokens/second)
	lastRefill  time.Time
	lastAccess  time.Time
}

func newBucket(burst int, ratePerSec float64) *bucket {
	now := time.Now()
	return &bucket{
		tokens:     float64(burst),
		maxTokens:  float64(burst),
		ratePerSec: ratePerSec,
		lastRefill: now,
		lastAccess: now,
	}
}

// refill adds tokens based on elapsed time since last refill (must hold mu).
func (b *bucket) refill(now time.Time) {
	elapsed := now.Sub(b.lastRefill).Seconds()
	b.tokens += elapsed * b.ratePerSec
	if b.tokens > b.maxTokens {
		b.tokens = b.maxTokens
	}
	b.lastRefill = now
}

// check tries to consume `cost` tokens. Returns (allowed, remaining, resetAt).
func (b *bucket) check(cost int) (bool, int, time.Time) {
	b.mu.Lock()
	defer b.mu.Unlock()
	now := time.Now()
	b.refill(now)
	b.lastAccess = now

	c := float64(cost)
	if b.tokens >= c {
		b.tokens -= c
		resetAt := now.Add(time.Duration((b.maxTokens-b.tokens)/b.ratePerSec * float64(time.Second)))
		return true, int(b.tokens), resetAt
	}
	// Denied: tell caller when bucket will be full enough
	waitSec := (c - b.tokens) / b.ratePerSec
	resetAt := now.Add(time.Duration(waitSec * float64(time.Second)))
	return false, int(b.tokens), resetAt
}

func (b *bucket) reset(burst int) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.tokens = float64(burst)
	b.lastRefill = time.Now()
	b.lastAccess = time.Now()
}

func (b *bucket) remaining() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.refill(time.Now())
	return int(b.tokens)
}

func (b *bucket) idle() time.Duration {
	b.mu.Lock()
	defer b.mu.Unlock()
	return time.Since(b.lastAccess)
}

// ── Registry ─────────────────────────────────────────────────────────────────

type store struct {
	m           sync.Map // key(string) → *bucket
	defaultBurst int
	defaultRate  float64
}

func (s *store) get(key string) *bucket {
	if v, ok := s.m.Load(key); ok {
		return v.(*bucket)
	}
	b := newBucket(s.defaultBurst, s.defaultRate)
	actual, _ := s.m.LoadOrStore(key, b)
	return actual.(*bucket)
}

func (s *store) delete(key string) {
	s.m.Delete(key)
}

// evictLoop removes buckets idle for more than 1 hour.
func (s *store) evictLoop(ctx context.Context) {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			s.m.Range(func(k, v any) bool {
				if v.(*bucket).idle() > time.Hour {
					s.m.Delete(k)
					slog.Info("bucket evicted", "key", k)
				}
				return true
			})
		case <-ctx.Done():
			return
		}
	}
}

// ── Handlers ─────────────────────────────────────────────────────────────────

func jsonResponse(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func makeCheckHandler(st *store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var req struct {
			Key  string `json:"key"`
			Cost int    `json:"cost"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			jsonResponse(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
			return
		}
		if req.Key == "" {
			jsonResponse(w, http.StatusBadRequest, map[string]string{"error": "key is required"})
			return
		}
		if req.Cost <= 0 {
			req.Cost = 1
		}
		allowed, remaining, resetAt := st.get(req.Key).check(req.Cost)
		statusCode := http.StatusOK
		if !allowed {
			statusCode = http.StatusTooManyRequests
		}
		slog.Info("ratelimit check", "key", req.Key, "cost", req.Cost, "allowed", allowed, "remaining", remaining)
		jsonResponse(w, statusCode, map[string]any{
			"allowed":   allowed,
			"remaining": remaining,
			"reset_at":  resetAt.UTC().Format(time.RFC3339),
		})
	}
}

func makeResetHandler(st *store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var req struct {
			Key string `json:"key"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			jsonResponse(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
			return
		}
		if req.Key == "" {
			jsonResponse(w, http.StatusBadRequest, map[string]string{"error": "key is required"})
			return
		}
		st.get(req.Key).reset(st.defaultBurst)
		slog.Info("ratelimit reset", "key", req.Key)
		jsonResponse(w, http.StatusOK, map[string]string{"reset": req.Key})
	}
}

func makeStatusHandler(st *store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		buckets := make(map[string]any)
		st.m.Range(func(k, v any) bool {
			b := v.(*bucket)
			buckets[k.(string)] = map[string]any{
				"remaining":    b.remaining(),
				"max_tokens":   int(b.maxTokens),
				"rate_per_sec": b.ratePerSec,
				"idle_seconds": int(b.idle().Seconds()),
			}
			return true
		})
		jsonResponse(w, http.StatusOK, map[string]any{
			"buckets":   buckets,
			"timestamp": time.Now().UTC().Format(time.RFC3339),
		})
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	jsonResponse(w, http.StatusOK, map[string]string{
		"status":    "ok",
		"service":   "rate-limit-service-go",
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	})
}

// ── Main ─────────────────────────────────────────────────────────────────────

func envInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}

func envFloat(key string, fallback float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return fallback
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	burst := envInt("RATE_LIMIT_DEFAULT_BURST", 100)
	rate := envFloat("RATE_LIMIT_DEFAULT_RATE_PER_SEC", 10)

	st := &store{
		defaultBurst: burst,
		defaultRate:  rate,
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8028"
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go st.evictLoop(ctx)

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/ratelimit/check", makeCheckHandler(st))
	mux.HandleFunc("/ratelimit/reset", makeResetHandler(st))
	mux.HandleFunc("/ratelimit/status", makeStatusHandler(st))

	srv := &http.Server{
		Addr:         net.JoinHostPort("", port),
		Handler:      mux,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGTERM, syscall.SIGINT)

	go func() {
		slog.Info("rate-limit-service-go starting", "port", port, "burst", burst, "rate_per_sec", rate)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("server error", "err", err)
			os.Exit(1)
		}
	}()

	<-quit
	cancel()
	slog.Info("shutting down")
	shutCtx, shutCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutCancel()
	if err := srv.Shutdown(shutCtx); err != nil {
		slog.Error("shutdown error", "err", err)
	}
	slog.Info("stopped")
}
