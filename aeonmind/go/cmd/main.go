// AeonMind gRPC Orchestrator — Go Entry Point
//
// Starts the AeonMind gRPC server for the Tranc3 Infinity Ecosystem.
// The orchestrator manages AI Complexes (Tier 3), Agents (Tier 4),
// and Bot Services (Tier 5) via gRPC protocol.
package main

import (
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"

	pb "github.com/Trancendos/Tranc3/aeonmind/go/proto"
	"github.com/Trancendos/Tranc3/aeonmind/go/orchestrator"
)

func main() {
	port := os.Getenv("AEONMIND_PORT")
	if port == "" {
		port = "50051"
	}

	lis, err := net.Listen("tcp", fmt.Sprintf(":%s", port))
	if err != nil {
		log.Fatalf("[AeonMind] Failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(64 * 1024 * 1024),
		grpc.MaxSendMsgSize(64 * 1024 * 1024),
	)

	orchestratorServer := orchestrator.NewOrchestratorServer()
	pb.RegisterAeonMindOrchestratorServer(grpcServer, orchestratorServer)

	// Enable server reflection for debugging
	reflection.Register(grpcServer)

	// Graceful shutdown
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-sigCh
		log.Println("[AeonMind] Received shutdown signal, gracefully stopping...")
		grpcServer.GracefulStop()
	}()

	log.Printf("╔══════════════════════════════════════════════════╗")
	log.Printf("║  AeonMind gRPC Orchestrator v0.9.0              ║")
	log.Printf("║  Tranc3 Infinity Ecosystem                      ║")
	log.Printf("║  Tier 1 — Logical Orchestrator                  ║")
	log.Printf("╠══════════════════════════════════════════════════╣")
	log.Printf("║  Listening on: :%-30s ║", port)
	log.Printf("║  Hierarchy:                                     ║")
	log.Printf("║    T3  AI    = ML/LLM Complex                   ║")
	log.Printf("║    T4  Agent = Autonomous AI                    ║")
	log.Printf("║    T5  Bot   = Stateless Worker                 ║")
	log.Printf("╚══════════════════════════════════════════════════╝")

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("[AeonMind] Failed to serve: %v", err)
	}
}
