with open("tests/test_entities.py", "r") as f:
    content = f.read()

new_tests = """    def test_get_entity_by_pid_case_insensitivity(self):
        entity = get_entity_by_pid("pid-nxs")
        assert entity is not None
        assert entity.location == "The Nexus"

    def test_get_entity_by_pid_none(self):
        assert get_entity_by_pid(None) is None
"""

content = content.replace('    def test_get_entity_by_aid(self):', new_tests + '\n    def test_get_entity_by_aid(self):')

with open("tests/test_entities.py", "w") as f:
    f.write(content)
