from langchain.tools import BaseTool
from typing import Optional, List, Dict, Any, Union, Tuple
from .docker_runner import run_code_in_sandbox

class AICodeExecutorTool(BaseTool):
    # super.name = "ai_code_executor"
    description = (
        "Runs trusted or AI-generated Python code in an isolated Docker sandbox. "
        "Accepts code, optional requirements (list of pip packages), and optional env vars. "
        "Returns path to output directory with logs and artifacts."
    )

    def _run(
        self,
        code: str,
        requirements: Optional[List[str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        network: bool = False,
        timeout_sec: int = 120,
    ) -> str:
        out_dir, stdout, stderr = run_code_in_sandbox(
            code=code,
            requirements=requirements,
            env_vars=env_vars,
            network=network,
            timeout_sec=timeout_sec,
            stream=True,
        )
        return f"OUT_DIR={out_dir}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError("Use synchronous execution for this tool.")
