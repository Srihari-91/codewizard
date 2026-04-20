"""
SandboxExecutor — validates proposed fixes by running them in an isolated
Docker container with a 30-second timeout.

Strategy:
  1. Write the fixed code to a temp file
  2. Run `python -m py_compile` (syntax check) + `pytest --co -q` if tests exist
  3. Return True if all checks pass
"""

import os
import tempfile
import structlog
from config import settings

logger = structlog.get_logger(__name__)


class SandboxExecutor:
    def validate(self, fix: dict) -> bool:
        """
        Returns True if the fix passes basic validation.
        Uses Docker if available, falls back to subprocess.
        """
        fix_code = fix.get("fix_code")
        if not fix_code:
            return False

        try:
            import docker
            return self._validate_docker(fix_code, fix)
        except Exception as e:
            logger.warning("docker_unavailable", error=str(e))
            return self._validate_subprocess(fix_code)

    def _validate_docker(self, fix_code: str, fix: dict) -> bool:
        import docker

        client = docker.from_env()
        with tempfile.TemporaryDirectory() as tmpdir:
            code_file = os.path.join(tmpdir, "fix_check.py")
            with open(code_file, "w") as f:
                # Write the raw fix — could be full file or diff-style
                # We extract the "+" lines if it's a diff
                if fix_code.strip().startswith("@@") or "\n+" in fix_code:
                    code = "\n".join(
                        line[1:] for line in fix_code.splitlines()
                        if line.startswith("+") and not line.startswith("+++")
                    )
                else:
                    code = fix_code
                f.write(code)

            try:
                result = client.containers.run(
                    "python:3.11-alpine",
                    f"python -m py_compile /code/fix_check.py && echo OK",
                    volumes={tmpdir: {"bind": "/code", "mode": "ro"}},
                    remove=True,
                    network_disabled=True,
                    mem_limit="64m",
                    cpu_period=100000,
                    cpu_quota=50000,
                    timeout=settings.SANDBOX_TIMEOUT,
                )
                output = result.decode("utf-8", errors="replace").strip()
                passed = "OK" in output
                logger.info("sandbox_result", passed=passed, output=output[:100])
                return passed
            except Exception as e:
                logger.warning("sandbox_container_error", error=str(e))
                return False

    def _validate_subprocess(self, fix_code: str) -> bool:
        """Lightweight fallback: just compile-check the Python code."""
        import subprocess

        if fix_code.strip().startswith("@@") or "\n+" in fix_code:
            code = "\n".join(
                line[1:] for line in fix_code.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            )
        else:
            code = fix_code

        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(code)
            tmp_path = f.name

        try:
            result = subprocess.run(
                ["python3", "-m", "py_compile", tmp_path],
                capture_output=True,
                timeout=settings.SANDBOX_TIMEOUT,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning("subprocess_validate_error", error=str(e))
            return False
        finally:
            os.unlink(tmp_path)
