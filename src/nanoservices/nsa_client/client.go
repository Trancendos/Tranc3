/*
NSA Client — Go Nanoservice Client Library
===========================================
Shared-memory IPC client compatible with the Rust NSA Broker.
Uses /dev/shm for zero-copy message passing between nanoservices.

Architecture:
  - Ring buffer protocol matching the Rust broker's memory layout
  - Slot-based messaging: 64 slots × 1024 bytes per segment
  - Atomic headers for lock-free concurrent access
  - HTTP discovery via the NSA Broker REST API (port 7780)

Integration:
  - Compatible with Rust NSA Broker's shared memory format
  - HTTP client for service registry queries
  - Event-driven message processing with goroutines
*/

package nsaclient

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"
	"unsafe"

	"github.com/google/uuid"
)

// Constants matching the Rust NSA Broker
const (
	SHMDir           = "/dev/shm"
	SHMPrefix        = "nsa_"
	DefaultSegSize   = 65536
	RingBufferSlots  = 64
	SlotSize         = 1024
	SlotHeaderSize   = 24
	HTTPPort         = 7780
	PollIntervalMs   = 1
)

// SlotHeader matches the Rust repr(C) SlotHeader struct
type SlotHeader struct {
	Occupied int32   // AtomicBool — 0=false, 1=true
	_        int32   // padding
	Sequence uint64  // AtomicU64
	Length   uint32  // u32
	_        uint32  // padding
}

// IPCMessage represents a nanoservice IPC message
type IPCMessage struct {
	ID        string                 `json:"id"`
	Source    string                 `json:"source"`
	Target    string                 `json:"target"`
	Type      string                 `json:"type"` // request, response, event, command, heartbeat, error
	Payload   map[string]interface{} `json:"payload"`
	Timestamp float64                `json:"timestamp"`
	Priority  int                    `json:"priority"`
	TTLMs     int                    `json:"ttl_ms"`
}

// ServiceStatus represents nanoservice status
type ServiceStatus string

const (
	StatusStarting  ServiceStatus = "starting"
	StatusReady     ServiceStatus = "ready"
	StatusBusy      ServiceStatus = "busy"
	StatusDegraded  ServiceStatus = "degraded"
	StatusOffline   ServiceStatus = "offline"
)

// NanoserviceRecord represents a registered service
type NanoserviceRecord struct {
	ID           string        `json:"id"`
	Name         string        `json:"name"`
	Tier         int           `json:"tier"`
	PID          int           `json:"pid"`
	SHMSegment   string        `json:"shm_segment"`
	Status       ServiceStatus `json:"status"`
	MessageCount int           `json:"message_count"`
	ErrorCount   int           `json:"error_count"`
}

// MessageHandler is a callback for incoming messages
type MessageHandler func(msg IPCMessage)

// ShmRingBuffer provides shared-memory ring buffer access
type ShmRingBuffer struct {
	segmentName string
	file        *os.File
	data        []byte
	writeSlot   uint64
	readSlot    uint64
	mu          sync.Mutex
}

// NewShmRingBuffer creates or opens a shared memory ring buffer
func NewShmRingBuffer(segmentName string, create bool) (*ShmRingBuffer, error) {
	path := fmt.Sprintf("%s/%s%s", SHMDir, SHMPrefix, segmentName)

	var file *os.File
	var err error

	if create {
		file, err = os.OpenFile(path, os.O_RDWR|os.O_CREATE, 0666)
		if err != nil {
			return nil, fmt.Errorf("create shm segment: %w", err)
		}
		// Size the file
		totalSize := RingBufferSlots * SlotSize
		if err := file.Truncate(int64(totalSize)); err != nil {
			file.Close()
			return nil, fmt.Errorf("truncate shm segment: %w", err)
		}
	} else {
		file, err = os.OpenFile(path, os.O_RDWR, 0)
		if err != nil {
			return nil, fmt.Errorf("open shm segment: %w", err)
		}
	}

	data := make([]byte, RingBufferSlots*SlotSize)
	if _, err := file.Read(data); err != nil && err != io.EOF {
		file.Close()
		return nil, fmt.Errorf("read shm segment: %w", err)
	}

	return &ShmRingBuffer{
		segmentName: segmentName,
		file:        file,
		data:        data,
		writeSlot:   0,
		readSlot:    0,
	}, nil
}

// WriteMessage writes a message to the next available slot
func (rb *ShmRingBuffer) WriteMessage(msg IPCMessage) error {
	rb.mu.Lock()
	defer rb.mu.Unlock()

	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("marshal message: %w", err)
	}

	if len(data) > SlotSize-SlotHeaderSize {
		return fmt.Errorf("message too large: %d > %d", len(data), SlotSize-SlotHeaderSize)
	}

	slotOffset := int(rb.writeSlot) * SlotSize
	headerOffset := slotOffset

	// Write header
	header := (*SlotHeader)(unsafe.Pointer(&rb.data[headerOffset]))
	atomic.StoreInt32(&header.Occupied, 1)
	atomic.AddUint64(&header.Sequence, 1)
	header.Length = uint32(len(data))

	// Write payload
	copy(rb.data[slotOffset+SlotHeaderSize:], data)

	// Advance write pointer
	rb.writeSlot = (rb.writeSlot + 1) % RingBufferSlots

	// Write back to file
	if _, err := rb.file.WriteAt(rb.data[slotOffset:slotOffset+SlotSize], int64(slotOffset)); err != nil {
		return fmt.Errorf("write to shm: %w", err)
	}

	return nil
}

// ReadMessage reads a message from the current read slot
func (rb *ShmRingBuffer) ReadMessage() (*IPCMessage, error) {
	rb.mu.Lock()
	defer rb.mu.Unlock()

	slotOffset := int(rb.readSlot) * SlotSize
	header := (*SlotHeader)(unsafe.Pointer(&rb.data[slotOffset]))

	if atomic.LoadInt32(&header.Occupied) == 0 {
		return nil, nil // No message
	}

	length := header.Length
	if length == 0 || length > SlotSize-SlotHeaderSize {
		return nil, fmt.Errorf("invalid slot length: %d", length)
	}

	payload := make([]byte, length)
	copy(payload, rb.data[slotOffset+SlotHeaderSize:slotOffset+SlotHeaderSize+int(length)])

	var msg IPCMessage
	if err := json.Unmarshal(payload, &msg); err != nil {
		return nil, fmt.Errorf("unmarshal message: %w", err)
	}

	// Mark as read
	atomic.StoreInt32(&header.Occupied, 0)
	rb.readSlot = (rb.readSlot + 1) % RingBufferSlots

	return &msg, nil
}

// Close releases the shared memory segment
func (rb *ShmRingBuffer) Close() error {
	if rb.file != nil {
		return rb.file.Close()
	}
	return nil
}

// OccupiedCount returns the number of occupied slots
func (rb *ShmRingBuffer) OccupiedCount() int {
	count := 0
	for i := 0; i < RingBufferSlots; i++ {
		offset := i * SlotSize
		header := (*SlotHeader)(unsafe.Pointer(&rb.data[offset]))
		if atomic.LoadInt32(&header.Occupied) == 1 {
			count++
		}
	}
	return count
}

// NanoserviceClient is the Go client for the NSA ecosystem
type NanoserviceClient struct {
	serviceName string
	serviceID   string
	tier        int
	brokerURL   string
	shm         *ShmRingBuffer
	handlers    map[string][]MessageHandler
	running     atomic.Bool
	cancel      context.CancelFunc
	wg          sync.WaitGroup
	msgCount    atomic.Int64
	errCount    atomic.Int64
	httpClient  *http.Client
}

// NewNanoserviceClient creates a new nanoservice client
func NewNanoserviceClient(serviceName string, tier int, brokerURL string) *NanoserviceClient {
	if brokerURL == "" {
		brokerURL = fmt.Sprintf("http://localhost:%d", HTTPPort)
	}
	return &NanoserviceClient{
		serviceName: serviceName,
		serviceID:   fmt.Sprintf("%s_%s", serviceName, uuid.New().String()[:8]),
		tier:        tier,
		brokerURL:   brokerURL,
		handlers:    make(map[string][]MessageHandler),
		httpClient:  &http.Client{Timeout: 5 * time.Second},
	}
}

// Start initializes the client and begins message processing
func (c *NanoserviceClient) Start() error {
	// Create shared memory segment
	shm, err := NewShmRingBuffer(c.serviceName, true)
	if err != nil {
		return fmt.Errorf("create shm: %w", err)
	}
	c.shm = shm

	ctx, cancel := context.WithCancel(context.Background())
	c.cancel = cancel
	c.running.Store(true)

	// Start message polling goroutine
	c.wg.Add(1)
	go c.pollMessages(ctx)

	return nil
}

// Stop gracefully shuts down the client
func (c *NanoserviceClient) Stop() error {
	c.running.Store(false)
	if c.cancel != nil {
		c.cancel()
	}
	c.wg.Wait()
	if c.shm != nil {
		return c.shm.Close()
	}
	return nil
}

// Send sends a message to a target nanoservice
func (c *NanoserviceClient) Send(target string, msgType string, payload map[string]interface{}) error {
	msg := IPCMessage{
		ID:        uuid.New().String(),
		Source:    c.serviceID,
		Target:    target,
		Type:      msgType,
		Payload:   payload,
		Timestamp: float64(time.Now().UnixMilli()),
		Priority:  0,
		TTLMs:     30000,
	}

	// Write to target's SHM segment
	targetShm, err := NewShmRingBuffer(target, false)
	if err != nil {
		return fmt.Errorf("open target shm %s: %w", target, err)
	}
	defer targetShm.Close()

	if err := targetShm.WriteMessage(msg); err != nil {
		return fmt.Errorf("write to target: %w", err)
	}

	c.msgCount.Add(1)
	return nil
}

// On registers a handler for a message type
func (c *NanoserviceClient) On(msgType string, handler MessageHandler) {
	c.handlers[msgType] = append(c.handlers[msgType], handler)
}

// Stats returns client statistics
func (c *NanoserviceClient) Stats() map[string]interface{} {
	return map[string]interface{}{
		"service_id":    c.serviceID,
		"service_name":  c.serviceName,
		"tier":          c.tier,
		"running":       c.running.Load(),
		"msg_count":     c.msgCount.Load(),
		"error_count":   c.errCount.Load(),
	}
}

// ListServices queries the broker for registered services
func (c *NanoserviceClient) ListServices() ([]NanoserviceRecord, error) {
	resp, err := c.httpClient.Get(fmt.Sprintf("%s/services", c.brokerURL))
	if err != nil {
		return nil, fmt.Errorf("list services: %w", err)
	}
	defer resp.Body.Close()

	var services []NanoserviceRecord
	if err := json.NewDecoder(resp.Body).Decode(&services); err != nil {
		return nil, fmt.Errorf("decode services: %w", err)
	}
	return services, nil
}

// Health queries the broker health
func (c *NanoserviceClient) Health() (map[string]interface{}, error) {
	resp, err := c.httpClient.Get(fmt.Sprintf("%s/health", c.brokerURL))
	if err != nil {
		return nil, fmt.Errorf("health check: %w", err)
	}
	defer resp.Body.Close()

	var health map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&health); err != nil {
		return nil, fmt.Errorf("decode health: %w", err)
	}
	return health, nil
}

func (c *NanoserviceClient) pollMessages(ctx context.Context) {
	defer c.wg.Done()

	ticker := time.NewTicker(time.Duration(PollIntervalMs) * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if !c.running.Load() {
				return
			}
			msg, err := c.shm.ReadMessage()
			if err != nil {
				c.errCount.Add(1)
				continue
			}
			if msg != nil {
				c.dispatchMessage(*msg)
			}
		}
	}
}

func (c *NanoserviceClient) dispatchMessage(msg IPCMessage) {
	handlers, ok := c.handlers[msg.Type]
	if !ok {
		// Try wildcard handlers
		handlers = c.handlers["*"]
	}
	for _, handler := range handlers {
		func() {
			defer func() {
				if r := recover(); r != nil {
					c.errCount.Add(1)
				}
			}()
			handler(msg)
		}()
	}
}
