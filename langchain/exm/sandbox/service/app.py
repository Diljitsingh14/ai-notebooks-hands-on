from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from redis import Redis
from rq import Queue
import uuid, os, json

app = FastAPI(title="AI Code Executor Service")
redis = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
q = Queue("jobs", connection=redis)

class JobIn(BaseModel):
    code: str
    requirements: list[str] | None = None
    env_vars: dict[str, str] | None = None
    network: bool = False
    timeout_sec: int = 120

@app.post("/submit")
def submit(job: JobIn):
    job_id = str(uuid.uuid4())
    rq_job = q.enqueue("service.worker.run_job", job.dict(), job_id=job_id)
    return {"job_id": job_id, "status": "queued"}

@app.get("/status/{job_id}")
def status(job_id: str):
    from rq.job import Job
    try:
        j = Job.fetch(job_id, connection=redis)
        return {"job_id": job_id, "status": j.get_status(), "result": j.result}
    except Exception:
        return {"job_id": job_id, "status": "unknown"}

# Server-Sent Events streaming
from fastapi import Request
from fastapi.responses import StreamingResponse

@app.get("/stream/{job_id}")
async def stream_logs(job_id: str, request: Request):
    def iter_logs():
        # tail logs in redis pubsub channel "logs:{job_id}"
        pubsub = redis.pubsub()
        pubsub.subscribe(f"logs:{job_id}")
        try:
            for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                line = msg["data"]
                if isinstance(line, bytes): line = line.decode("utf-8", "ignore")
                yield f"data: {line}\n\n"
        finally:
            pubsub.close()
    return StreamingResponse(iter_logs(), media_type="text/event-stream")
