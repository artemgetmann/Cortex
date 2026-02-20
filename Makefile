PYTHON ?= python3

.PHONY: help test test-root test-cli run-agent run-cli fl-benchmark

help:
	@echo "Cortex developer commands"
	@echo ""
	@echo "  make test-root      # run root runtime smoke tests"
	@echo "  make test-cli       # run Memory V2 CLI track tests"
	@echo "  make test           # run both test suites"
	@echo "  make run-agent      # run FL agent (requires TASK, optional SESSION)"
	@echo "  make run-cli        # run CLI track agent (requires TASK_ID, DOMAIN, SESSION)"
	@echo "  make fl-benchmark   # run FL benchmark (optional START, RUNS)"

test-root:
	$(PYTHON) -m pytest tests -q

test-cli:
	$(PYTHON) -m pytest tracks/cli_sqlite/tests -q

test: test-root test-cli

run-agent:
	@test -n "$(TASK)" || (echo "TASK is required. Example: make run-agent TASK='Create a 4-on-the-floor kick drum pattern'"; exit 1)
	$(PYTHON) scripts/run_agent.py \
		--task "$(TASK)" \
		--session $${SESSION:-1} \
		--max-steps $${MAX_STEPS:-80} \
		--llm-backend $${LLM_BACKEND:-claude_print} \
		$${VERBOSE:+--verbose}

run-cli:
	@test -n "$(TASK_ID)" || (echo "TASK_ID is required. Example: make run-cli TASK_ID=aggregate_report DOMAIN=gridtool SESSION=9501"; exit 1)
	@test -n "$(DOMAIN)" || (echo "DOMAIN is required. Example: DOMAIN=gridtool"; exit 1)
	@test -n "$(SESSION)" || (echo "SESSION is required. Example: SESSION=9501"; exit 1)
	$(PYTHON) tracks/cli_sqlite/scripts/run_cli_agent.py \
		--task-id "$(TASK_ID)" \
		--domain "$(DOMAIN)" \
		--session "$(SESSION)" \
		--max-steps $${MAX_STEPS:-12} \
		--llm-backend $${LLM_BACKEND:-claude_print} \
		$${VERBOSE:+--verbose}

fl-benchmark:
	$(PYTHON) scripts/run_fl_benchmark.py \
		--start-session $${START:-200001} \
		--runs $${RUNS:-10} \
		--max-steps $${MAX_STEPS:-12} \
		--llm-backend $${LLM_BACKEND:-claude_print}

