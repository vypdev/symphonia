from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile
import threading
import unittest

from symphonia.infrastructure import IdempotencyConflict, LeaseConflict, OperationRepository


UTC = timezone.utc


class OperationRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = OperationRepository()
        self.now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.repository.close()

    def test_create_is_idempotent_for_same_payload(self) -> None:
        first = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={"plan_digest": "abc"},
            now=self.now,
        )
        second = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={"plan_digest": "abc"},
            now=self.now + timedelta(seconds=1),
        )
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertEqual(second.state, "queued")

    def test_same_idempotency_key_cannot_change_intent(self) -> None:
        self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={"plan_digest": "abc"},
            now=self.now,
        )
        with self.assertRaises(IdempotencyConflict):
            self.repository.create(
                operation_type="copy",
                idempotency_key="copy-1",
                payload={"plan_digest": "changed"},
                now=self.now,
            )

    def test_lease_claim_checkpoint_and_terminal_state(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={"plan_digest": "abc"},
            now=self.now,
        )
        claimed = self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        self.assertEqual(claimed.state, "running")
        self.assertEqual(claimed.worker_id, "worker-a")

        completed = self.repository.checkpoint(
            operation.operation_id,
            worker_id="worker-a",
            checkpoint={"confirmed": ["occ-1"]},
            now=self.now + timedelta(seconds=1),
            state="succeeded",
        )
        self.assertEqual(completed.state, "succeeded")
        self.assertEqual(completed.checkpoint, {"confirmed": ["occ-1"]})
        self.assertIsNone(completed.worker_id)

        events = self.repository.events(operation.operation_id)
        self.assertEqual(
            [event.event_type for event in events],
            ["created", "claimed", "checkpointed"],
        )
        self.assertEqual([event.state for event in events], ["queued", "running", "succeeded"])
        self.assertEqual(events[1].worker_id, "worker-a")

    def test_two_sqlite_connections_cannot_claim_same_operation(self) -> None:
        """Exercise the BEGIN IMMEDIATE lease boundary with real connections."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = f"{temporary_directory}/operations.sqlite3"
            seed_repository = OperationRepository(database_path)
            operation = seed_repository.create(
                operation_type="copy",
                idempotency_key="concurrent-claim",
                payload={},
                now=self.now,
            )
            seed_repository.close()

            start = threading.Barrier(2)
            outcomes: list[tuple[str, str]] = []
            outcomes_lock = threading.Lock()

            def attempt_claim(worker_id: str) -> None:
                repository = OperationRepository(database_path)
                try:
                    start.wait(timeout=5)
                    repository.claim(operation.operation_id, worker_id=worker_id, now=self.now)
                    outcome = (worker_id, "claimed")
                except LeaseConflict:
                    outcome = (worker_id, "conflict")
                except Exception as error:  # pragma: no cover - keeps thread failures observable
                    outcome = (worker_id, f"error:{type(error).__name__}")
                finally:
                    repository.close()
                with outcomes_lock:
                    outcomes.append(outcome)

            threads = [
                threading.Thread(target=attempt_claim, args=(worker_id,))
                for worker_id in ("worker-a", "worker-b")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            statuses = {worker_id: status for worker_id, status in outcomes}
            self.assertEqual(set(statuses), {"worker-a", "worker-b"})
            self.assertEqual(sorted(statuses.values()), ["claimed", "conflict"])

            verifier = OperationRepository(database_path)
            try:
                record = verifier.get(operation.operation_id)
                self.assertEqual(record.state, "running")
                self.assertIn(record.worker_id, {"worker-a", "worker-b"})
                self.assertEqual(
                    [event.event_type for event in verifier.events(operation.operation_id)],
                    ["created", "claimed"],
                )
            finally:
                verifier.close()

    def test_two_sqlite_connections_claim_distinct_queue_items(self) -> None:
        """Exercise scheduler selection under concurrent workers."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = f"{temporary_directory}/operations.sqlite3"
            seed_repository = OperationRepository(database_path)
            first = seed_repository.create(
                operation_type="copy",
                idempotency_key="concurrent-next-1",
                payload={},
                now=self.now,
            )
            second = seed_repository.create(
                operation_type="copy",
                idempotency_key="concurrent-next-2",
                payload={},
                now=self.now + timedelta(seconds=1),
            )
            seed_repository.close()

            start = threading.Barrier(2)
            outcomes: list[tuple[str, str | None]] = []
            outcomes_lock = threading.Lock()

            def claim_next(worker_id: str) -> None:
                repository = OperationRepository(database_path)
                try:
                    start.wait(timeout=5)
                    claimed = repository.claim_next(worker_id=worker_id, now=self.now)
                    outcome = (worker_id, None if claimed is None else claimed.operation_id)
                except Exception as error:  # pragma: no cover - keeps thread failures observable
                    outcome = (worker_id, f"error:{type(error).__name__}")
                finally:
                    repository.close()
                with outcomes_lock:
                    outcomes.append(outcome)

            threads = [
                threading.Thread(target=claim_next, args=(worker_id,))
                for worker_id in ("worker-a", "worker-b")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual({worker_id for worker_id, _ in outcomes}, {"worker-a", "worker-b"})
            claimed_ids = [operation_id for _, operation_id in outcomes]
            self.assertEqual(set(claimed_ids), {first.operation_id, second.operation_id})
            self.assertEqual(len(claimed_ids), len(set(claimed_ids)))

    def test_checkpoint_events_store_only_sanitized_summary(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={"plan_digest": "abc"},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        self.repository.checkpoint(
            operation.operation_id,
            worker_id="worker-a",
            checkpoint={
                "confirmed_occurrences": ["occ-1", "occ-2"],
                "issues": [{"code": "provider_error"}],
                "private_value": "must-not-be-an-audit-payload",
            },
            now=self.now + timedelta(seconds=1),
        )

        event = self.repository.events(operation.operation_id)[-1]
        self.assertEqual(event.payload["confirmed_occurrences_count"], 2)
        self.assertEqual(event.payload["issues_count"], 1)
        self.assertEqual(
            event.payload["checkpoint_keys"],
            ["confirmed_occurrences", "issues", "private_value"],
        )
        self.assertNotIn("must-not-be-an-audit-payload", event.payload)

    def test_checkpoint_rejects_nested_credentials_before_persistence(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="checkpoint-credential",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)

        with self.assertRaisesRegex(ValueError, "access_token"):
            self.repository.checkpoint(
                operation.operation_id,
                worker_id="worker-a",
                checkpoint={"provider": {"access_token": "must-not-persist"}},
                now=self.now + timedelta(seconds=1),
            )

        self.assertEqual(self.repository.get(operation.operation_id).checkpoint, {})

    def test_retry_and_rate_limit_checkpoints_reject_credentials(self) -> None:
        retry_operation = self.repository.create(
            operation_type="copy",
            idempotency_key="retry-checkpoint-credential",
            payload={},
            now=self.now,
        )
        self.repository.claim(retry_operation.operation_id, worker_id="worker-a", now=self.now)
        with self.assertRaises(ValueError):
            self.repository.schedule_retry(
                retry_operation.operation_id,
                worker_id="worker-a",
                next_run_at=self.now + timedelta(minutes=1),
                checkpoint={"refresh_token": "must-not-persist"},
                now=self.now,
            )

        rate_limit_operation = self.repository.create(
            operation_type="copy",
            idempotency_key="rate-limit-checkpoint-credential",
            payload={},
            now=self.now,
        )
        self.repository.claim(rate_limit_operation.operation_id, worker_id="worker-a", now=self.now)
        with self.assertRaises(ValueError):
            self.repository.schedule_rate_limit(
                rate_limit_operation.operation_id,
                worker_id="worker-a",
                next_run_at=self.now + timedelta(minutes=1),
                checkpoint={"client_secret": "must-not-persist"},
                now=self.now,
            )

    def test_diagnostic_export_is_bounded_and_redacted(self) -> None:
        operation = self.repository.create(
                operation_type="copy",
                idempotency_key="copy-1",
                payload={"plan_digest": "secret-plan", "private_value": "secret-token"},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        self.repository.checkpoint(
            operation.operation_id,
            worker_id="worker-a",
            checkpoint={
                "confirmed_occurrences": ["occ-1"],
                "provider_track_id": "provider-secret",
            },
            now=self.now + timedelta(seconds=1),
        )

        diagnostic = self.repository.diagnostic(operation.operation_id, event_limit=2)
        self.assertEqual(diagnostic["operation_id"], operation.operation_id)
        self.assertEqual(diagnostic["payload_keys"], ["plan_digest", "private_value"])
        self.assertEqual(diagnostic["checkpoint"]["confirmed_occurrences_count"], 1)
        self.assertTrue(diagnostic["events_truncated"])
        self.assertEqual(len(diagnostic["events"]), 2)
        serialized = str(diagnostic)
        self.assertNotIn("secret-plan", serialized)
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("provider-secret", serialized)
        with self.assertRaises(ValueError):
            self.repository.diagnostic(operation.operation_id, event_limit=101)

    def test_diagnostics_list_is_bounded_and_redacted(self) -> None:
        for index in range(3):
            self.repository.create(
                operation_type="copy",
                idempotency_key=f"diagnostic-{index}",
                payload={"private_value": f"secret-{index}"},
                now=self.now + timedelta(seconds=index),
            )

        diagnostics = self.repository.diagnostics(limit=2, event_limit=1)

        self.assertEqual(len(diagnostics), 2)
        self.assertTrue(all("payload_keys" in item for item in diagnostics))
        self.assertTrue(all("private_value" in item["payload_keys"] for item in diagnostics))
        self.assertNotIn("secret-", str(diagnostics))

        with self.assertRaises(ValueError):
            self.repository.diagnostics(limit=0)
        with self.assertRaises(ValueError):
            self.repository.diagnostics(limit=101)

    def test_diagnostic_key_lists_are_bounded_and_mark_truncation(self) -> None:
        payload = {f"key-{index:03d}": index for index in range(101)}
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="bounded-diagnostic-keys",
            payload=payload,
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        self.repository.checkpoint(
            operation.operation_id,
            worker_id="worker-a",
            checkpoint={f"checkpoint-{index:03d}": index for index in range(101)},
            now=self.now + timedelta(seconds=1),
        )

        diagnostic = self.repository.diagnostic(operation.operation_id)

        self.assertEqual(len(diagnostic["payload_keys"]), 100)
        self.assertTrue(diagnostic["payload_keys_truncated"])
        self.assertEqual(len(diagnostic["checkpoint"]["checkpoint_keys"]), 100)
        self.assertTrue(diagnostic["checkpoint"]["checkpoint_keys_truncated"])

    def test_diagnostic_reads_only_a_bounded_event_window(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="bounded-event-window",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        for index in range(12):
            self.repository.checkpoint(
                operation.operation_id,
                worker_id="worker-a",
                checkpoint={"step": index},
                now=self.now + timedelta(seconds=index + 1),
            )

        diagnostic = self.repository.diagnostic(operation.operation_id, event_limit=5)

        self.assertTrue(diagnostic["events_truncated"])
        self.assertEqual(len(diagnostic["events"]), 5)
        self.assertEqual(
            [event["event_type"] for event in diagnostic["events"]],
            ["checkpointed"] * 5,
        )

    def test_queue_summary_is_aggregate_and_counts_only_eligible_work(self) -> None:
        queued = self.repository.create(
            operation_type="copy",
            idempotency_key="summary-queued",
            payload={"plan_digest": "opaque"},
            now=self.now,
        )
        running = self.repository.create(
            operation_type="copy",
            idempotency_key="summary-running",
            payload={},
            now=self.now,
        )
        self.repository.claim(running.operation_id, worker_id="worker-a", now=self.now, lease_seconds=60)
        retry = self.repository.create(
            operation_type="import",
            idempotency_key="summary-retry",
            payload={},
            now=self.now,
        )
        self.repository.claim(retry.operation_id, worker_id="worker-a", now=self.now)
        self.repository.schedule_retry(
            retry.operation_id,
            worker_id="worker-a",
            next_run_at=self.now - timedelta(seconds=1),
            checkpoint={"private": "not returned"},
            now=self.now,
        )

        summary = self.repository.queue_summary(now=self.now)

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["states"], {"queued": 1, "retry_scheduled": 1, "running": 1})
        self.assertEqual(summary["eligible_count"], 2)
        self.assertEqual(summary["expired_lease_count"], 0)
        self.assertEqual(
            summary["oldest_eligible_at"],
            (self.now - timedelta(seconds=1)).isoformat(timespec="microseconds"),
        )
        self.assertEqual(summary["oldest_eligible_age_seconds"], 1)
        self.assertEqual(summary["cancellation_requested_count"], 0)
        self.assertNotIn("opaque", str(summary))
        self.assertNotIn("private", str(summary))

    def test_queue_summary_counts_expired_leases(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="summary-expired",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now, lease_seconds=1)

        summary = self.repository.queue_summary(now=self.now + timedelta(seconds=2))

        self.assertEqual(summary["eligible_count"], 1)
        self.assertEqual(summary["expired_lease_count"], 1)
        self.assertEqual(summary["oldest_eligible_age_seconds"], 1)

    def test_operation_payload_rejects_credential_named_fields(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.create(
                operation_type="copy",
                idempotency_key="credential-payload",
                payload={"access_token": "must-not-persist"},
                now=self.now,
            )

    def test_operation_payload_rejects_nested_credentials(self) -> None:
        with self.assertRaisesRegex(ValueError, r"provider.credentials\[0\]\.access_token"):
            self.repository.create(
                operation_type="copy",
                idempotency_key="nested-credential-payload",
                payload={"provider": {"credentials": [{"access_token": "must-not-persist"}]}},
                now=self.now,
            )

    def test_operation_payload_rejects_cyclic_structures_before_json_encoding(self) -> None:
        payload: dict[str, object] = {}
        payload["nested"] = payload
        with self.assertRaisesRegex(ValueError, "cyclic"):
            self.repository.create(
                operation_type="copy",
                idempotency_key="cyclic-payload",
                payload=payload,
                now=self.now,
            )

    def test_operation_payload_and_checkpoint_must_be_json_objects(self) -> None:
        with self.assertRaisesRegex(ValueError, "operation payload must be a JSON object"):
            self.repository.create(
                operation_type="copy",
                idempotency_key="list-payload",
                payload=[],  # type: ignore[arg-type]
                now=self.now,
            )

        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="list-checkpoint",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        with self.assertRaisesRegex(ValueError, "checkpoint must be a JSON object"):
            self.repository.checkpoint(
                operation.operation_id,
                worker_id="worker-a",
                checkpoint=[],  # type: ignore[arg-type]
                now=self.now + timedelta(seconds=1),
            )
        self.assertEqual(self.repository.get(operation.operation_id).state, "running")

    def test_non_finite_numbers_are_rejected_before_durable_json_writes(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.create(
                operation_type="copy",
                idempotency_key="nan-payload",
                payload={"value": float("nan")},
                now=self.now,
            )

        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="nan-checkpoint",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        with self.assertRaises(ValueError):
            self.repository.checkpoint(
                operation.operation_id,
                worker_id="worker-a",
                checkpoint={"value": float("inf")},
                now=self.now,
            )
        self.assertEqual(self.repository.get(operation.operation_id).checkpoint, {})

        self.repository._connection.execute(
            "UPDATE operations SET payload_json = ? WHERE operation_id = ?",
            ('{"value": NaN}', operation.operation_id),
        )
        with self.assertRaises(ValueError):
            self.repository.get(operation.operation_id)

    def test_healthcheck_fails_closed_on_invalid_state_or_json(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="healthcheck-corruption",
            payload={},
            now=self.now,
        )

        self.repository._connection.execute(  # type: ignore[attr-defined]
            "UPDATE operations SET state = ? WHERE operation_id = ?",
            ("not-a-real-state", operation.operation_id),
        )
        self.assertFalse(self.repository.healthcheck())

        self.repository._connection.execute(  # type: ignore[attr-defined]
            "UPDATE operations SET state = ?, payload_json = ? WHERE operation_id = ?",
            ("queued", "[]", operation.operation_id),
        )
        self.assertFalse(self.repository.healthcheck())

        self.repository._connection.execute(  # type: ignore[attr-defined]
            "UPDATE operations SET payload_json = ? WHERE operation_id = ?",
            ('{"access_token":"must-not-be-readable"}', operation.operation_id),
        )
        self.assertFalse(self.repository.healthcheck())

    def test_operation_and_worker_identifiers_require_non_empty_text(self) -> None:
        for field, value in (
            ("operation_type", None),
            ("idempotency_key", "   "),
            ("operation_id", ""),
        ):
            values = {
                "operation_type": "copy",
                "idempotency_key": "identifier-test",
                "payload": {},
                "now": self.now,
            }
            if field == "operation_id":
                values[field] = value
            else:
                values[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.repository.create(**values)

        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="worker-identifier-test",
            payload={},
            now=self.now,
        )
        with self.assertRaises(ValueError):
            self.repository.claim(operation.operation_id, worker_id=None, now=self.now)  # type: ignore[arg-type]

    def test_operation_payload_rejects_non_string_object_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "keys must be strings"):
            self.repository.create(
                operation_type="copy",
                idempotency_key="numeric-key",
                payload={1: "must-not-be-coerced"},  # type: ignore[dict-item]
                now=self.now,
            )

    def test_only_lease_owner_can_checkpoint(self) -> None:
        operation = self.repository.create(
            operation_type="import",
            idempotency_key="import-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        with self.assertRaises(LeaseConflict):
            self.repository.checkpoint(
                operation.operation_id,
                worker_id="worker-b",
                checkpoint={},
                now=self.now + timedelta(seconds=1),
            )

    def test_expired_lease_can_be_reclaimed_and_retry_survives(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now, lease_seconds=5)
        retry = self.repository.schedule_retry(
            operation.operation_id,
            worker_id="worker-a",
            next_run_at=self.now + timedelta(minutes=1),
            checkpoint={"last": "timeout"},
            now=self.now + timedelta(seconds=1),
        )
        self.assertEqual(retry.state, "retry_scheduled")
        self.assertEqual(retry.next_run_at, self.now + timedelta(minutes=1))
        self.assertIsNone(retry.worker_id)

        reclaimed = self.repository.claim(
            operation.operation_id,
            worker_id="worker-b",
            now=self.now + timedelta(minutes=2),
        )
        self.assertEqual(reclaimed.worker_id, "worker-b")

    def test_expired_running_lease_can_be_reclaimed(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now, lease_seconds=5)
        reclaimed = self.repository.claim(
            operation.operation_id,
            worker_id="worker-b",
            now=self.now + timedelta(seconds=6),
        )
        self.assertEqual(reclaimed.worker_id, "worker-b")
        events = self.repository.events(operation.operation_id)
        self.assertEqual(events[-1].event_type, "lease_reclaimed")
        self.assertEqual(events[-1].payload["previous_worker_id"], "worker-a")

    def test_claim_next_selects_queued_and_due_retry_work(self) -> None:
        queued = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-queued",
            payload={},
            now=self.now,
        )
        retry = self.repository.create(
            operation_type="import",
            idempotency_key="import-retry",
            payload={},
            now=self.now + timedelta(seconds=1),
        )
        self.repository.claim(retry.operation_id, worker_id="worker-a", now=self.now)
        self.repository.schedule_retry(
            retry.operation_id,
            worker_id="worker-a",
            next_run_at=self.now + timedelta(minutes=1),
            checkpoint={},
            now=self.now + timedelta(seconds=1),
        )

        claimed = self.repository.claim_next(worker_id="worker-b", now=self.now + timedelta(seconds=2))
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.operation_id, queued.operation_id)
        self.assertIsNone(
            self.repository.claim_next(
                worker_id="worker-b",
                now=self.now + timedelta(seconds=30),
                operation_type="import",
            )
        )

        due = self.repository.claim_next(
            worker_id="worker-c",
            now=self.now + timedelta(minutes=2),
            operation_type="import",
        )
        self.assertIsNotNone(due)
        self.assertEqual(due.operation_id, retry.operation_id)

    def test_claim_next_recovers_an_expired_running_lease(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now, lease_seconds=5)

        recovered = self.repository.claim_next(
            worker_id="worker-b",
            now=self.now + timedelta(seconds=6),
        )
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.operation_id, operation.operation_id)
        self.assertEqual(recovered.worker_id, "worker-b")
        self.assertEqual(self.repository.events(operation.operation_id)[-1].event_type, "lease_reclaimed")

    def test_retry_cannot_be_claimed_before_its_scheduled_time(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        self.repository.schedule_retry(
            operation.operation_id,
            worker_id="worker-a",
            next_run_at=self.now + timedelta(minutes=1),
            checkpoint={"last": "rate_limited"},
            now=self.now + timedelta(seconds=1),
        )
        with self.assertRaises(LeaseConflict):
            self.repository.claim(
                operation.operation_id,
                worker_id="worker-b",
                now=self.now + timedelta(seconds=30),
            )

    def test_rate_limit_wait_is_durable_and_claimable_after_deadline(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        waiting = self.repository.schedule_rate_limit(
            operation.operation_id,
            worker_id="worker-a",
            next_run_at=self.now + timedelta(minutes=2),
            checkpoint={"confirmed_occurrences": ["occ-1"]},
            now=self.now + timedelta(seconds=1),
        )
        self.assertEqual(waiting.state, "waiting_rate_limit")
        with self.assertRaises(LeaseConflict):
            self.repository.claim(operation.operation_id, worker_id="worker-b", now=self.now + timedelta(minutes=1))
        claimed = self.repository.claim_next(
            worker_id="worker-b",
            now=self.now + timedelta(minutes=2),
        )
        self.assertEqual(claimed.operation_id, operation.operation_id)
        self.assertEqual(
            [event.event_type for event in self.repository.events(operation.operation_id)],
            ["created", "claimed", "rate_limit_wait", "claimed"],
        )

    def test_cancellation_race_does_not_schedule_retry(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-cancel-race",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        self.repository.cancel(operation.operation_id, now=self.now + timedelta(seconds=1))

        cancelled = self.repository.schedule_retry(
            operation.operation_id,
            worker_id="worker-a",
            next_run_at=self.now + timedelta(minutes=1),
            checkpoint={"failure_code": "timeout"},
            now=self.now + timedelta(seconds=2),
        )

        self.assertEqual(cancelled.state, "cancelled")
        self.assertIsNone(cancelled.next_run_at)
        self.assertEqual(
            [event.event_type for event in self.repository.events(operation.operation_id)],
            ["created", "claimed", "cancellation_requested", "cancelled"],
        )

    def test_healthy_worker_can_renew_lease(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        claimed = self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now, lease_seconds=5)
        renewed = self.repository.renew_lease(
            operation.operation_id,
            worker_id="worker-a",
            now=self.now + timedelta(seconds=1),
            lease_seconds=60,
        )
        self.assertGreater(renewed.lease_expires_at, claimed.lease_expires_at)

    def test_waiting_user_operation_releases_lease_and_can_resume(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        waiting = self.repository.checkpoint(
            operation.operation_id,
            worker_id="worker-a",
            checkpoint={"unknown_step": "occ-1"},
            now=self.now + timedelta(seconds=1),
            state="waiting_user",
        )
        self.assertEqual(waiting.state, "waiting_user")
        self.assertIsNone(waiting.worker_id)
        resumed = self.repository.resume(operation.operation_id, now=self.now + timedelta(seconds=2))
        self.assertEqual(resumed.state, "queued")

    def test_queued_cancellation_is_terminal(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        cancelled = self.repository.cancel(operation.operation_id, now=self.now + timedelta(seconds=1))
        self.assertEqual(cancelled.state, "cancelled")
        self.assertFalse(cancelled.cancel_requested)

    def test_running_cancellation_is_acknowledged_at_checkpoint(self) -> None:
        operation = self.repository.create(
            operation_type="copy",
            idempotency_key="copy-1",
            payload={},
            now=self.now,
        )
        claimed = self.repository.claim(operation.operation_id, worker_id="worker-a", now=self.now)
        requested = self.repository.cancel(operation.operation_id, now=self.now + timedelta(seconds=1))
        self.assertEqual(requested.state, "running")
        self.assertTrue(requested.cancel_requested)
        completed = self.repository.checkpoint(
            claimed.operation_id,
            worker_id="worker-a",
            checkpoint={"confirmed": ["occ-1"]},
            now=self.now + timedelta(seconds=2),
            state="running",
        )
        self.assertEqual(completed.state, "cancelled")
        self.assertFalse(completed.cancel_requested)
        self.assertIsNone(completed.worker_id)
        self.assertEqual(
            [event.event_type for event in self.repository.events(operation.operation_id)],
            ["created", "claimed", "cancellation_requested", "checkpointed"],
        )

    def test_legacy_store_is_migrated_forward_without_losing_operations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE operations (
                    operation_id TEXT PRIMARY KEY,
                    operation_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    worker_id TEXT,
                    lease_expires_at TEXT,
                    next_run_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                PRAGMA user_version = 1;
                """
            )
            connection.execute(
                """
                INSERT INTO operations (
                    operation_id, operation_type, state, idempotency_key,
                    payload_json, checkpoint_json, created_at, updated_at
                ) VALUES ('legacy-1', 'copy', 'queued', 'legacy-key', '{}', '{}', ?, ?)
                """,
                (self.now.isoformat(), self.now.isoformat()),
            )
            connection.commit()
            connection.close()

            repository = OperationRepository(path)
            try:
                record = repository.get("legacy-1")
                self.assertFalse(record.cancel_requested)
                self.assertEqual(
                    repository._connection.execute(
                        "SELECT COUNT(*) FROM operation_events"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    repository._connection.execute("PRAGMA user_version").fetchone()[0],
                    OperationRepository.SCHEMA_VERSION,
                )
            finally:
                repository.close()

    def test_fresh_operation_store_commits_schema_and_version_together(self) -> None:
        self.assertEqual(
            self.repository._connection.execute("PRAGMA user_version").fetchone()[0],  # type: ignore[attr-defined]
            self.repository.SCHEMA_VERSION,
        )
        self.assertFalse(self.repository._connection.in_transaction)  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
