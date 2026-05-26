// Package orchestrator implements the AeonMind gRPC Orchestrator Server.
//
// The orchestrator runs at Tier 1 and manages AI Complexes (Tier 3),
// Agents (Tier 4), and Bot Services (Tier 5). It provides entity
// lifecycle management, task dispatch, evolution, optimization,
// and sentinel broadcast capabilities.
//
// Custom Hierarchy:
//   AI    = The overarching ML/LLM Complex (Tier 3)
//   Agent = Lower-level autonomous AI (Tier 4)
//   Bot   = Stateless service worker/function (Tier 5)
package orchestrator

import (
	"context"
	"fmt"
	"io"
	"log"
	"sync"
	"sync/atomic"
	"time"

	pb "github.com/Trancendos/Tranc3/aeonmind/go/proto"
)

// ── Tier Constants ──────────────────────────────────────────────────────────

const (
	TierHuman        = 0
	TierOrchestrator = 1
	TierPrime        = 2
	TierAI           = 3
	TierAgent        = 4
	TierBot          = 5
)

// ── Entity Registry ─────────────────────────────────────────────────────────

// Entity represents a platform entity in the orchestrator's registry.
type Entity struct {
	ID         string
	Name       string
	EntityType pb.EntityType
	Tier       pb.Tier
	Status     pb.AgentStatus
	Config     map[string]string
	Metadata   map[string]string
	CreatedAt  time.Time
	UpdatedAt  time.Time
}

// OrchestratorServer implements the AeonMindOrchestrator gRPC service.
type OrchestratorServer struct {
	pb.UnimplementedAeonMindOrchestratorServer

	mu       sync.RWMutex
	entities map[string]*Entity
	version  string
	startTime time.Time

	// Sentinel channel subscribers
	subscribers map[pb.SentinelChannel]map[string]chan<- []byte

	// Metrics
	totalTasksDispatched atomic.Int64
	totalEvolutionRounds atomic.Int64
}

// NewOrchestratorServer creates a new orchestrator server instance.
func NewOrchestratorServer() *OrchestratorServer {
	return &OrchestratorServer{
		entities:    make(map[string]*Entity),
		version:     "0.9.0",
		startTime:   time.Now(),
		subscribers: make(map[pb.SentinelChannel]map[string]chan<- []byte),
	}
}

// ── Entity Management ───────────────────────────────────────────────────────

// CreateEntity creates a new platform entity.
func (s *OrchestratorServer) CreateEntity(ctx context.Context, req *pb.CreateEntityRequest) (*pb.CreateEntityResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	id := fmt.Sprintf("%s-%d", req.Name, time.Now().UnixNano())

	entity := &Entity{
		ID:         id,
		Name:       req.Name,
		EntityType: req.EntityType,
		Tier:       req.Tier,
		Status:     pb.AgentStatus_STATUS_IDLE,
		Config:     req.Config,
		Metadata:   make(map[string]string),
		CreatedAt:  time.Now(),
		UpdatedAt:  time.Now(),
	}

	s.entities[id] = entity

	log.Printf("[Orchestrator] Created entity: id=%s type=%v tier=%v name=%s",
		id, req.EntityType, req.Tier, req.Name)

	return &pb.CreateEntityResponse{
		EntityId: id,
		Success:  true,
		Message:  fmt.Sprintf("Entity %s created successfully", id),
	}, nil
}

// GetEntity retrieves an entity by ID.
func (s *OrchestratorServer) GetEntity(ctx context.Context, req *pb.GetEntityRequest) (*pb.GetEntityResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	entity, ok := s.entities[req.EntityId]
	if !ok {
		return &pb.GetEntityResponse{
			Found: false,
		}, nil
	}

	return &pb.GetEntityResponse{
		EntityType: entity.EntityType,
		Found:      true,
	}, nil
}

// ListEntities lists entities with optional filtering.
func (s *OrchestratorServer) ListEntities(ctx context.Context, req *pb.ListEntitiesRequest) (*pb.ListEntitiesResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var ids []string
	for id, entity := range s.entities {
		if req.EntityType != pb.EntityType_ENTITY_UNSPECIFIED && entity.EntityType != req.EntityType {
			continue
		}
		if req.Tier != pb.Tier_TIER_UNSPECIFIED && entity.Tier != req.Tier {
			continue
		}
		ids = append(ids, id)
	}

	return &pb.ListEntitiesResponse{
		EntityIds:  ids,
		TotalCount: int32(len(ids)),
	}, nil
}

// ── Task Dispatch ────────────────────────────────────────────────────────────

// DispatchTask dispatches a task to a specific entity.
func (s *OrchestratorServer) DispatchTask(ctx context.Context, req *pb.DispatchTaskRequest) (*pb.DispatchTaskResponse, error) {
	s.mu.RLock()
	entity, ok := s.entities[req.EntityId]
	s.mu.RUnlock()

	if !ok {
		return &pb.DispatchTaskResponse{
			Success: false,
			Message: fmt.Sprintf("Entity %s not found", req.EntityId),
		}, nil
	}

	taskID := fmt.Sprintf("task-%d", time.Now().UnixNano())
	s.totalTasksDispatched.Add(1)

	log.Printf("[Orchestrator] Dispatched task: task_id=%s entity=%s type=%s priority=%d",
		taskID, entity.Name, req.TaskType, req.Priority)

	return &pb.DispatchTaskResponse{
		TaskId:  taskID,
		Success: true,
		Message: fmt.Sprintf("Task %s dispatched to %s", taskID, entity.Name),
	}, nil
}

// DispatchBatch dispatches a batch of tasks.
func (s *OrchestratorServer) DispatchBatch(stream pb.AeonMindOrchestrator_DispatchBatchServer) error {
	var count int32
	for {
		req, err := stream.Recv()
		if err == io.EOF {
			return stream.SendAndClose(&pb.DispatchTaskResponse{
				TaskId:  fmt.Sprintf("batch-%d", time.Now().UnixNano()),
				Success: true,
				Message: fmt.Sprintf("Batch of %d tasks dispatched", count),
			})
		}
		if err != nil {
			return err
		}

		s.totalTasksDispatched.Add(1)
		count++

		if err := stream.Send(&pb.DispatchTaskResponse{
			TaskId:  fmt.Sprintf("batch-task-%d", count),
			Success: true,
			Message: fmt.Sprintf("Task %d dispatched", count),
		}); err != nil {
			return err
		}
	}
}

// ── Evolution & Optimization ────────────────────────────────────────────────

// EvolveAgent triggers evolution for an agent.
func (s *OrchestratorServer) EvolveAgent(ctx context.Context, req *pb.EvolveRequest) (*pb.EvolveResponse, error) {
	s.mu.RLock()
	_, ok := s.entities[req.AgentId]
	s.mu.RUnlock()

	if !ok {
		return &pb.EvolveResponse{
			Converged: false,
		}, fmt.Errorf("agent %s not found", req.AgentId)
	}

	s.totalEvolutionRounds.Add(1)

	log.Printf("[Orchestrator] Evolving agent: agent_id=%s generations=%d",
		req.AgentId, req.Generations)

	return &pb.EvolveResponse{
		BestFitness:          0.0,
		GenerationsCompleted: req.Generations,
		Converged:            false,
	}, nil
}

// OptimizeAgent triggers optimization for an agent.
func (s *OrchestratorServer) OptimizeAgent(ctx context.Context, req *pb.OptimizeRequest) (*pb.OptimizeResponse, error) {
	s.mu.RLock()
	_, ok := s.entities[req.AgentId]
	s.mu.RUnlock()

	if !ok {
		return &pb.OptimizeResponse{
			Converged: false,
		}, fmt.Errorf("agent %s not found", req.AgentId)
	}

	log.Printf("[Orchestrator] Optimizing agent: agent_id=%s max_steps=%d",
		req.AgentId, req.MaxSteps)

	return &pb.OptimizeResponse{
		FinalLoss:      0.0,
		StepsCompleted: req.MaxSteps,
		Converged:      false,
	}, nil
}

// ── Sentinel Broadcasting ───────────────────────────────────────────────────

// Broadcast sends a message to all subscribers of a channel.
func (s *OrchestratorServer) Broadcast(ctx context.Context, req *pb.BroadcastRequest) (*pb.BroadcastResponse, error) {
	s.mu.RLock()
	subs, ok := s.subscribers[req.Channel]
	s.mu.RUnlock()

	if !ok {
		return &pb.BroadcastResponse{
			Recipients: 0,
			Success:    true,
		}, nil
	}

	count := 0
	for id, ch := range subs {
		select {
		case ch <- req.Message:
			count++
		default:
			log.Printf("[Orchestrator] Channel full for subscriber %s on channel %v", id, req.Channel)
		}
	}

	log.Printf("[Orchestrator] Broadcast: channel=%v source=%s recipients=%d",
		req.Channel, req.SourceId, count)

	return &pb.BroadcastResponse{
		Recipients: int32(count),
		Success:    true,
	}, nil
}

// ── Health & Monitoring ─────────────────────────────────────────────────────

// HealthCheck returns the health status of the orchestrator.
func (s *OrchestratorServer) HealthCheck(ctx context.Context, req *pb.HealthCheckRequest) (*pb.HealthCheckResponse, error) {
	s.mu.RLock()
	totalAgents := 0
	totalBots := 0
	for _, entity := range s.entities {
		switch entity.EntityType {
		case pb.EntityType_ENTITY_AGENT:
			totalAgents++
		case pb.EntityType_ENTITY_BOT:
			totalBots++
		}
	}
	s.mu.RUnlock()

	return &pb.HealthCheckResponse{
		Healthy:        true,
		ActiveEntities: int32(len(s.entities)),
		TotalAgents:    int32(totalAgents),
		TotalBots:      int32(totalBots),
		UptimeSeconds:  time.Since(s.startTime).Seconds(),
		Version:        s.version,
	}, nil
}
