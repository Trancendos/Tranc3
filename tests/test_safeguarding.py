"""Tranquility's safeguarding path — the one place the estate might notice a crisis.

Before this suite existed the path was inert in three independent ways at once,
and every one of them was invisible:

  1. it assessed ``f"User reported mood: {mood_level.name}"`` -- a synthetic
     string that matches none of I-Mind's crisis patterns, so the result was
     always NONE;
  2. it discarded the returned assessment, ``escalate`` included;
  3. it wrapped the whole thing in ``except Exception: pass``.

Any one of those alone made it useless. The tests here are written against the
consequences a person would actually care about — does a crisis reach a human —
rather than against the shape of the code.
"""

from __future__ import annotations

import logging

import pytest

from src.tranquility.wellbeing import Tranquility


@pytest.fixture
def raised(monkeypatch):
    """Capture incidents instead of writing to the real Town Hall database."""
    incidents: list[dict] = []

    class _Svc:
        def create_incident(self, title, description, *, priority=None, service=None):
            incidents.append(
                {
                    "title": title,
                    "description": description,
                    "priority": getattr(priority, "value", priority),
                    "service": service,
                }
            )
            return type("I", (), {"id": "INC-test"})()

    import src.townhall.itsm as itsm_module

    monkeypatch.setattr(itsm_module, "get_itsm_service", lambda: _Svc())
    return incidents


@pytest.fixture
def tranquility():
    return Tranquility()


class TestACrisisReachesAPerson:
    def test_crisis_text_in_the_notes_raises_an_incident(self, tranquility, raised):
        tranquility.log_mood("u1", 1, notes="I want to die")
        assert len(raised) == 1
        assert raised[0]["priority"] == "p1"
        assert "Safeguarding escalation" in raised[0]["title"]

    def test_self_harm_text_raises_an_incident(self, tranquility, raised):
        tranquility.log_mood("u1", 1, notes="I have been cutting myself again")
        assert raised

    def test_a_low_mood_with_benign_notes_does_not(self, tranquility, raised):
        tranquility.log_mood("u1", 2, notes="tired, long week")
        assert raised == []

    def test_a_good_mood_is_not_assessed_at_all(self, tranquility, raised):
        tranquility.log_mood("u1", 5, notes="I want to die")
        # Deliberate: the assessment only runs on a low mood. Recorded so that
        # widening the trigger is a decision somebody makes on purpose.
        assert raised == []


class TestTheNotesAreWhatGetAssessed:
    def test_the_old_synthetic_string_could_never_have_escalated(self):
        """A regression guard on the exact bug, not on its shape.

        `assess` was handed "User reported mood: VERY_LOW". If that string ever
        starts matching, this test is wrong rather than the code -- but while it
        does not, any reimplementation that assesses the mood label instead of
        the user's words is provably inert and this pins why.
        """
        from src.imind.protocol import get_imind

        synthetic = get_imind().assess("User reported mood: VERY_LOW")
        assert synthetic.escalate is False
        assert get_imind().assess("I want to die").escalate is True

    def test_an_empty_note_still_records_the_mood_without_escalating(self, tranquility, raised):
        entry = tranquility.log_mood("u1", 1, notes="")
        assert entry is not None
        assert raised == []


class TestTheEscalationIsOwned:
    """An unowned P1 is a page to nobody — the failure this path removes."""

    def test_the_incident_service_resolves_to_a_location_and_an_ai(self, tranquility, raised):
        from src.townhall.itsm import resolve_ownership

        tranquility.log_mood("u1", 1, notes="I want to die")
        assert raised
        ownership = resolve_ownership(raised[0]["service"])
        # The worker directory name "imind" does NOT resolve; the CMDB
        # ServiceID does. Passing the wrong one produces an incident with no
        # accountable owner, which looks identical to a working escalation.
        assert ownership.resolved is True, (
            f"{raised[0]['service']!r} does not resolve: {ownership.unresolved_reason}"
        )
        assert ownership.location
        assert ownership.tier3_ai


class TestTheUsersWordsAreNotCopiedIntoTheIncident:
    def test_the_incident_does_not_quote_the_note(self, tranquility, raised):
        # Named `disclosure`, not `secret`: detect-secrets' keyword heuristic
        # flags a variable called `secret`, and silencing it with an allowlist
        # pragma would tell every future reader that a real credential here was
        # reviewed and waived. There is no credential; there is a person's note.
        disclosure = "I want to die and here is something private"
        tranquility.log_mood("u1", 1, notes=disclosure)
        assert raised
        assert disclosure not in raised[0]["description"]
        assert "private" not in raised[0]["description"]

    def test_the_incident_says_where_to_retrieve_it_instead(self, tranquility, raised):
        tranquility.log_mood("u1", 1, notes="I want to die")
        assert "u1" in raised[0]["description"]
        assert "Tranquility" in raised[0]["description"]


class TestFailuresAreLoudNotSwallowed:
    def test_a_failing_assessment_is_logged(self, tranquility, caplog, monkeypatch):
        import src.imind.protocol as imind_module

        def explode():
            raise RuntimeError("imind down")

        monkeypatch.setattr(imind_module, "get_imind", explode)
        with caplog.at_level(logging.ERROR):
            tranquility.log_mood("u1", 1, notes="I want to die")
        assert "safeguarding assessment failed" in caplog.text

    def test_an_undelivered_escalation_is_logged_loudly(self, tranquility, caplog, monkeypatch):
        # The failure mode the whole method exists to remove: the signal is
        # correct and still reaches nobody.
        import src.townhall.itsm as itsm_module

        def explode():
            raise RuntimeError("town hall down")

        monkeypatch.setattr(itsm_module, "get_itsm_service", explode)
        with caplog.at_level(logging.ERROR):
            tranquility.log_mood("u1", 1, notes="I want to die")
        assert "SAFEGUARDING ESCALATION NOT DELIVERED" in caplog.text

    def test_a_forged_log_line_cannot_be_injected_through_the_user_id(
        self, tranquility, caplog, monkeypatch
    ):
        """The safeguarding trail is the worst place for a fabricated entry.

        A user_id carrying a newline could otherwise write its own line into
        the log — including one claiming an escalation was delivered.
        """
        import src.imind.protocol as imind_module

        def explode():
            raise RuntimeError("imind down")

        monkeypatch.setattr(imind_module, "get_imind", explode)
        forged = "u1\nERROR safeguarding escalation delivered to on-call"
        with caplog.at_level(logging.ERROR):
            tranquility.log_mood(forged, 1, notes="I want to die")

        logged = [r.getMessage() for r in caplog.records]
        assert any("safeguarding assessment failed" in m for m in logged)
        assert not any("\n" in m for m in logged), "a newline reached the log verbatim"

    def test_a_broken_safeguarding_path_still_records_the_mood(self, tranquility, monkeypatch):
        import src.imind.protocol as imind_module

        monkeypatch.setattr(
            imind_module, "get_imind", lambda: (_ for _ in ()).throw(RuntimeError("down"))
        )
        entry = tranquility.log_mood("u1", 1, notes="I want to die")
        assert entry is not None


class TestTheLimitationsAreRealAndRecorded:
    """These assert what the classifier CANNOT do.

    They exist so the I-Mind model card's "known limitations" are backed by
    evidence rather than prose, and so anyone who improves recall finds a test
    telling them exactly what to aim at. A failure here is good news -- it means
    the gap closed and the card needs updating.
    """

    def test_indirect_ideation_is_missed(self):
        from src.imind.protocol import get_imind

        missed = get_imind().assess("I don't want to be here anymore")
        assert missed.escalate is False, (
            "recall improved -- update the I-Mind model card's known limitations"
        )

    def test_third_party_speech_false_positives(self):
        from src.imind.protocol import get_imind

        # Someone describing a friend triggers a CRITICAL crisis assessment.
        # Recorded because the escalation it now produces reaches a person, and
        # they should know this class of alert is expected.
        assert get_imind().assess("my friend is suicidal").escalate is True

    def test_it_is_english_only(self):
        from src.imind.protocol import get_imind

        assert get_imind().assess("je veux mourir").escalate is False
        assert get_imind().assess("I want to die").escalate is True

    def test_inflections_that_used_to_be_missed_are_caught(self):
        from src.imind.protocol import get_imind

        for phrase in ("cutting myself", "killing myself", "ending my life", "self-harming"):
            assert get_imind().assess(phrase).escalate is True, phrase


class TestTheLogSanitiserCoversEveryLineBreakPythonKnows:
    """`str.splitlines()` is the yardstick, not the CR/LF pair.

    The sanitiser stripped \\r and \\n and let U+0085, U+2028 and U+2029
    through — and Python itself splits lines on all three, so any downstream
    tool that splits log lines the way Python does would still have seen a
    forged entry. Asserted against splitlines() rather than a hand-listed set,
    so a new separator Python learns about fails here.
    """

    def test_no_sanitised_value_can_split_into_two_lines(self):
        from Dimensional.sanitize import sanitize_for_log

        for code in (10, 13, 0x85, 0x2028, 0x2029, 11, 12):
            forged = "u1" + chr(code) + "ERROR escalation delivered"
            assert len(sanitize_for_log(forged).splitlines()) == 1, (
                f"U+{code:04X} survives sanitisation and still breaks the line"
            )

    def test_a_benign_id_is_left_readable(self):
        from Dimensional.sanitize import sanitize_for_log

        assert sanitize_for_log("user-42_alpha") == "user-42_alpha"
