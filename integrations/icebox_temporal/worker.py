"""Explicitly-started optional Temporal worker, no automatic cloud/network setup."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.envconfig import ClientConfig
from temporalio.worker import Worker

from integrations.icebox_temporal.activities import evaluate_scan_policy

TASK_QUEUE = "icebox-metadata-policy-v1"


async def main() -> None:
    # Server identity and credentials come from Temporal SDK deployment config.
    # Do not put sample bytes or sensitive details in Temporal event history.
    client_config = ClientConfig.load_client_connect_config()
    # Reuse The Digital Grid's existing TEMPORAL_HOST configuration where set.
    # A missing target still fails closed; this adapter never starts a cluster.
    if not client_config.get("target_host") and os.getenv("TEMPORAL_HOST"):
        client_config["target_host"] = os.environ["TEMPORAL_HOST"]
    if not client_config.get("target_host"):
        raise RuntimeError("Temporal target_host or TEMPORAL_HOST is required")
    client = await Client.connect(**client_config)
    with ThreadPoolExecutor(max_workers=4) as executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            activities=[evaluate_scan_policy],
            activity_executor=executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
