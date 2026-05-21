# TSK-004 Enhancement: ML + MCP + Workflow Phase4 Bridge

## Branch: enhancement/ml-mcp-workflow-phase4-bridge

### Phase A: New Spark MCP Tools (src/mcp/spark_phase4_tools.py)
- [ ] neural_mesh_emit — emit signals through NeuralMesh
- [ ] neural_mesh_topology — get mesh topology snapshot
- [ ] collective_memory_store — store entry in CollectiveMemory
- [ ] collective_memory_query — query CollectiveMemory by topic/tag
- [ ] meta_learn_adapt — adapt task parameters via MetaLearner
- [ ] attention_route — route request via AttentionRouter
- [ ] causal_predict — predict effects via CausalReasoner
- [ ] causal_diagnose — diagnose causes via CausalReasoner
- [ ] causal_counterfactual — run counterfactual query
- [ ] knowledge_graph_query — query SemanticKnowledgeGraph nodes
- [ ] knowledge_graph_path — find shortest path in knowledge graph
- [ ] knowledge_graph_expand — semantic expand from a node
- [ ] foresight_predict — use AdaptiveForesight for trajectory prediction
- [ ] analytics_intent — predict user intent via IntentPredictor
- [ ] nanobot_dispatch — dispatch NanoCode repair bots
- [ ] Register all new tools into SparkToolRegistry

### Phase B: New Workflow Nodes (src/workflow/phase4_nodes.py)
- [ ] NeuralMeshNode — emit/receive signals in workflows
- [ ] CollectiveMemoryNode — store/retrieve from shared memory
- [ ] MetaLearnNode — adapt parameters mid-workflow
- [ ] AttentionRouteNode — select optimal service in workflow
- [ ] CausalReasonNode — causal inference step in workflow
- [ ] KnowledgeGraphNode — structured knowledge lookup in workflow
- [ ] ForesightNode — predictive branching in workflow
- [ ] Register all nodes in create_node() factory

### Phase C: ML Pipeline Enhancements (src/core/ml_pipeline.py)
- [ ] MLPipeline class — unified inference orchestration
- [ ] Integrate AttentionRouter for model selection
- [ ] Integrate MetaLearner for few-shot task adaptation
- [ ] Integrate CollectiveMemory for cross-request context
- [ ] 5-tier inference with Phase4 intelligence routing

### Phase D: Integration & Registration
- [ ] Wire spark_phase4_tools.py into src/mcp/tools.py (import + call register)
- [ ] Wire phase4_nodes.py into src/workflow/nodes.py create_node()
- [ ] Add ml_pipeline.py import to src/core/__init__.py
- [ ] Commit all changes
- [ ] Push branch
- [ ] Create PR targeting claude/enhance-ml-mcp-workflow-LYXkX
