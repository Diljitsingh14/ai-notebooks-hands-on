import os
import io
import shutil
import tempfile
import subprocess
from typing import Optional, List, Dict, Tuple, Union, Generator

DOCKER_IMAGE = "python:3.11-slim"


def _env_args(env_vars: Optional[Dict[str, str]]) -> List[str]:
    if not env_vars:
        return []
    args = []
    for k, v in env_vars.items():
        args += ["-e", f"{k}={v}"]
    return args


def run_code_in_sandbox(
    code: str,
    requirements: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, str]] = None,
    cpu: str = "0.5",          # limit CPU
    mem: str = "256m",         # limit RAM
    network: bool = False,     # disable network by default
    timeout_sec: int = 120,    # hard timeout
    stream: bool = False,      # if True, yield logs line-by-line
) -> Union[Tuple[str, str, str], Generator[str, None, None]]:
    """
    Runs code in a disposable Docker container.
    Returns (out_dir, stdout, stderr) when stream=False.
    When stream=True, yields log lines and finally a tuple (out_dir, stdout, stderr).
    Only /out remains after cleanup; caller can move/retain it as needed.
    """
    tmpdir = tempfile.mkdtemp(prefix="job_")
    job_out = os.path.join(tmpdir, "out")
    os.makedirs(job_out, exist_ok=True)

    script_path = os.path.join(tmpdir, "script.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)

    if requirements:
        req_path = os.path.join(tmpdir, "requirements.txt")
        with open(req_path, "w", encoding="utf-8") as f:
            f.write("\n".join(requirements))
        install_cmd = ["pip", "install", "-r", "requirements.txt"]
    else:
        install_cmd = []

    # entrypoint: install deps then run script
    entrypoint = [
        "bash", "-c",
        " && ".join(
            [
                "mkdir -p out",
                *([" ".join(install_cmd)] if install_cmd else []),
                "python script.py"
            ]
        )
    ]

    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{tmpdir}:/job",
        "-w", "/job",
        "--cpus", cpu,
        "--memory", mem,
        "--pids-limit", "256",
        "--name", f"sandbox_{os.path.basename(tmpdir)}",
    ] + _env_args(env_vars)

    if not network:
        docker_cmd += ["--network", "none"]

    docker_cmd += [DOCKER_IMAGE] + entrypoint

    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()

    if stream:
        def _generator():
            import threading
            import queue
            q = queue.Queue()

            proc = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            def _reader(pipe, label):
                for line in iter(pipe.readline, ''):
                    q.put((label, line))
                pipe.close()
                q.put((label, None))

            t1 = threading.Thread(target=_reader, args=(
                proc.stdout, "STDOUT"), daemon=True)
            t2 = threading.Thread(target=_reader, args=(
                proc.stderr, "STDERR"), daemon=True)
            t1.start()
            t2.start()

            finished = {"STDOUT": False, "STDERR": False}
            while True:
                try:
                    label, line = q.get(timeout=0.1)
                except queue.Empty:
                    if proc.poll() is not None and all(finished.values()):
                        break
                    continue

                if line is None:
                    finished[label] = True
                else:
                    if label == "STDOUT":
                        stdout_buf.write(line)
                    else:
                        stderr_buf.write(line)
                    yield f"{label} {line.rstrip()}"

            rc = proc.wait(timeout=timeout_sec)

            # Final cleanup
            parent = os.path.dirname(tmpdir)
            final_out = os.path.join(parent, f"{os.path.basename(tmpdir)}_out")
            if os.path.exists(job_out):
                shutil.move(job_out, final_out)
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir, ignore_errors=True)

            yield (final_out, stdout_buf.getvalue(), stderr_buf.getvalue())

        return _generator()

    else:
        proc = subprocess.Popen(
            docker_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout_sec)
            stdout_buf.write(out or "")
            stderr_buf.write(err or "")
        finally:
            parent = os.path.dirname(tmpdir)
            final_out = os.path.join(parent, f"{os.path.basename(tmpdir)}_out")
            if os.path.exists(job_out):
                shutil.move(job_out, final_out)
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir, ignore_errors=True)

        return final_out, stdout_buf.getvalue(), stderr_buf.getvalue()
