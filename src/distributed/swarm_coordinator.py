# src/core/swarm_coordination.py

import logging

logger = logging.getLogger("src.distributed.swarm_coordinator")

import asyncio  # noqa: E402
from typing import Any, Dict, List, Optional  # noqa: E402

import aiohttp  # noqa: E402

from Dimensional.sanitize import sanitize_for_log  # noqa: E402
from src.core.feature_flags import FeatureFlag, FeatureFlagManager  # noqa: E402


class SwarmCoordinator:
    """
    Coordinate distributed AI swarm for enhanced reasoning
    """

    def __init__(self, config, feature_manager: FeatureFlagManager):
        self.config = config
        self.feature_manager = feature_manager
        self.swarm_nodes = config.get("swarm_nodes", [])
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def swarm_reasoning(
        self, problem: Dict[str, Any], user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Distributed reasoning across swarm nodes
        """
        if not self.feature_manager.is_enabled(FeatureFlag.SWARM_INTELLIGENCE, user_id):
            return None

        if not self.swarm_nodes:
            return None

        try:
            return await self._coordinate_swarm(problem)
        except Exception as e:
            logger.warning("Swarm reasoning failed: %s", sanitize_for_log(e))
            return None

    async def _coordinate_swarm(self, problem: Dict[str, Any]) -> Dict[str, Any]:
        """Coordinate reasoning across swarm"""

        # Decompose problem
        sub_problems = self._decompose_problem(problem)

        # Distribute to nodes
        tasks = []
        for i, sub_problem in enumerate(sub_problems):
            node_url = self.swarm_nodes[i % len(self.swarm_nodes)]
            tasks.append(self._query_node(node_url, sub_problem))

        # Gather results
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter successful results
        valid_results = [r for r in results if not isinstance(r, Exception)]

        if not valid_results:
            raise Exception("No valid swarm responses")

        # Consensus aggregation
        consensus = self._swarm_consensus(valid_results)  # type: ignore[arg-type]

        return {
            "swarm_response": consensus,
            "node_count": len(valid_results),
            "confidence": len(valid_results) / len(self.swarm_nodes),
        }

    async def _query_node(self, node_url: str, sub_problem: Dict[str, Any]) -> Dict[str, Any]:
        """Query individual swarm node"""
        assert self.session is not None  # noqa: S101 — session is set by __aenter__
        async with self.session.post(
            f"{node_url}/reason",
            json=sub_problem,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            return await response.json()

    def _decompose_problem(self, problem: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Decompose complex problem into sub-problems"""
        message = problem.get("message", "")

        # Simple decomposition by sentences
        sentences = message.split(".")

        sub_problems = []
        for sentence in sentences:
            if sentence.strip():
                sub_problems.append({"message": sentence.strip(), "context": problem})

        return sub_problems[: len(self.swarm_nodes)]  # Limit to available nodes

    def _swarm_consensus(self, results: List[Dict[str, Any]]) -> str:
        """Aggregate swarm responses using consensus"""

        # Simple majority voting for text responses
        responses = [r.get("response", "") for r in results]

        # Count frequencies
        from collections import Counter

        response_counts = Counter(responses)

        # Return most common response
        most_common = response_counts.most_common(1)
        return most_common[0][0] if most_common else "Swarm consensus failed"

    async def update_swarm_nodes(self, new_nodes: List[str]):
        """Dynamically update swarm node list"""
        self.swarm_nodes = new_nodes

        # Health check nodes
        health_tasks = [self._check_node_health(node) for node in new_nodes]
        health_results = await asyncio.gather(*health_tasks, return_exceptions=True)

        # Keep only healthy nodes
        self.swarm_nodes = [
            node
            for node, health in zip(new_nodes, health_results, strict=False)
            if not isinstance(health, Exception)
            and isinstance(health, dict)
            and health.get("status") == "healthy"
        ]

    async def _check_node_health(self, node_url: str) -> Dict[str, Any]:
        """Check health of swarm node"""
        try:
            assert self.session is not None  # noqa: S101 — session is set by __aenter__
            async with self.session.get(
                f"{node_url}/health", timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                return await response.json()
        except Exception:
            return {"status": "unhealthy"}
