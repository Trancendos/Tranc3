/*
DNF Orchestrator — Distributed Nano-Flows
==========================================
Replaces cloud FaaS with local event loops and edge-worker patterns.
Avoids vendor lock-in and execution costs entirely.

Architecture:
  - Flow DAG: Directed Acyclic Graph of nano-steps
  - Event-driven: steps triggered by events, not HTTP calls
  - Local-first: runs on bare metal, k3s, or edge devices
  - Zero-cost: pure Go, no cloud dependencies
  - Adaptive: genetic algorithm optimizes flow routing (via genetic_optimizer)
  - Fluidic: flows can be rerouted, paused, merged at runtime
  - Gas: flows can expand to fill available compute or compress when constrained

Integration with NSA:
  - Each flow step is a nanoservice registered in NSA
  - Step communication via shared memory IPC
  - Orchestrator itself is a Tier-2 nanoservice

Integration with IGI:
  - Flow definitions stored as code in Forgejo
  - FluxCD ensures running flows match declared state
*/

package dnf

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"sync/atomic"
	"time"

	"github.com/google/uuid"
)

// ============================================================
// Core Types
// ============================================================

// FlowStatus represents the state of a flow execution
type FlowStatus string

const (
	FlowPending   FlowStatus = "pending"
	FlowRunning   FlowStatus = "running"
	FlowPaused    FlowStatus = "paused"
	FlowCompleted FlowStatus = "completed"
	FlowFailed    FlowStatus = "failed"
	FlowCancelled FlowStatus = "cancelled"
	FlowMerged    FlowStatus = "merged"  // Gas pattern: merged into another flow
)

// StepStatus represents the state of a flow step
type StepStatus string

const (
	StepIdle      StepStatus = "idle"
	StepRunning   StepStatus = "running"
	StepSuccess   StepStatus = "success"
	StepFailed    StepStatus = "failed"
	StepSkipped   StepStatus = "skipped"
	StepRetrying  StepStatus = "retrying"
)

// StepHandler is the function signature for flow step execution
type StepHandler func(ctx context.Context, input map[string]interface{}) (map[string]interface{}, error)

// ============================================================
// Flow Definition (DAG)
// ============================================================

// FlowStep defines a single step in a flow
type FlowStep struct {
	ID          string                 `json:"id"`
	Name        string                 `json:"name"`
	ServiceName string                 `json:"service_name"`  // NSA nanoservice name
	Capability  string                 `json:"capability"`    // Required capability
	TimeoutMs   int                    `json:"timeout_ms"`
	RetryCount  int                    `json:"retry_count"`
	RetryDelayMs int                  `json:"retry_delay_ms"`
	DependsOn   []string              `json:"depends_on"`    // Step IDs this depends on
	Condition   string                `json:"condition"`     // Optional: expression to evaluate
	Properties  map[string]interface{} `json:"properties"`
}

// FlowDefinition defines a complete flow DAG
type FlowDefinition struct {
	ID          string                 `json:"id"`
	Name        string                 `json:"name"`
	Version     string                 `json:"version"`
	Description string                 `json:"description"`
	Steps       []FlowStep             `json:"steps"`
	Tags        []string               `json:"tags"`
	Tier        int                    `json:"tier"`          // Tranc3 tier
	Properties  map[string]interface{} `json:"properties"`
	CreatedAt   time.Time              `json:"created_at"`
	UpdatedAt   time.Time              `json:"updated_at"`
}

// Validate checks the flow definition for errors
func (fd *FlowDefinition) Validate() error {
	if fd.ID == "" {
		return fmt.Errorf("flow definition must have an ID")
	}
	if len(fd.Steps) == 0 {
		return fmt.Errorf("flow must have at least one step")
	}

	// Check for duplicate step IDs
	stepIDs := make(map[string]bool)
	for _, step := range fd.Steps {
		if step.ID == "" {
			return fmt.Errorf("step must have an ID")
		}
		if stepIDs[step.ID] {
			return fmt.Errorf("duplicate step ID: %s", step.ID)
		}
		stepIDs[step.ID] = true
	}

	// Check dependency references
	for _, step := range fd.Steps {
		for _, dep := range step.DependsOn {
			if !stepIDs[dep] {
				return fmt.Errorf("step %s depends on unknown step %s", step.ID, dep)
			}
		}
	}

	// Check for cycles using DFS
	if err := fd.detectCycle(); err != nil {
		return err
	}

	return nil
}

func (fd *FlowDefinition) detectCycle() error {
	visited := make(map[string]bool)
	inStack := make(map[string]bool)

	var dfs func(stepID string) error
	dfs = func(stepID string) error {
		visited[stepID] = true
		inStack[stepID] = true

		for _, step := range fd.Steps {
			if step.ID == stepID {
				for _, dep := range step.DependsOn {
					if inStack[dep] {
						return fmt.Errorf("cycle detected: %s -> %s", stepID, dep)
					}
					if !visited[dep] {
						if err := dfs(dep); err != nil {
							return err
						}
					}
				}
			}
		}

		inStack[stepID] = false
		return nil
	}

	for _, step := range fd.Steps {
		if !visited[step.ID] {
			if err := dfs(step.ID); err != nil {
				return err
			}
		}
	}

	return nil
}

// GetRootSteps returns steps with no dependencies
func (fd *FlowDefinition) GetRootSteps() []FlowStep {
	var roots []FlowStep
	for _, step := range fd.Steps {
		if len(step.DependsOn) == 0 {
			roots = append(roots, step)
		}
	}
	return roots
}

// GetDependents returns steps that depend on the given step
func (fd *FlowDefinition) GetDependents(stepID string) []FlowStep {
	var dependents []FlowStep
	for _, step := range fd.Steps {
		for _, dep := range step.DependsOn {
			if dep == stepID {
				dependents = append(dependents, step)
				break
			}
		}
	}
	return dependents
}

// ============================================================
// Flow Execution
// ============================================================

// StepResult holds the result of a step execution
type StepResult struct {
	StepID    string                 `json:"step_id"`
	Status    StepStatus             `json:"status"`
	Output    map[string]interface{} `json:"output"`
	Error     string                 `json:"error,omitempty"`
	StartedAt time.Time              `json:"started_at"`
	EndedAt   time.Time              `json:"ended_at"`
	DurationMs int64                 `json:"duration_ms"`
	Retries   int                    `json:"retries"`
}

// FlowExecution represents a running flow instance
type FlowExecution struct {
	ID           string                `json:"id"`
	FlowID       string                `json:"flow_id"`
	FlowVersion  string                `json:"flow_version"`
	Status       FlowStatus            `json:"status"`
	StepResults  map[string]*StepResult `json:"step_results"`
	Input        map[string]interface{} `json:"input"`
	Output       map[string]interface{} `json:"output"`
	StartedAt    time.Time             `json:"started_at"`
	CompletedAt  *time.Time            `json:"completed_at,omitempty"`
	Error        string                `json:"error,omitempty"`
	ParentFlowID string                `json:"parent_flow_id,omitempty"` // For merged flows
}

// ============================================================
// Orchestrator
// ============================================================

// FlowEventHandler is called on flow lifecycle events
type FlowEventHandler func(event string, execution *FlowExecution)

// Orchestrator manages flow definitions and executions
type Orchestrator struct {
	definitions  map[string]*FlowDefinition
	executions   map[string]*FlowExecution
	handlers     map[string]StepHandler
	eventHandlers []FlowEventHandler
	mu           sync.RWMutex
	execCount    atomic.Int64
	failCount    atomic.Int64
	running      atomic.Bool
	workerPool   chan struct{} // Semaphore for concurrency control
}

// NewOrchestrator creates a new DNF orchestrator
func NewOrchestrator(maxConcurrentSteps int) *Orchestrator {
	if maxConcurrentSteps <= 0 {
		maxConcurrentSteps = 100
	}
	return &Orchestrator{
		definitions: make(map[string]*FlowDefinition),
		executions:  make(map[string]*FlowExecution),
		handlers:    make(map[string]StepHandler),
		workerPool:  make(chan struct{}, maxConcurrentSteps),
	}
}

// RegisterHandler registers a step handler function
func (o *Orchestrator) RegisterHandler(stepName string, handler StepHandler) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.handlers[stepName] = handler
}

// RegisterFlow registers a flow definition
func (o *Orchestrator) RegisterFlow(def *FlowDefinition) error {
	if err := def.Validate(); err != nil {
		return fmt.Errorf("invalid flow definition: %w", err)
	}
	o.mu.Lock()
	defer o.mu.Unlock()
	o.definitions[def.ID] = def
	log.Printf("[DNF] Registered flow: %s (%s) with %d steps", def.Name, def.ID, len(def.Steps))
	return nil
}

// OnEvent registers a flow lifecycle event handler
func (o *Orchestrator) OnEvent(handler FlowEventHandler) {
	o.eventHandlers = append(o.eventHandlers, handler)
}

// Execute starts a flow execution
func (o *Orchestrator) Execute(ctx context.Context, flowID string, input map[string]interface{}) (*FlowExecution, error) {
	o.mu.RLock()
	def, ok := o.definitions[flowID]
	o.mu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("flow not found: %s", flowID)
	}

	exec := &FlowExecution{
		ID:          uuid.New().String(),
		FlowID:      flowID,
		FlowVersion: def.Version,
		Status:      FlowPending,
		StepResults: make(map[string]*StepResult),
		Input:       input,
		Output:      make(map[string]interface{}),
		StartedAt:   time.Now(),
	}

	o.mu.Lock()
	o.executions[exec.ID] = exec
	o.mu.Unlock()

	o.emitEvent("started", exec)

	// Execute the flow DAG
	go o.executeFlow(ctx, def, exec)

	return exec, nil
}

// GetExecution returns an execution by ID
func (o *Orchestrator) GetExecution(execID string) (*FlowExecution, bool) {
	o.mu.RLock()
	defer o.mu.RUnlock()
	exec, ok := o.executions[execID]
	return exec, ok
}

// ListExecutions returns all executions
func (o *Orchestrator) ListExecutions() []*FlowExecution {
	o.mu.RLock()
	defer o.mu.RUnlock()
	result := make([]*FlowExecution, 0, len(o.executions))
	for _, exec := range o.executions {
		result = append(result, exec)
	}
	return result
}

// Pause pauses a running flow execution
func (o *Orchestrator) Pause(execID string) error {
	o.mu.Lock()
	defer o.mu.Unlock()
	exec, ok := o.executions[execID]
	if !ok {
		return fmt.Errorf("execution not found: %s", execID)
	}
	if exec.Status != FlowRunning {
		return fmt.Errorf("cannot pause flow in status: %s", exec.Status)
	}
	exec.Status = FlowPaused
	o.emitEvent("paused", exec)
	return nil
}

// Resume resumes a paused flow execution
func (o *Orchestrator) Resume(ctx context.Context, execID string) error {
	o.mu.RLock()
	exec, ok := o.executions[execID]
	o.mu.RUnlock()
	if !ok {
		return fmt.Errorf("execution not found: %s", execID)
	}
	if exec.Status != FlowPaused {
		return fmt.Errorf("cannot resume flow in status: %s", exec.Status)
	}
	def, ok := o.definitions[exec.FlowID]
	if !ok {
		return fmt.Errorf("flow definition not found: %s", exec.FlowID)
	}

	exec.Status = FlowRunning
	o.emitEvent("resumed", exec)
	go o.executeFlow(ctx, def, exec)
	return nil
}

// Cancel cancels a flow execution
func (o *Orchestrator) Cancel(execID string) error {
	o.mu.Lock()
	defer o.mu.Unlock()
	exec, ok := o.executions[execID]
	if !ok {
		return fmt.Errorf("execution not found: %s", execID)
	}
	exec.Status = FlowCancelled
	now := time.Now()
	exec.CompletedAt = &now
	o.emitEvent("cancelled", exec)
	return nil
}

// Merge merges two flow executions (Gas pattern — flows expand/contract)
func (o *Orchestrator) Merge(targetExecID, sourceExecID string) error {
	o.mu.Lock()
	defer o.mu.Unlock()

	target, ok := o.executions[targetExecID]
	if !ok {
		return fmt.Errorf("target execution not found: %s", targetExecID)
	}
	source, ok := o.executions[sourceExecID]
	if !ok {
		return fmt.Errorf("source execution not found: %s", sourceExecID)
	}

	// Merge step results from source into target
	for stepID, result := range source.StepResults {
		if _, exists := target.StepResults[stepID]; !exists {
			target.StepResults[stepID] = result
		}
	}

	// Merge output data
	for k, v := range source.Output {
		target.Output[k] = v
	}

	// Mark source as merged
	source.Status = FlowMerged
	source.ParentFlowID = targetExecID
	now := time.Now()
	source.CompletedAt = &now

	o.emitEvent("merged", target)
	return nil
}

// Stats returns orchestrator statistics
func (o *Orchestrator) Stats() map[string]interface{} {
	o.mu.RLock()
	defer o.mu.RUnlock()

	statusCounts := make(map[string]int)
	for _, exec := range o.executions {
		statusCounts[string(exec.Status)]++
	}

	return map[string]interface{}{
		"registered_flows":  len(o.definitions),
		"total_executions":  len(o.executions),
		"by_status":         statusCounts,
		"total_completed":   o.execCount.Load(),
		"total_failed":      o.failCount.Load(),
		"registered_handlers": len(o.handlers),
	}
}

// ============================================================
// Internal execution engine
// ============================================================

func (o *Orchestrator) executeFlow(ctx context.Context, def *FlowDefinition, exec *FlowExecution) {
	exec.Status = FlowRunning
	o.emitEvent("running", exec)

	// Topological sort for execution order
	order, err := o.topologicalSort(def)
	if err != nil {
		exec.Status = FlowFailed
		exec.Error = err.Error()
		now := time.Now()
		exec.CompletedAt = &now
		o.failCount.Add(1)
		o.emitEvent("failed", exec)
		return
	}

	// Execute steps in dependency order
	completed := make(map[string]bool)

	for len(completed) < len(def.Steps) {
		// Check for cancellation/pause
		if exec.Status == FlowCancelled || exec.Status == FlowPaused {
			return
		}

		// Find ready steps (all deps completed, not yet executed)
		var ready []FlowStep
		for _, step := range def.Steps {
			if completed[step.ID] {
				continue
			}
			if exec.StepResults[step.ID] != nil && exec.StepResults[step.ID].Status == StepRunning {
				continue
			}
			allDepsMet := true
			for _, dep := range step.DependsOn {
				if !completed[dep] {
					allDepsMet = false
					break
				}
				// Check if dependency failed
				if result, ok := exec.StepResults[dep]; ok && result.Status == StepFailed {
					// Skip this step if dependency failed
					exec.StepResults[step.ID] = &StepResult{
						StepID: step.ID,
						Status: StepSkipped,
						Error:  fmt.Sprintf("dependency %s failed", dep),
					}
					completed[step.ID] = true
					allDepsMet = false
					break
				}
			}
			if allDepsMet && !completed[step.ID] {
				ready = append(ready, step)
			}
		}

		if len(ready) == 0 {
			// Check if we're stuck
			if len(completed) < len(def.Steps) {
				remaining := len(def.Steps) - len(completed)
				// Check if all remaining are skipped/failed
				allDone := true
				for _, step := range def.Steps {
					if !completed[step.ID] {
						if result, ok := exec.StepResults[step.ID]; ok {
							if result.Status != StepRunning {
								completed[step.ID] = true
							} else {
								allDone = false
							}
						} else {
							allDone = false
						}
					}
				}
				if allDone {
					break
				}
				if remaining > 0 {
					time.Sleep(10 * time.Millisecond)
					continue
				}
			}
			break
		}

		// Execute ready steps concurrently
		var wg sync.WaitGroup
		for _, step := range ready {
			wg.Add(1)
			go func(s FlowStep) {
				defer wg.Done()
				o.executeStep(ctx, def, exec, s)
				completed[s.ID] = true
			}(step)
		}
		wg.Wait()
	}

	// Determine final status
	allSkipped := true
	for _, step := range def.Steps {
		if result, ok := exec.StepResults[step.ID]; ok {
			if result.Status == StepSuccess {
				allSkipped = false
			}
		}
	}

	if allSkipped && len(def.Steps) > 0 {
		exec.Status = FlowFailed
		exec.Error = "all steps were skipped or failed"
		o.failCount.Add(1)
	} else {
		exec.Status = FlowCompleted
		o.execCount.Add(1)
		// Collect output from terminal steps
		for _, step := range def.Steps {
			if result, ok := exec.StepResults[step.ID]; ok && result.Status == StepSuccess {
				for k, v := range result.Output {
					exec.Output[step.ID+"."+k] = v
				}
			}
		}
	}

	now := time.Now()
	exec.CompletedAt = &now
	o.emitEvent(string(exec.Status), exec)
}

func (o *Orchestrator) executeStep(ctx context.Context, def *FlowDefinition, exec *FlowExecution, step FlowStep) {
	// Mark as running
	result := &StepResult{
		StepID:    step.ID,
		Status:    StepRunning,
		StartedAt: time.Now(),
	}
	exec.StepResults[step.ID] = result

	// Get handler
	o.mu.RLock()
	handler, ok := o.handlers[step.Name]
	o.mu.RUnlock()

	if !ok {
		result.Status = StepFailed
		result.Error = fmt.Sprintf("no handler registered for step: %s", step.Name)
		result.EndedAt = time.Now()
		result.DurationMs = result.EndedAt.Sub(result.StartedAt).Milliseconds()
		return
	}

	// Execute with retry logic
	var lastErr error
	for attempt := 0; attempt <= step.RetryCount; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(step.RetryDelayMs) * time.Millisecond)
			result.Status = StepRetrying
			result.Retries = attempt
		}

		// Acquire worker slot
		o.workerPool <- struct{}{}

		stepCtx := ctx
		if step.TimeoutMs > 0 {
			var cancel context.CancelFunc
			stepCtx, cancel = context.WithTimeout(ctx, time.Duration(step.TimeoutMs)*time.Millisecond)
			defer cancel()
		}

		// Build input from dependency outputs
		input := make(map[string]interface{})
		for k, v := range exec.Input {
			input[k] = v
		}
		for _, depID := range step.DependsOn {
			if depResult, ok := exec.StepResults[depID]; ok && depResult.Status == StepSuccess {
				for k, v := range depResult.Output {
					input[depID+"."+k] = v
				}
			}
		}
		for k, v := range step.Properties {
			input[k] = v
		}

		output, err := handler(stepCtx, input)
		<-o.workerPool // Release worker slot

		if err != nil {
			lastErr = err
			result.Error = err.Error()
			continue
		}

		result.Output = output
		result.Status = StepSuccess
		result.Error = ""
		result.EndedAt = time.Now()
		result.DurationMs = result.EndedAt.Sub(result.StartedAt).Milliseconds()
		return
	}

	result.Status = StepFailed
	result.Error = fmt.Sprintf("after %d retries: %s", step.RetryCount, lastErr.Error())
	result.EndedAt = time.Now()
	result.DurationMs = result.EndedAt.Sub(result.StartedAt).Milliseconds()
}

func (o *Orchestrator) topologicalSort(def *FlowDefinition) ([]string, error) {
	inDegree := make(map[string]int)
	for _, step := range def.Steps {
		inDegree[step.ID] = len(step.DependsOn)
	}

	queue := make([]string, 0)
	for _, step := range def.Steps {
		if inDegree[step.ID] == 0 {
			queue = append(queue, step.ID)
		}
	}

	var order []string
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		order = append(order, current)

		for _, dep := range def.GetDependents(current) {
			inDegree[dep.ID]--
			if inDegree[dep.ID] == 0 {
				queue = append(queue, dep.ID)
			}
		}
	}

	if len(order) != len(def.Steps) {
		return nil, fmt.Errorf("cycle detected in flow DAG")
	}

	return order, nil
}

func (o *Orchestrator) emitEvent(event string, exec *FlowExecution) {
	for _, handler := range o.eventHandlers {
		func() {
			defer func() {
				if r := recover(); r != nil {
					log.Printf("[DNF] Event handler panic: %v", r)
				}
			}()
			handler(event, exec)
		}()
	}
}

// ============================================================
// Flow Registry — stores flow definitions
// ============================================================

// FlowRegistry manages flow definitions with versioning
type FlowRegistry struct {
	flows   map[string]map[string]*FlowDefinition // flowID -> version -> def
	latest  map[string]string                      // flowID -> latest version
	mu      sync.RWMutex
}

// NewFlowRegistry creates a new flow registry
func NewFlowRegistry() *FlowRegistry {
	return &FlowRegistry{
		flows:  make(map[string]map[string]*FlowDefinition),
		latest: make(map[string]string),
	}
}

// Put stores a flow definition
func (fr *FlowRegistry) Put(def *FlowDefinition) {
	fr.mu.Lock()
	defer fr.mu.Unlock()

	if _, ok := fr.flows[def.ID]; !ok {
		fr.flows[def.ID] = make(map[string]*FlowDefinition)
	}
	fr.flows[def.ID][def.Version] = def
	fr.latest[def.ID] = def.Version
}

// Get retrieves a specific version of a flow
func (fr *FlowRegistry) Get(flowID, version string) (*FlowDefinition, bool) {
	fr.mu.RLock()
	defer fr.mu.RUnlock()

	versions, ok := fr.flows[flowID]
	if !ok {
		return nil, false
	}
	def, ok := versions[version]
	return def, ok
}

// GetLatest retrieves the latest version of a flow
func (fr *FlowRegistry) GetLatest(flowID string) (*FlowDefinition, bool) {
	fr.mu.RLock()
	defer fr.mu.RUnlock()

	version, ok := fr.latest[flowID]
	if !ok {
		return nil, false
	}
	return fr.flows[flowID][version], true
}

// List returns all flow IDs
func (fr *FlowRegistry) List() []string {
	fr.mu.RLock()
	defer fr.mu.RUnlock()

	result := make([]string, 0, len(fr.flows))
	for id := range fr.flows {
		result = append(result, id)
	}
	return result
}

// Serialize serializes a flow definition to JSON
func (fr *FlowRegistry) Serialize(def *FlowDefinition) ([]byte, error) {
	return json.MarshalIndent(def, "", "  ")
}

// Deserialize deserializes a flow definition from JSON
func (fr *FlowRegistry) Deserialize(data []byte) (*FlowDefinition, error) {
	var def FlowDefinition
	if err := json.Unmarshal(data, &def); err != nil {
		return nil, fmt.Errorf("deserialize flow: %w", err)
	}
	if err := def.Validate(); err != nil {
		return nil, fmt.Errorf("invalid flow: %w", err)
	}
	return &def, nil
}
