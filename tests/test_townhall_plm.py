"""Calibration for the Town Hall's product lifecycle gates.

The estate's recurring defect is a control that exists, runs and reports but
does not act. A lifecycle gate is the easiest place in the world to build one
by accident, so most of what follows tests the refusal rather than the pass.

Every test below was calibrated by mutating the behaviour it protects and
confirming it fails, then restoring.
"""

from __future__ import annotations

import pytest

from src.townhall.plm import (
    CRITERIA,
    DeliverableKind,
    GateBlocked,
    Outcome,
    PlmService,
    Stage,
    UnknownCriterionError,
    UnknownDeliverableError,
    criteria_for,
    next_stage,
)


@pytest.fixture
def plm(tmp_path):
    service = PlmService(db_path=tmp_path / "plm.db")
    yield service
    service.close()


def _game(plm, title="A platformer"):
    return plm.create(title=title, kind=DeliverableKind.GAME, location="TranceFlow")


def _pass(plm, item, criterion_id, ref="ref"):
    return plm.submit_evidence(item.id, criterion_id, ref, Outcome.PASS, "tester")


def _to_stage(plm, item, target: Stage):
    """Walk a deliverable to a stage, evidencing whatever each gate asks."""
    while plm.get(item.id).stage is not target:
        current = plm.get(item.id)
        for cs in plm.gate_status(item.id).criteria:
            if cs.criterion.mandatory:
                _pass(plm, item, cs.criterion.id)
        plm.advance(item.id, approver="tristuran")
        assert plm.get(item.id).stage is not current.stage
    return plm.get(item.id)


class TestTheGateRefuses:
    def test_an_unevidenced_gate_raises_rather_than_warning(self, plm):
        """Calibrated: returning the deliverable instead of raising fails this.

        This is the whole module. A gate whose refusal a caller may ignore is
        a report, and the platform already has plenty of those.
        """
        item = _game(plm)
        with pytest.raises(GateBlocked) as exc:
            plm.advance(item.id)
        assert exc.value.stage is Stage.CONCEPT
        assert [c.id for c in exc.value.unmet] == ["concept.business-case"]

    def test_a_blocked_deliverable_does_not_move(self, plm):
        """Calibrated: writing the stage before the gate check fails this."""
        item = _game(plm)
        with pytest.raises(GateBlocked):
            plm.advance(item.id)
        assert plm.get(item.id).stage is Stage.CONCEPT

    def test_failed_evidence_does_not_satisfy_its_criterion(self, plm):
        """Calibrated: satisfying on `ev is not None` fails this.

        A test suite that ran and went red is evidence *against* the gate.
        Counting the existence of the record is exactly how a red suite
        passes a release gate.
        """
        item = _game(plm)
        plm.submit_evidence(item.id, "concept.business-case", "BC-1", Outcome.FAIL, "tester")
        with pytest.raises(GateBlocked):
            plm.advance(item.id)

    def test_pending_evidence_does_not_satisfy_either(self, plm):
        item = _game(plm)
        plm.submit_evidence(item.id, "concept.business-case", "BC-1", Outcome.PENDING, "tester")
        with pytest.raises(GateBlocked):
            plm.advance(item.id)

    def test_a_failing_rerun_takes_satisfaction_away_again(self, plm):
        """Calibrated: using the first or any PASS row rather than the latest fails this.

        A criterion satisfied in March and re-run red in September is not
        satisfied. Reading "has any passing evidence" would keep the gate
        open on the strength of a result the platform has since disproved.
        """
        item = _game(plm)
        _pass(plm, item, "concept.business-case")
        assert plm.gate_status(item.id).can_advance
        plm.submit_evidence(item.id, "concept.business-case", "BC-2", Outcome.FAIL, "tester")
        assert not plm.gate_status(item.id).can_advance

    def test_evidence_for_another_criterion_satisfies_nothing(self, plm):
        """Calibrated: matching evidence by deliverable alone fails this."""
        item = _game(plm)
        _pass(plm, item, "validation.tested")
        with pytest.raises(GateBlocked) as exc:
            plm.advance(item.id)
        assert [c.id for c in exc.value.unmet] == ["concept.business-case"]

    def test_evidence_against_an_unknown_criterion_is_rejected(self, plm):
        """Calibrated: storing it anyway fails this.

        Evidence filed under a name no gate reads satisfies nothing while
        looking, in every listing, exactly like evidence that did.
        """
        item = _game(plm)
        with pytest.raises(UnknownCriterionError):
            plm.submit_evidence(item.id, "design.vibes", "ref", Outcome.PASS, "tester")

    def test_evidence_against_an_unknown_deliverable_is_rejected(self, plm):
        with pytest.raises(UnknownDeliverableError):
            plm.submit_evidence("PLM-NOPE", "concept.business-case", "r", Outcome.PASS, "t")


class TestTheGateOpens:
    def test_a_fully_evidenced_gate_advances(self, plm):
        item = _game(plm)
        _pass(plm, item, "concept.business-case")
        assert plm.advance(item.id, approver="tristuran").stage is Stage.INITIATION

    def test_stages_run_in_order_and_cannot_be_skipped(self, plm):
        """Calibrated: letting `advance` take a target stage fails this.

        The lifecycle is the guarantee. A deliverable that can jump from
        concept to release meets no gate at all.
        """
        item = _game(plm)
        seen = [item.stage]
        for _ in range(len(Stage) - 1):
            for cs in plm.gate_status(item.id).criteria:
                if cs.criterion.mandatory:
                    _pass(plm, item, cs.criterion.id)
            seen.append(plm.advance(item.id, approver="tristuran").stage)
        assert seen == [
            Stage.CONCEPT,
            Stage.INITIATION,
            Stage.DESIGN,
            Stage.BUILD,
            Stage.VALIDATION,
            Stage.RELEASE,
            Stage.CLOSED,
        ]

    def test_a_closed_deliverable_has_nowhere_left_to_go(self, plm):
        item = _to_stage(plm, _game(plm), Stage.CLOSED)
        with pytest.raises(GateBlocked):
            plm.advance(item.id)

    def test_an_optional_criterion_does_not_block(self, plm):
        """Calibrated: treating every criterion as mandatory fails this.

        release.lessons is worth asking for and not worth blocking a release
        on. Making everything mandatory is how a gate gets waived by policy
        and stops meaning anything.
        """
        item = _to_stage(plm, _game(plm), Stage.RELEASE)
        _pass(plm, item, "release.documented")
        _pass(plm, item, "release.authorised")
        assert plm.gate_status(item.id).can_advance
        assert "release.lessons" not in [c.id for c in plm.gate_status(item.id).unmet]


class TestWaivers:
    def test_a_waiver_needs_a_written_reason(self, plm):
        """Calibrated: dropping the reason check fails this."""
        item = _game(plm)
        with pytest.raises(ValueError, match="reason"):
            plm.waive(item.id, "concept.business-case", "   ", "tristuran")

    def test_a_waiver_needs_a_named_approver(self, plm):
        item = _game(plm)
        with pytest.raises(ValueError, match="approver"):
            plm.waive(item.id, "concept.business-case", "out of scope for the pilot", "")

    def test_a_waived_gate_is_recorded_as_waived_not_passed(self, plm):
        """Calibrated: recording every advance as PASSED fails this.

        Six months later the difference between "we did the work" and "we
        agreed not to" is the only question anyone asks, and a waiver that
        looks like a pass cannot answer it.
        """
        item = _game(plm)
        plm.waive(item.id, "concept.business-case", "internal spike, no case", "tristuran")
        plm.advance(item.id, approver="tristuran")
        entry = plm.history(item.id)[0]
        assert entry["decision"] == "waived"
        assert entry["waived_criteria"] == ["concept.business-case"]
        assert entry["approver"] == "tristuran"

    def test_a_gate_with_real_evidence_is_recorded_as_passed(self, plm):
        """The contrast the test above depends on."""
        item = _game(plm)
        _pass(plm, item, "concept.business-case")
        plm.advance(item.id, approver="tristuran")
        assert plm.history(item.id)[0]["decision"] == "passed"
        assert plm.history(item.id)[0]["waived_criteria"] == []

    def test_a_waiver_for_an_unknown_criterion_is_rejected(self, plm):
        item = _game(plm)
        with pytest.raises(UnknownCriterionError):
            plm.waive(item.id, "design.vibes", "because", "tristuran")


class TestCriteriaFitTheDeliverable:
    def test_an_image_is_not_asked_for_a_build_artefact(self, plm):
        """Calibrated: giving build.artefact-registered every kind fails this.

        A checklist an image can only half-satisfy trains everyone to waive
        the half that never applied, and a waiver habit is how a gate dies.
        """
        ids = [c.id for c in criteria_for(DeliverableKind.IMAGE, Stage.BUILD)]
        assert "build.artefact-registered" not in ids

    def test_a_module_is_not_asked_for_an_accessibility_audit(self, plm):
        ids = [c.id for c in criteria_for(DeliverableKind.MODULE, Stage.DESIGN)]
        assert "design.accessible" not in ids

    def test_everything_with_an_interface_is_asked_for_both(self, plm):
        """Calibrated: dropping design.accessible from any interactive kind fails this.

        Design review and accessibility audit must not drift apart. Reviewed
        and unaudited is the exact state web/ was already in: ARIA attributes
        hand-written, and nothing in either CI tree verifying them.
        """
        for kind in (
            DeliverableKind.GAME,
            DeliverableKind.APPLICATION,
            DeliverableKind.DESIGN_SYSTEM,
            DeliverableKind.TEMPLATE,
        ):
            ids = {c.id for c in criteria_for(kind, Stage.DESIGN)}
            assert {"design.reviewed", "design.accessible"} <= ids, kind

    def test_every_kind_must_be_tested_and_documented(self, plm):
        """Calibrated: narrowing either criterion's applies_to fails this.

        These are the two the brief asks for by name — validation, and
        documentation generated for everything built.
        """
        for kind in DeliverableKind:
            assert "validation.tested" in {c.id for c in criteria_for(kind, Stage.VALIDATION)}
            assert "release.documented" in {c.id for c in criteria_for(kind, Stage.RELEASE)}

    def test_every_criterion_names_the_location_that_supplies_it(self, plm):
        """Calibrated: blanking any supplied_by fails this.

        A criterion nobody owns is a criterion nobody produces.
        """
        for crit in CRITERIA:
            assert crit.supplied_by.strip(), crit.id

    def test_criterion_ids_are_unique(self, plm):
        ids = [c.id for c in CRITERIA]
        assert len(ids) == len(set(ids))


class TestDurability:
    def test_a_deliverable_survives_a_restart(self, tmp_path):
        """Calibrated: holding records in a dict fails this.

        A gate whose record disappears on restart cannot be audited, which
        is the same as not gating.
        """
        first = PlmService(db_path=tmp_path / "plm.db")
        item = first.create("A game", DeliverableKind.GAME, "TranceFlow", "owner")
        first.submit_evidence(item.id, "concept.business-case", "BC-1", Outcome.PASS, "t")
        first.advance(item.id, approver="tristuran")
        first.close()

        second = PlmService(db_path=tmp_path / "plm.db")
        try:
            assert second.get(item.id).stage is Stage.INITIATION
            assert second.history(item.id)[0]["decision"] == "passed"
        finally:
            second.close()

    def test_the_deliverable_records_who_answers_for_its_location(self, plm):
        """The CMDB spine, not a guess: unresolved is recorded as unresolved."""
        item = _game(plm)
        assert item.ownership is not None
        assert item.ownership["service"] == "TranceFlow"

    def test_history_is_oldest_first(self, plm):
        item = _to_stage(plm, _game(plm), Stage.BUILD)
        stages = [h["stage"] for h in plm.history(item.id)]
        assert stages == ["concept", "initiation", "design"]


class TestStageArithmetic:
    def test_next_stage_ends_at_closed(self):
        assert next_stage(Stage.CLOSED) is None

    def test_next_stage_walks_the_declared_order(self):
        assert next_stage(Stage.CONCEPT) is Stage.INITIATION
        assert next_stage(Stage.RELEASE) is Stage.CLOSED


class TestTheHttpSurface:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from auth import get_current_user
        from src.townhall import plm as plm_module
        from src.townhall.plm_routes import router

        service = PlmService(db_path=tmp_path / "plm.db")
        monkeypatch.setattr(plm_module, "_service", service)
        app = FastAPI()
        app.include_router(router)
        # The writes take the admin gate, so the surface tests need a principal.
        # Overridden rather than tokenised: what is under test here is the
        # routes' own behaviour, and `TestTheWritesAreGated` below covers the
        # gate itself with the override deliberately absent or downgraded.
        app.dependency_overrides[get_current_user] = lambda: {
            "sub": "test-admin",
            "username": "test-admin",
            "role": "admin",
        }
        yield TestClient(app)
        service.close()

    def _deliverable(self, client):
        return client.post(
            "/townhall/plm/deliverables",
            json={"title": "A platformer", "kind": "game", "location": "TranceFlow"},
        ).json()

    def test_a_blocked_gate_answers_409_with_what_is_missing(self, client):
        """Calibrated: returning 200 on GateBlocked fails this.

        A caller that gets 200 has been told the gate opened. The unmet
        criteria travel in the body so nobody has to make a second call to
        find out what stopped them.
        """
        item = self._deliverable(client)
        r = client.post(f"/townhall/plm/deliverables/{item['id']}/advance", json={})
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["stage"] == "concept"
        assert [c["id"] for c in detail["unmet"]] == ["concept.business-case"]

    def test_an_evidenced_gate_advances_over_http(self, client):
        item = self._deliverable(client)
        client.post(
            f"/townhall/plm/deliverables/{item['id']}/evidence",
            json={"criterion_id": "concept.business-case", "reference": "BC-1"},
        )
        r = client.post(
            f"/townhall/plm/deliverables/{item['id']}/advance", json={"approver": "tristuran"}
        )
        assert r.status_code == 200
        assert r.json()["stage"] == "initiation"

    def test_failed_evidence_over_http_still_blocks(self, client):
        """Calibrated: defaulting outcome to pass regardless of the body fails this."""
        item = self._deliverable(client)
        client.post(
            f"/townhall/plm/deliverables/{item['id']}/evidence",
            json={
                "criterion_id": "concept.business-case",
                "reference": "BC-1",
                "outcome": "fail",
            },
        )
        assert (
            client.post(f"/townhall/plm/deliverables/{item['id']}/advance", json={}).status_code
            == 409
        )

    def test_a_lost_advance_race_is_a_409_not_a_500(self, client):
        """Calibrated: dropping the GateAlreadyPassed handler fails this.

        Two operators can press the same gate at once; the conditional UPDATE
        picks a winner and the loser raises. Unhandled, that reaches the
        client as a 500 — an operator reading it as a platform fault and
        re-filing evidence that is already filed. The gate worked, so the
        answer is the same 409 the blocked case gets, naming the stage the
        deliverable actually reached.
        """
        from src.townhall import plm as plm_module
        from src.townhall.plm import GateAlreadyPassed, Stage

        item = self._deliverable(client)

        def _lose_the_race(deliverable_id, approver="system"):
            raise GateAlreadyPassed(deliverable_id, Stage.CONCEPT, Stage.INITIATION)

        plm_module._service.advance = _lose_the_race
        r = client.post(f"/townhall/plm/deliverables/{item['id']}/advance", json={})
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert detail["error"] == "gate already passed"
        assert detail["current_stage"] == "initiation"

    def test_blank_evidence_metadata_is_a_400_not_a_500(self, client):
        """Calibrated: dropping the ValueError handler fails this.

        `submit_evidence` refuses a blank reference, because evidence nobody
        can look up is not evidence. That refusal is the caller's fault and
        has to read as one over HTTP.
        """
        item = self._deliverable(client)
        r = client.post(
            f"/townhall/plm/deliverables/{item['id']}/evidence",
            json={"criterion_id": "concept.business-case", "reference": "   "},
        )
        assert r.status_code == 400

    def test_an_unknown_criterion_is_a_400_not_a_stored_record(self, client):
        item = self._deliverable(client)
        r = client.post(
            f"/townhall/plm/deliverables/{item['id']}/evidence",
            json={"criterion_id": "design.vibes", "reference": "x"},
        )
        assert r.status_code == 400

    def test_an_unknown_deliverable_is_a_404(self, client):
        assert client.get("/townhall/plm/deliverables/PLM-NOPE").status_code == 404

    def test_criteria_can_be_narrowed_to_a_kind_and_stage(self, client):
        r = client.get("/townhall/plm/criteria", params={"kind": "image", "stage": "build"})
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_a_kind_without_a_stage_is_rejected(self, client):
        """Calibrated: silently ignoring a lone filter fails this.

        Answering the full criteria list to a request that asked for one
        kind's would tell a caller an image needs a build artefact.
        """
        r = client.get("/townhall/plm/criteria", params={"kind": "image"})
        assert r.status_code == 400


class TestTheGeneratedDocumentation:
    """The policy and procedure are rendered from the criteria, not written beside them."""

    def test_the_committed_document_matches_the_criteria(self):
        """Calibrated: editing docs/governance/PLM-GATES.md by hand fails this.

        A governance document that drifts from the control it describes is
        worse than none: it is consulted precisely when somebody has decided
        not to read the code.
        """
        from scripts.generate_plm_docs import main

        assert main(["--check"]) == 0

    def test_every_criterion_appears_in_the_rendered_document(self):
        """Calibrated: rendering only mandatory criteria fails this.

        release.lessons is optional and still has to be documented, or nobody
        knows it can be asked for.
        """
        from scripts.generate_plm_docs import render

        rendered = render()
        for crit in CRITERIA:
            assert crit.id in rendered, crit.id

    def test_the_document_states_which_kinds_each_criterion_applies_to(self):
        """Calibrated: dropping the matrix section fails this.

        "Required for a game, not for an image" is the part a reader needs
        and the part a prose summary always loses.
        """
        from scripts.generate_plm_docs import render

        rendered = render()
        assert "## Criteria by deliverable kind" in rendered
        assert "build.artefact-registered" in rendered

    def test_the_check_is_wired_into_ci(self):
        """Calibrated: removing the step from ci.yml fails this.

        A drift check nothing runs is the same class of defect as the gate
        that only warned.
        """
        import pathlib

        ci = pathlib.Path(__file__).resolve().parent.parent / ".github/workflows/ci.yml"
        assert "scripts/generate_plm_docs.py --check" in ci.read_text()


class TestReviewFindings:
    """Behaviour added after review. Each names the defect it closes."""

    def test_blank_evidence_is_refused(self, plm):
        """Calibrated: dropping the reference check fails this.

        Evidence is a pointer to the thing that was done. Without one the
        gate opens on an assertion, which is the state this module exists to
        end.
        """
        item = _game(plm)
        with pytest.raises(ValueError, match="reference"):
            plm.submit_evidence(item.id, "concept.business-case", "   ", Outcome.PASS, "tester")

    def test_evidence_with_no_recorder_is_refused(self, plm):
        item = _game(plm)
        with pytest.raises(ValueError, match="who recorded"):
            plm.submit_evidence(item.id, "concept.business-case", "BC-1", Outcome.PASS, " ")

    def test_a_second_advance_over_the_same_boundary_is_refused(self, plm):
        """Calibrated: making the UPDATE unconditional fails this.

        The stage is read before the lock, so two callers can both evaluate
        the same gate as open. The UPDATE is conditional on the stage still
        being what was evaluated, so the second one changes no row. Without
        that, both write a gate decision for a boundary crossed once.
        """
        from src.townhall.plm import GateAlreadyPassed

        item = _game(plm)
        _pass(plm, item, "concept.business-case")
        plm.advance(item.id, approver="tristuran")

        # A caller holding the pre-advance view, replayed.
        stale = plm.get(item.id)
        object.__setattr__(stale, "stage", Stage.CONCEPT)
        with pytest.raises(GateAlreadyPassed):
            plm._advance_from(stale, approver="tristuran")

        assert len(plm.history(item.id)) == 1

    def test_a_refused_second_advance_does_not_move_the_stage(self, plm):
        from src.townhall.plm import GateAlreadyPassed

        item = _game(plm)
        _pass(plm, item, "concept.business-case")
        plm.advance(item.id, approver="tristuran")
        stale = plm.get(item.id)
        object.__setattr__(stale, "stage", Stage.CONCEPT)
        with pytest.raises(GateAlreadyPassed):
            plm._advance_from(stale, approver="tristuran")
        assert plm.get(item.id).stage is Stage.INITIATION

    def test_events_use_the_enum_not_parallel_string_literals(self):
        """Calibrated: reverting to raw strings fails this.

        The enum is the bus's canonical naming. A producer holding its own
        copies lets the two drift, and a rename in one silences the other
        with no error.
        """
        source = (
            __import__("pathlib").Path(__file__).resolve().parent.parent / "src/townhall/plm.py"
        ).read_text()
        from src.event_bus.types import PlatformEventType

        plm_members = [m for m in PlatformEventType if m.name.startswith("PLM_")]
        assert '_emit("plm.' not in source
        assert source.count("PlatformEventType.PLM_") == len(plm_members)

    def test_every_plm_event_member_is_actually_emitted(self):
        """A member nothing emits is a name, not an event."""
        import re

        from src.event_bus.types import PlatformEventType

        source = (
            __import__("pathlib").Path(__file__).resolve().parent.parent / "src/townhall/plm.py"
        ).read_text()
        emitted = set(re.findall(r"PlatformEventType\.(PLM_\w+)", source))
        declared = {m.name for m in PlatformEventType if m.name.startswith("PLM_")}
        assert declared == emitted


class TestLogInjection:
    def test_a_newline_in_a_location_cannot_forge_a_log_record(self, plm, caplog, monkeypatch):
        """Calibrated: logging the raw value fails this.

        `location` arrives in a request body. An unsanitised newline in it
        splits the log line, so an attacker writes whatever second record
        they like — into the file an auditor reads to find out what
        happened.

        The resolver has to be made to raise. It answers an unknown location
        with an *unresolved* ownership record rather than an exception —
        deliberately, so a bad service string never becomes a plausible
        owner — and the log line lives only on the failure path. A test that
        did not force it asserted over zero log records and passed under the
        mutation it names.
        """
        import logging

        from src.townhall import itsm

        def _raise(_service):
            raise RuntimeError("identity spine down")

        monkeypatch.setattr(itsm, "resolve_ownership", _raise)

        forged = "TranceFlow\nplm: ownership for Infinity: granted"
        with caplog.at_level(logging.DEBUG, logger="tranc3.townhall.plm"):
            plm.create(title="A game", kind=DeliverableKind.GAME, location=forged)

        messages = [r.getMessage() for r in caplog.records if "ownership" in r.getMessage()]
        assert messages, "the failure path did not log, so nothing was tested"
        for message in messages:
            assert "\n" not in message

    def test_the_deliverable_still_records_the_location_it_was_given(self, plm):
        """Sanitising the log must not sanitise the record.

        The log is a narrative; the row is the fact. Scrubbing the stored
        value would lose what the caller actually asked for.
        """
        item = plm.create(title="A game", kind=DeliverableKind.GAME, location="TranceFlow")
        assert plm.get(item.id).location == "TranceFlow"


class TestTheGateIsReadInsideTheWriteTransaction:
    """The window between deciding and writing, and why it had to close.

    The conditional UPDATE in `_advance_from` is conditional on the *stage*,
    so it catches two callers advancing the same deliverable. It cannot catch
    a FAIL arriving from `submit_evidence` after the gate was evaluated and
    before the stage was written: that changes no stage, the row still
    matched, and the deliverable advanced on evidence already superseded.
    This module documents that the latest evidence wins; that window was the
    one place it did not.
    """

    @staticmethod
    def _record_transaction_state(plm, monkeypatch) -> list[bool]:
        """Note whether a write transaction was open each time the gate was read."""
        seen: list[bool] = []
        original = plm._gate_status_for

        def _watched(item):
            seen.append(plm._conn.in_transaction)
            return original(item)

        monkeypatch.setattr(plm, "_gate_status_for", _watched)
        return seen

    def test_the_passing_gate_is_evaluated_inside_the_transaction(self, plm, monkeypatch):
        item = _game(plm)
        for criterion in criteria_for(item.kind, item.stage):
            _pass(plm, item, criterion.id)
        seen = self._record_transaction_state(plm, monkeypatch)

        plm.advance(item.id)

        assert seen, "the gate must actually be evaluated"
        assert all(seen), (
            "the gate was read outside the write transaction — a concurrent FAIL "
            "landing here would be invisible to the decision that follows it"
        )

    def test_a_transaction_left_open_by_an_earlier_failure_is_discarded(self, plm):
        """The "already in one, carry on" reading was itself the hole.

        A transaction left open by an earlier failed write makes
        `in_transaction` true. Skipping BEGIN IMMEDIATE on that basis puts the
        gate read back outside the write lock — the exact defect the block
        exists to close, reachable through the guard meant to close it.
        """
        item = _game(plm)
        for criterion in criteria_for(item.kind, item.stage):
            _pass(plm, item, criterion.id)
        # A stale DEFERRED transaction, as an earlier failed write would leave.
        # DEFERRED takes no write lock, so a gate read inside it is exactly as
        # exposed as one taken outside any transaction at all — and the end
        # state is identical either way, which is why this asserts on the
        # statement issued rather than on what the database looks like after.
        plm._conn.execute("BEGIN")
        assert plm._conn.in_transaction

        # set_trace_callback, not a monkeypatched `execute`:
        # `sqlite3.Connection.execute` is a read-only attribute.
        issued: list[str] = []
        plm._conn.set_trace_callback(lambda sql: issued.append(" ".join(sql.split())))
        try:
            plm.advance(item.id)
        finally:
            plm._conn.set_trace_callback(None)

        assert "BEGIN IMMEDIATE" in issued, (
            "the advance carried on inside the stale transaction instead of "
            "opening its own, so the gate read took no write lock"
        )
        assert plm.get(item.id).stage is not Stage.CONCEPT, "the advance must still land"
        assert not plm._conn.in_transaction

    def test_a_blocked_gate_leaves_no_transaction_open(self, plm):
        """An IMMEDIATE transaction held past the refusal blocks every writer."""
        item = _game(plm)
        with pytest.raises(GateBlocked):
            plm.advance(item.id)
        assert not plm._conn.in_transaction
        # And the service is still usable, which is the thing a leaked write
        # lock would take away.
        _pass(plm, item, criteria_for(item.kind, item.stage)[0].id)

    def test_a_fail_visible_at_decision_time_blocks_the_advance(self, plm, monkeypatch):
        """Latest-evidence-wins, exercised at the decision point itself.

        Stated plainly because it matters: this test does NOT discriminate the
        transaction fix. It passes under both mutations above, because the
        injected FAIL is written on the same connection immediately before the
        deciding read either way. It is kept as a scenario check on
        latest-evidence-wins; `test_the_passing_gate_is_evaluated_inside_the
        _transaction` is the one that holds the race closed.
        """
        item = _game(plm)
        criteria = criteria_for(item.kind, item.stage)
        for criterion in criteria:
            _pass(plm, item, criterion.id)

        original = plm._gate_status_for
        calls: list[int] = []

        def _fail_arrives_first(deliverable):
            calls.append(1)
            if len(calls) == 1:
                # Written on the same connection, inside the transaction the
                # advance has already opened — which is exactly what a second
                # process's committed FAIL looks like from in here.
                plm._conn.execute(
                    "INSERT INTO evidence (id, deliverable_id, criterion_id, outcome, "
                    "reference, recorded_by, recorded_at, detail) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        "EV-RACE",
                        deliverable.id,
                        criteria[0].id,
                        Outcome.FAIL.value,
                        "ref",
                        "tester",
                        9_999_999_999.0,
                        "",
                    ),
                )
            return original(deliverable)

        monkeypatch.setattr(plm, "_gate_status_for", _fail_arrives_first)

        with pytest.raises(GateBlocked):
            plm.advance(item.id)
        assert plm.get(item.id).stage is Stage.CONCEPT, "the stage must not have moved"


class TestTheWritesAreGated:
    """Until this existed, every lifecycle write was an unauthenticated call.

    Creating a deliverable, filing PASS evidence, waiving a criterion and
    advancing a stage are all ways of declaring that a control was satisfied,
    and all four were reachable by anyone who could reach the port. Worse, the
    record of who did it came out of the request body — so the audit trail
    said whatever the caller typed.
    """

    @staticmethod
    def _app(tmp_path, monkeypatch, principal):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from auth import get_current_user
        from src.townhall import plm as plm_module
        from src.townhall.plm_routes import router

        service = PlmService(db_path=tmp_path / "plm.db")
        monkeypatch.setattr(plm_module, "_service", service)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: principal
        return TestClient(app), service

    @pytest.fixture
    def as_user(self, tmp_path, monkeypatch):
        client, service = self._app(
            tmp_path, monkeypatch, {"sub": "nobody", "username": "nobody", "role": "user"}
        )
        yield client
        service.close()

    @pytest.fixture
    def as_admin(self, tmp_path, monkeypatch):
        client, service = self._app(
            tmp_path, monkeypatch, {"sub": "boss", "username": "boss", "role": "admin"}
        )
        yield client
        service.close()

    @pytest.mark.parametrize(
        "path,body",
        [
            (
                "/townhall/plm/deliverables",
                {"title": "T", "kind": "game", "location": "TranceFlow"},
            ),
            (
                "/townhall/plm/deliverables/DL-1/evidence",
                {"criterion_id": "concept.business-case", "reference": "R"},
            ),
            (
                "/townhall/plm/deliverables/DL-1/waivers",
                {"criterion_id": "concept.business-case", "reason": "because"},
            ),
            ("/townhall/plm/deliverables/DL-1/advance", {}),
        ],
    )
    def test_a_non_admin_cannot_write(self, as_user, path, body):
        """403 before the handler runs — not 404 from the unknown deliverable.

        The order matters: a 404 here would mean the route reached the store
        and merely happened to find nothing, which is authorisation deciding
        after the fact.
        """
        assert as_user.post(path, json=body).status_code == 403

    def test_reads_stay_open_to_a_non_admin(self, as_user):
        """The split is deliberate. Gate state is not a secret; declaring one
        satisfied is what needed the gate."""
        assert as_user.get("/townhall/plm/criteria").status_code == 200
        assert as_user.get("/townhall/plm/deliverables").status_code == 200

    def test_attribution_comes_from_the_token_not_the_body(self, as_admin):
        """An attribution the caller chooses is not attribution."""
        created = as_admin.post(
            "/townhall/plm/deliverables",
            json={
                "title": "A platformer",
                "kind": "game",
                "location": "TranceFlow",
                "requested_by": "somebody-else",
            },
        ).json()
        assert created["requested_by"] == "boss"

        as_admin.post(
            f"/townhall/plm/deliverables/{created['id']}/evidence",
            json={
                "criterion_id": "concept.business-case",
                "reference": "BC-1",
                "recorded_by": "somebody-else",
            },
        )
        as_admin.post(f"/townhall/plm/deliverables/{created['id']}/advance", json={})
        entries = as_admin.get(f"/townhall/plm/deliverables/{created['id']}/history").json()[
            "history"
        ]
        assert [e["approver"] for e in entries] == ["boss"]

    def test_a_principal_with_no_identity_is_refused(self, tmp_path, monkeypatch):
        """Admin role, no name. Writing 'unknown' into a governance record is
        worse than refusing, because the record still reads as attributed."""
        client, service = self._app(tmp_path, monkeypatch, {"role": "admin"})
        try:
            r = client.post(
                "/townhall/plm/deliverables",
                json={"title": "T", "kind": "game", "location": "TranceFlow"},
            )
            assert r.status_code == 403
        finally:
            service.close()
