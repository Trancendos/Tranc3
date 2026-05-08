# src/cloud/federation_controller.py

import asyncio
import aiohttp
import os
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class MultiCloudFederationController:
    """
    Manage TRANC3 across multiple cloud providers
    Handles failover, load balancing, and health monitoring
    """

    def __init__(self):
        self.primary_cluster = os.getenv("PRIMARY_CLUSTER", "gke-us-central1")
        self.failover_clusters = os.getenv("FAILOVER_CLUSTERS", "aks-eastus,eks-us-east-1").split(",")
        self.all_clusters = [self.primary_cluster] + self.failover_clusters
        
        self.cluster_health = {}
        self.session = None
        self.health_check_interval = 30  # seconds
        
        # Initialize health status
        for cluster in self.all_clusters:
            self.cluster_health[cluster] = {
                'status': 'unknown',
                'last_check': None,
                'consecutive_failures': 0,
                'endpoint': self._get_cluster_endpoint(cluster)
            }

    async def start(self):
        """Start federation controller"""
        self.session = aiohttp.ClientSession()
        
        # Start health monitoring
        asyncio.create_task(self._health_monitor_loop())
        
        logger.info(f"Federation controller started. Primary: {self.primary_cluster}")

    async def stop(self):
        """Stop federation controller"""
        if self.session:
            await self.session.close()

    async def _health_monitor_loop(self):
        """Continuously monitor cluster health"""
        while True:
            try:
                await self._check_all_clusters()
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(5)

    async def _check_all_clusters(self):
        """Check health of all clusters"""
        tasks = [self._check_cluster_health(cluster) for cluster in self.all_clusters]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_cluster_health(self, cluster: str):
        """Check individual cluster health"""
        endpoint = self.cluster_health[cluster]['endpoint']
        
        try:
            async with self.session.get(
                f"{endpoint}/health",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.cluster_health[cluster]['status'] = 'healthy'
                    self.cluster_health[cluster]['consecutive_failures'] = 0
                    logger.info(f"✓ {cluster} is healthy")
                else:
                    self._mark_unhealthy(cluster)
        except Exception as e:
            logger.warning(f"Health check failed for {cluster}: {e}")
            self._mark_unhealthy(cluster)

    def _mark_unhealthy(self, cluster: str):
        """Mark cluster as unhealthy"""
        self.cluster_health[cluster]['consecutive_failures'] += 1
        
        if self.cluster_health[cluster]['consecutive_failures'] >= 3:
            self.cluster_health[cluster]['status'] = 'unhealthy'
            logger.error(f"✗ {cluster} marked as UNHEALTHY")
            
            # Trigger failover if primary
            if cluster == self.primary_cluster:
                asyncio.create_task(self._trigger_failover())

    async def _trigger_failover(self):
        """Failover to secondary cluster"""
        logger.critical("🚨 PRIMARY CLUSTER FAILED - INITIATING FAILOVER")
        
        # Find healthy failover cluster
        for cluster in self.failover_clusters:
            if self.cluster_health[cluster]['status'] == 'healthy':
                logger.info(f"Failing over to: {cluster}")
                self.primary_cluster = cluster
                
                # Update DNS/routing
                await self._update_global_routing(cluster)
                break

    async def _update_global_routing(self, new_primary: str):
        """Update global DNS/routing to new primary"""
        logger.info(f"Updating routing to {new_primary}")
        # Implementation depends on DNS provider (Route53, Cloud DNS, etc.)

    def _get_cluster_endpoint(self, cluster: str) -> str:
        """Get endpoint for cluster"""
        endpoints = {
            'gke-us-central1': 'http://tranc3-api.tranc3.svc.cluster.local',
            'aks-eastus': 'http://tranc3-api.tranc3.svc.cluster.local',
            'eks-us-east-1': 'http://tranc3-api.tranc3.svc.cluster.local'
        }
        return endpoints.get(cluster, 'http://localhost:8000')

    def get_status(self) -> Dict:
        """Get federation status"""
        return {
            'primary_cluster': self.primary_cluster,
            'clusters': self.cluster_health,
            'timestamp': datetime.utcnow().isoformat()
        }

    async def route_request(self, request_data: Dict) -> Dict:
        """Route request to appropriate cluster"""
        
        # Try primary first
        if self.cluster_health[self.primary_cluster]['status'] == 'healthy':
            return await self._send_to_cluster(self.primary_cluster, request_data)
        
        # Fallback to healthy failover clusters
        for cluster in self.failover_clusters:
            if self.cluster_health[cluster]['status'] == 'healthy':
                logger.warning(f"Primary unavailable, routing to {cluster}")
                return await self._send_to_cluster(cluster, request_data)
        
        raise Exception("No healthy clusters available")

    async def _send_to_cluster(self, cluster: str, request_data: Dict) -> Dict:
        """Send request to specific cluster"""
        endpoint = self.cluster_health[cluster]['endpoint']
        
        try:
            async with self.session.post(
                f"{endpoint}/chat",
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"Request to {cluster} failed: {e}")
            raise

# Global federation controller instance
federation_controller = None

async def init_federation():
    """Initialize federation controller"""
    global federation_controller
    federation_controller = MultiCloudFederationController()
    await federation_controller.start()

async def shutdown_federation():
    """Shutdown federation controller"""
    if federation_controller:
        await federation_controller.stop()