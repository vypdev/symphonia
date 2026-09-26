.PHONY: verify specs test spike-storage

specs:
	PYTHONPATH=. python3 tools/validate_specs.py

test:
	PYTHONPATH=src:. python3 -m unittest discover -s tests -v

spike-storage:
	PYTHONPATH=src:. python3 tools/storage_recovery_spike.py --operations 1000

verify: specs
	git diff --check
	$(MAKE) test
