"""Explicitly-started optional Temporal worker, no automatic cloud/network setup."""
from __future__ import annotations

import asyncio
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
    if not client_config.get("target_host"):
        raise RuntimeError("Temporal target_host is required")
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
