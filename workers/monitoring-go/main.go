package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Alert represents a stored alert entry.
type Alert struct {
	ID        string            `json:"id"`
	Status    string            `json:"status"`
	Message   string            `json:"message"`
	Labels    map[string]string `json:"labels,omitempty"`
	Timestamp time.Time         `json:"timestamp"`
}

// WorkerSnapshot holds the health status of a single worker.
type WorkerSnapshot struct {
	URL     string        `json:"url"`
	Healthy bool          `json:"healthy"`
	LatencyMs int64  `json:"latency_ms"`
	Error   string        `json:"error,omitempty"`
}

// ringBuffer is a fixed-capacity FIFO for Alert.
type ringBuffer struct {
	mu   sync.RWMutex
	buf  []Alert
	head int
	size int
	cap  int
}

func newRingBuffer(capacity int) *ringBuffer {
	return &ringBuffer{
		buf: make([]Alert, capacity),
		cap: capacity,
	}
}

func (r *ringBuffer) push(a Alert) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.buf[r.head] = a
	r.head = (r.head + 1) % r.cap
	if r.size < r.cap {
		r.size++
	}
}

// all returns alerts newest-first, optionally filtered by status.
func (r *ringBuffer) all(status string) []Alert {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]Alert, 0, r.size)
	for i := 0; i < r.size; i++ {
		idx := ((r.head - 1 - i) + r.cap) % r.cap
		a := r.buf[idx]
		if status == "" || a.Status == status {
			out = append(out, a)
		}
	}
	return out
}

var (
	alerts  = newRingBuffer(1000)
	alertMu sync.Mutex
	alertID int

	httpRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "monitoring_http_requests_total",
			Help: "Total HTTP requests handled by the monitoring service.",
		},
		[]string{"method", "path", "status"},
	)
	alertsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "monitoring_alerts_total",
			Help: "Total alerts received.",
		},
		[]string{"status"},
	)
	workerHealthGauge = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "monitoring_worker_healthy",
			Help: "1 if the worker is healthy, 0 otherwise.",
		},
		[]string{"url"},
	)
)

func init() {
	prometheus.MustRegister(httpRequestsTotal, alertsTotal, workerHealthGauge)
}

func jsonResponse(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

// healthHandler — GET /health
func healthHandler(w http.ResponseWriter, r *http.Request) {
	httpRequestsTotal.WithLabelValues(r.Method, "/health", "200").Inc()
	jsonResponse(w, http.StatusOK, map[string]string{
		"status":    "ok",
		"service":   "monitoring-go",
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	})
}

// metricsHandler — GET /metrics (Prometheus exposition)
func metricsHandler() http.Handler {
	return promhttp.Handler()
}

// postAlertsHandler — POST /alerts
func postAlertsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 1<<16) // 64 KB limit
	var incoming struct {
		Status  string            `json:"status"`
		Message string            `json:"message"`
		Labels  map[string]string `json:"labels,omitempty"`
	}
	if err := json.NewDecoder(r.Body).Decode(&incoming); err != nil {
		httpRequestsTotal.WithLabelValues(r.Method, "/alerts", "400").Inc()
		jsonResponse(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON: " + err.Error()})
		return
	}
	if incoming.Status == "" {
		incoming.Status = "firing"
	}
	alertMu.Lock()
	alertID++
	id := fmt.Sprintf("alert-%d", alertID)
	alertMu.Unlock()

	a := Alert{
		ID:        id,
		Status:    incoming.Status,
		Message:   incoming.Message,
		Labels:    incoming.Labels,
		Timestamp: time.Now().UTC(),
	}
	alerts.push(a)
	metricStatus := a.Status
	if metricStatus != "firing" && metricStatus != "resolved" {
		metricStatus = "unknown"
	}
	alertsTotal.WithLabelValues(metricStatus).Inc()
	slog.Info("alert received", "id", a.ID, "status", a.Status, "message", a.Message)
	httpRequestsTotal.WithLabelValues(r.Method, "/alerts", "201").Inc()
	jsonResponse(w, http.StatusCreated, a)
}

// getAlertsHandler — GET /alerts?status=<optional>
func getAlertsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	status := r.URL.Query().Get("status")
	result := alerts.all(status)
	httpRequestsTotal.WithLabelValues(r.Method, "/alerts", "200").Inc()
	jsonResponse(w, http.StatusOK, map[string]any{
		"count":  len(result),
		"alerts": result,
	})
}

// alertsHandler dispatches GET/POST /alerts
func alertsHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		getAlertsHandler(w, r)
	case http.MethodPost:
		postAlertsHandler(w, r)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// snapshotsHandler — GET /snapshots
func snapshotsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	workerURLs := os.Getenv("WORKER_URLS")
	var snapshots []WorkerSnapshot
	if workerURLs == "" {
		httpRequestsTotal.WithLabelValues(r.Method, "/snapshots", "200").Inc()
		jsonResponse(w, http.StatusOK, map[string]any{"snapshots": snapshots, "note": "WORKER_URLS not configured"})
		return
	}

	urls := strings.Split(workerURLs, ",")
	var wg sync.WaitGroup
	mu := sync.Mutex{}
	snapshots = make([]WorkerSnapshot, 0, len(urls))

	client := &http.Client{Timeout: 5 * time.Second}
	for _, raw := range urls {
		url := strings.TrimSpace(raw)
		if url == "" {
			continue
		}
		wg.Add(1)
		go func(u string) {
			defer wg.Done()
			start := time.Now()
			resp, err := client.Get(u + "/health")
			latency := time.Since(start)
			snap := WorkerSnapshot{URL: u, LatencyMs: int64(latency / time.Millisecond)}
			if err != nil {
				snap.Healthy = false
				snap.Error = err.Error()
				workerHealthGauge.WithLabelValues(u).Set(0)
			} else {
				resp.Body.Close()
				snap.Healthy = resp.StatusCode == http.StatusOK
				if !snap.Healthy {
					snap.Error = fmt.Sprintf("HTTP %d", resp.StatusCode)
					workerHealthGauge.WithLabelValues(u).Set(0)
				} else {
					workerHealthGauge.WithLabelValues(u).Set(1)
				}
			}
			mu.Lock()
			snapshots = append(snapshots, snap)
			mu.Unlock()
		}(url)
	}
	wg.Wait()

	httpRequestsTotal.WithLabelValues(r.Method, "/snapshots", "200").Inc()
	jsonResponse(w, http.StatusOK, map[string]any{
		"timestamp": time.Now().UTC().Format(time.RFC3339),
		"snapshots": snapshots,
	})
}

func main() {
	// Structured JSON logging
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	// -healthcheck flag: used by Docker HEALTHCHECK CMD — probe /health and exit.
	if len(os.Args) > 1 && os.Args[1] == "-healthcheck" {
		port := os.Getenv("PORT")
		if port == "" {
			port = "8007"
		}
		resp, err := http.Get("http://127.0.0.1:" + port + "/health")
		if err != nil || resp.StatusCode >= 400 {
			os.Exit(1)
		}
		os.Exit(0)
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8007"
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.Handle("/metrics", metricsHandler())
	mux.HandleFunc("/alerts", alertsHandler)
	mux.HandleFunc("/snapshots", snapshotsHandler)

	srv := &http.Server{
		Addr:         net.JoinHostPort("", port),
		Handler:      mux,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGTERM, syscall.SIGINT)

	go func() {
		slog.Info("monitoring-go starting", "port", port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("server error", "err", err)
			os.Exit(1)
		}
	}()

	<-quit
	slog.Info("shutting down")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		slog.Error("shutdown error", "err", err)
	}
	slog.Info("stopped")
}
