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
)

// Priority levels
const (
	PriorityHigh   = "high"
	PriorityNormal = "normal"
	PriorityLow    = "low"
)

var priorityOrder = []string{PriorityHigh, PriorityNormal, PriorityLow}

// Task is a single queue entry.
type Task struct {
	TaskID    string          `json:"task_id"`
	QueueName string          `json:"queue_name"`
	Priority  string          `json:"priority"`
	Payload   json.RawMessage `json:"payload"`
	EnqueuedAt time.Time     `json:"enqueued_at"`
}

// QueueStats holds counters for one (queue, priority) pair.
type QueueStats struct {
	Depth     int `json:"depth"`
	Processed int `json:"processed"`
	Failed    int `json:"failed"`
}

// priorityQueue is a thread-safe triple-priority queue for one named queue.
type priorityQueue struct {
	mu     sync.Mutex
	queues map[string][]Task // keyed by priority
	stats  map[string]*QueueStats
}

func newPriorityQueue() *priorityQueue {
	q := &priorityQueue{
		queues: make(map[string][]Task),
		stats:  make(map[string]*QueueStats),
	}
	for _, p := range priorityOrder {
		q.queues[p] = []Task{}
		q.stats[p] = &QueueStats{}
	}
	return q
}

func (q *priorityQueue) enqueue(t Task) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.queues[t.Priority] = append(q.queues[t.Priority], t)
	q.stats[t.Priority].Depth++
}

// dequeue pops the next task from the given priority (or highest available if "").
func (q *priorityQueue) dequeue(priority string) (Task, bool) {
	q.mu.Lock()
	defer q.mu.Unlock()
	priorities := priorityOrder
	if priority != "" {
		priorities = []string{priority}
	}
	for _, p := range priorities {
		if len(q.queues[p]) > 0 {
			t := q.queues[p][0]
			q.queues[p] = q.queues[p][1:]
			q.stats[p].Depth--
			q.stats[p].Processed++
			return t, true
		}
	}
	return Task{}, false
}

// contains returns true if a task with the given ID exists in any priority queue.
func (q *priorityQueue) contains(taskID string) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	for _, p := range priorityOrder {
		for _, t := range q.queues[p] {
			if t.TaskID == taskID {
				return true
			}
		}
	}
	return false
}

// cancel removes a task by ID across all priorities.  Returns true if found.
func (q *priorityQueue) cancel(taskID string) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	for _, p := range priorityOrder {
		for i, t := range q.queues[p] {
			if t.TaskID == taskID {
				q.queues[p] = append(q.queues[p][:i], q.queues[p][i+1:]...)
				q.stats[p].Depth--
				return true
			}
		}
	}
	return false
}

func (q *priorityQueue) snapshot() map[string]*QueueStats {
	q.mu.Lock()
	defer q.mu.Unlock()
	out := make(map[string]*QueueStats, len(q.stats))
	for k, v := range q.stats {
		cp := *v
		out[k] = &cp
	}
	return out
}

// Registry of named queues
type registry struct {
	mu     sync.RWMutex
	queues map[string]*priorityQueue
}

func newRegistry() *registry {
	return &registry{queues: make(map[string]*priorityQueue)}
}

func (r *registry) get(name string) *priorityQueue {
	r.mu.RLock()
	q, ok := r.queues[name]
	r.mu.RUnlock()
	if ok {
		return q
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if q, ok = r.queues[name]; ok {
		return q
	}
	q = newPriorityQueue()
	r.queues[name] = q
	return q
}

func (r *registry) status() map[string]map[string]*QueueStats {
	r.mu.RLock()
	names := make([]string, 0, len(r.queues))
	for n := range r.queues {
		names = append(names, n)
	}
	r.mu.RUnlock()

	out := make(map[string]map[string]*QueueStats, len(names))
	for _, n := range names {
		out[n] = r.get(n).snapshot()
	}
	return out
}

// ── Global registry ──────────────────────────────────────────────────────────

var reg = newRegistry()

// ── Helpers ──────────────────────────────────────────────────────────────────

func jsonResponse(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func validPriority(p string) bool {
	for _, v := range priorityOrder {
		if v == p {
			return true
		}
	}
	return false
}

// ── Handlers ─────────────────────────────────────────────────────────────────

// POST /queue/enqueue
func enqueueHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 1<<20) // 1 MB limit
	var req struct {
		TaskID    string          `json:"task_id"`
		Payload   json.RawMessage `json:"payload"`
		Priority  string          `json:"priority"`
		QueueName string          `json:"queue_name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		jsonResponse(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON: " + err.Error()})
		return
	}
	if req.TaskID == "" {
		jsonResponse(w, http.StatusBadRequest, map[string]string{"error": "task_id is required"})
		return
	}
	if req.QueueName == "" {
		req.QueueName = "default"
	}
	if req.Priority == "" {
		req.Priority = PriorityNormal
	}
	if !validPriority(req.Priority) {
		jsonResponse(w, http.StatusBadRequest, map[string]string{
			"error": fmt.Sprintf("priority must be one of: %s", strings.Join(priorityOrder, ", ")),
		})
		return
	}
	q := reg.get(req.QueueName)
	if q.contains(req.TaskID) {
		jsonResponse(w, http.StatusConflict, map[string]string{
			"error": fmt.Sprintf("task_id %q already exists in queue %q", req.TaskID, req.QueueName),
		})
		return
	}
	t := Task{
		TaskID:     req.TaskID,
		QueueName:  req.QueueName,
		Priority:   req.Priority,
		Payload:    req.Payload,
		EnqueuedAt: time.Now().UTC(),
	}
	q.enqueue(t)
	slog.Info("task enqueued", "task_id", t.TaskID, "queue", t.QueueName, "priority", t.Priority)
	jsonResponse(w, http.StatusCreated, t)
}

// POST /queue/dequeue?queue=<name>&priority=<p>
func dequeueHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	queueName := r.URL.Query().Get("queue")
	if queueName == "" {
		queueName = "default"
	}
	priority := r.URL.Query().Get("priority")
	if priority != "" && !validPriority(priority) {
		jsonResponse(w, http.StatusBadRequest, map[string]string{
			"error": fmt.Sprintf("priority must be one of: %s", strings.Join(priorityOrder, ", ")),
		})
		return
	}
	task, ok := reg.get(queueName).dequeue(priority)
	if !ok {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	slog.Info("task dequeued", "task_id", task.TaskID, "queue", queueName)
	jsonResponse(w, http.StatusOK, task)
}

// GET /queue/status
func statusHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	jsonResponse(w, http.StatusOK, map[string]any{
		"queues":    reg.status(),
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	})
}

// DELETE /queue/{task_id}
func cancelHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	// Path: /queue/<task_id>
	taskID := strings.TrimPrefix(r.URL.Path, "/queue/")
	taskID = strings.TrimSpace(taskID)
	if taskID == "" || taskID == "enqueue" || taskID == "dequeue" || taskID == "status" {
		jsonResponse(w, http.StatusBadRequest, map[string]string{"error": "invalid task_id in path"})
		return
	}
	// Search all queues
	found := false
	reg.mu.RLock()
	names := make([]string, 0, len(reg.queues))
	for n := range reg.queues {
		names = append(names, n)
	}
	reg.mu.RUnlock()
	for _, n := range names {
		if reg.get(n).cancel(taskID) {
			found = true
			break
		}
	}
	if !found {
		jsonResponse(w, http.StatusNotFound, map[string]string{"error": "task not found"})
		return
	}
	slog.Info("task cancelled", "task_id", taskID)
	jsonResponse(w, http.StatusOK, map[string]string{"cancelled": taskID})
}

// healthHandler — GET /health
func healthHandler(w http.ResponseWriter, r *http.Request) {
	jsonResponse(w, http.StatusOK, map[string]string{
		"status":    "ok",
		"service":   "queue-service-go",
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	})
}

// ── Router ───────────────────────────────────────────────────────────────────

func router() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/queue/enqueue", enqueueHandler)
	mux.HandleFunc("/queue/dequeue", dequeueHandler)
	mux.HandleFunc("/queue/status", statusHandler)
	// All other /queue/ paths go to cancelHandler (DELETE /queue/{task_id})
	mux.HandleFunc("/queue/", cancelHandler)
	return mux
}

// ── Main ─────────────────────────────────────────────────────────────────────

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8027"
	}

	srv := &http.Server{
		Addr:         net.JoinHostPort("", port),
		Handler:      router(),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGTERM, syscall.SIGINT)

	go func() {
		slog.Info("queue-service-go starting", "port", port)
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
