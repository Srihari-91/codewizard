"""
Neo4j client — manages the lightweight code dependency graph.

Schema:
  Nodes:   File {path}, Function {name, file_path}
  Rels:    (File)-[:CONTAINS]->(Function)
           (Function)-[:CALLS]->(Function)
           (File)-[:IMPORTS]->(File)
"""

import re
import structlog
from neo4j import GraphDatabase
from config import settings

logger = structlog.get_logger(__name__)


class Neo4jClient:
    def __init__(self):
        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        self._ensure_constraints()

    def close(self):
        self._driver.close()

    # ── Schema constraints ─────────────────────────────────────────────────────
    def _ensure_constraints(self):
        with self._driver.session() as s:
            s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE")
            s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (fn:Function) REQUIRE (fn.name, fn.file_path) IS NODE KEY")

    # ── Graph update ───────────────────────────────────────────────────────────
    def update_graph(self, parsed_files: list[dict]):
        """
        For each changed file, update File/Function nodes and relationships.
        parsed_files: output of DiffParser.parse()
        """
        with self._driver.session() as session:
            for pf in parsed_files:
                path = pf["path"]
                content = pf.get("content_slice", "")

                functions = self._extract_functions(content)
                imports = self._extract_imports(content)
                calls = self._extract_calls(content)

                session.execute_write(
                    self._upsert_file_and_functions,
                    path, functions, imports, calls
                )

    @staticmethod
    def _upsert_file_and_functions(tx, path, functions, imports, call_names):
        # Merge File node
        tx.run("MERGE (f:File {path: $path})", path=path)

        # Merge Function nodes and CONTAINS relationships
        for fn_name in functions:
            tx.run("""
                MERGE (fn:Function {name: $name, file_path: $path})
                WITH fn
                MATCH (f:File {path: $path})
                MERGE (f)-[:CONTAINS]->(fn)
            """, name=fn_name, path=path)

        # IMPORTS relationships
        for imp in imports:
            tx.run("""
                MERGE (dep:File {path: $dep_path})
                WITH dep
                MATCH (f:File {path: $path})
                MERGE (f)-[:IMPORTS]->(dep)
            """, dep_path=imp, path=path)

        # CALLS relationships (best-effort: match by function name)
        for call in set(call_names):
            tx.run("""
                MATCH (caller_file:File {path: $path})-[:CONTAINS]->(caller:Function)
                MATCH (callee:Function {name: $call})
                WHERE callee.file_path <> $path
                MERGE (caller)-[:CALLS]->(callee)
            """, path=path, call=call)

    # ── Impact scoring ─────────────────────────────────────────────────────────
    def compute_impact_scores(self, file_paths: list[str]) -> dict[str, float]:
        """
        Returns a dict of file_path -> impact_score.
        Score = incoming CALLS + importing files + degree centrality
        """
        scores = {}
        with self._driver.session() as session:
            for path in file_paths:
                result = session.execute_read(self._compute_score, path)
                scores[path] = result
        return scores

    @staticmethod
    def _compute_score(tx, path) -> float:
        # Count functions in file called by other files
        incoming_calls = tx.run("""
            MATCH (f:File {path: $path})-[:CONTAINS]->(fn:Function)
            MATCH (caller:Function)-[:CALLS]->(fn)
            WHERE caller.file_path <> $path
            RETURN count(caller) AS cnt
        """, path=path).single()["cnt"]

        # Count files that import this file
        importers = tx.run("""
            MATCH (other:File)-[:IMPORTS]->(f:File {path: $path})
            RETURN count(other) AS cnt
        """, path=path).single()["cnt"]

        # Degree centrality
        degree = tx.run("""
            MATCH (f:File {path: $path})
            OPTIONAL MATCH (f)-[r]-()
            RETURN count(r) AS cnt
        """, path=path).single()["cnt"]

        return float(incoming_calls * 3 + importers * 2 + degree)

    # ── Static helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _extract_functions(content: str) -> list[str]:
        return re.findall(r"^def\s+(\w+)\s*\(", content, re.MULTILINE)

    @staticmethod
    def _extract_imports(content: str) -> list[str]:
        mods = []
        for m in re.finditer(r"^(?:import|from)\s+([\w.]+)", content, re.MULTILINE):
            mods.append(m.group(1).split(".")[0])
        return list(set(mods))

    @staticmethod
    def _extract_calls(content: str) -> list[str]:
        return re.findall(r"\b(\w+)\s*\(", content)
