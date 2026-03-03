from __future__ import annotations

from pathlib import Path


def _load_runtime_impl_symbols() -> None:
    # Keep the public import path stable while moving the large implementation
    # source into a non-module payload file that this module executes at import.
    module_path = Path(__file__)
    source_parts = sorted(module_path.parent.glob("agent_runtime_loop_impl.source.part_*"))
    if not source_parts:
        raise RuntimeError("Runtime loop implementation source parts are missing.")
    source_text = "".join(part.read_text(encoding="utf-8") for part in source_parts)
    source_path = module_path.with_name("agent_runtime_loop_impl.source.part_00")
    module_globals = globals()
    exec(compile(source_text, str(source_path), "exec"), module_globals, module_globals)


_load_runtime_impl_symbols()
