# src/cloud/cost_optimizer.py

import os
from typing import Dict


class MultiCloudCostOptimizer:
    """
    Monitor and optimize costs across cloud providers $CITE_1
    """

    def __init__(self):
        self.aws_enabled = os.getenv("AWS_ENABLED", "true").lower() == "true"
        self.azure_enabled = os.getenv("AZURE_ENABLED", "true").lower() == "true"
        self.gcp_enabled = os.getenv("GCP_ENABLED", "true").lower() == "true"

    def get_cost_estimates(self) -> Dict[str, Dict]:
        """Get cost estimates for each cloud provider"""

        estimates = {}

        if self.aws_enabled:
            estimates["aws"] = self._estimate_eks_costs()

        if self.azure_enabled:
            estimates["azure"] = self._estimate_aks_costs()

        if self.gcp_enabled:
            estimates["gcp"] = self._estimate_gke_costs()

        return estimates

    def _estimate_eks_costs(self) -> Dict:
        """Estimate AWS EKS costs"""
        # t3.2xlarge: ~$0.33/hour
        # 5 nodes * 730 hours/month = $1,204.50
        # Data transfer: ~$100/month
        # EBS storage: ~$50/month

        return {
            "provider": "AWS EKS",
            "monthly_estimate": 1354.50,
            "breakdown": {"compute": 1204.50, "data_transfer": 100, "storage": 50},
            "recommendations": [
                "Use Reserved Instances for 30% savings",
                "Consider Spot Instances for non-critical workloads",
                "Enable auto-scaling to reduce idle capacity",
            ],
        }

    def _estimate_aks_costs(self) -> Dict:
        """Estimate Azure AKS costs (most cost-effective) $CITE_8"""
        # Standard_D4s_v3: ~$0.22/hour
        # 3 nodes * 730 hours/month = $482.40
        # Storage: ~$30/month
        # FREE cluster management

        return {
            "provider": "Azure AKS",
            "monthly_estimate": 512.40,
            "breakdown": {
                "compute": 482.40,
                "storage": 30,
                "cluster_management": 0,  # FREE
            },
            "recommendations": [
                "Most cost-effective option",
                "Use Reserved Instances for additional 30% savings",
                "Consider Spot VMs for batch processing",
            ],
        }

    def _estimate_gke_costs(self) -> Dict:
        """Estimate GCP GKE costs (high performance) $CITE_2"""
        # n2-standard-4: ~$0.19/hour
        # 5 nodes * 730 hours/month = $694.00
        # Storage: ~$50/month
        # Network: ~$30/month

        return {
            "provider": "GCP GKE",
            "monthly_estimate": 774.00,
            "breakdown": {"compute": 694.00, "storage": 50, "network": 30},
            "recommendations": [
                "Best performance per dollar",
                "Use Committed Use Discounts for 25% savings",
                "Consider Preemptible VMs for non-critical workloads",
            ],
        }

    def get_optimization_recommendations(self) -> Dict:
        """Get cost optimization recommendations"""

        estimates = self.get_cost_estimates()
        total_monthly = sum(e["monthly_estimate"] for e in estimates.values())

        return {
            "total_monthly_estimate": total_monthly,
            "breakdown_by_provider": estimates,
            "global_recommendations": [
                "Use multi-cloud strategy for redundancy",
                "Primary: GKE (best performance)",
                "Failover: AKS (most cost-effective)",
                "Disaster recovery: EKS (enterprise features)",
                "Implement auto-scaling on all clusters",
                "Use spot/preemptible instances for non-critical workloads",
                "Monitor and right-size instances monthly",
                "Consider reserved instances for 30% savings",
            ],
            "estimated_annual_cost": total_monthly * 12,
            "potential_savings_with_optimization": total_monthly * 0.35,  # 35% potential savings
        }
