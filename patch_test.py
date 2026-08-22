def test_get_entity_by_pid_case_insensitivity(self):
    entity = get_entity_by_pid("pid-nxs")
    assert entity is not None
    assert entity.location == "The Nexus"

def test_get_entity_by_pid_none(self):
    assert get_entity_by_pid(None) is None
