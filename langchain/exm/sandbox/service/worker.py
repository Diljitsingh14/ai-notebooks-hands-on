import os
import shutil
from typing import Dict, List, Optional
from redis import Redis

from executor.docker_runner import run_code_in_sandbox

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def run_job(payload: Dict):
    code: str = payload["code"]
    requirements: Optional[List[str]] = payload.get("requirements")
    env_vars: Optional[Dict[str, str]] = payload.get("env_vars")
    network: bool = payload.get("network", False)
    timeout_sec: int = payload.get("timeout_sec", 120)

    # Real-time streaming: re-run with stream=True and publish to Redis channel
    gen = run_code_in_sandbox(
        code=code,
        requirements=requirements,
        env_vars=env_vars,
        network=network,
        timeout_sec=timeout_sec,
        stream=True,
    )

    out_dir, stdout, stderr = None, "", ""
    channel = f"logs:{os.environ.get('RQ_JOB_ID', 'unknown')}"
    for msg in gen:
        if isinstance(msg, tuple):
            out_dir, stdout, stderr = msg
        else:
            redis.publish(channel, msg)

    # Persist final artifact path somewhere (DB/object storage) if needed
    return {"out_dir": out_dir, "stdout": stdout, "stderr": stderr}
