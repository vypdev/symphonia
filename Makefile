.PHONY: verify specs test coverage spike-storage

COVERAGE_PYTHON ?= python3

specs:
	PYTHONPATH=. python3 tools/validate_specs.py

test:
	PYTHONPATH=src:. python3 -m unittest discover -s tests -v

coverage:
	PYTHONPATH=src:. $(COVERAGE_PYTHON) -m coverage run -m unittest discover -s tests -q
	$(COVERAGE_PYTHON) -m coverage report --sort=cover

spike-storage:
	PYTHONPATH=src:. python3 tools/storage_recovery_spike.py --operations 1000

verify: specs
	git diff --check
	$(MAKE) test
