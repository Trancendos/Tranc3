with open("src/entities/platform.py", "r") as f:
    content = f.read()

content = content.replace(
'''def get_entity_by_pid(pid: str) -> Optional[LocationEntity]:
    """Look up a LocationEntity by its PID-XXX identifier."""
    for entity in PLATFORM_ENTITIES.values():
        if entity.pid == pid:
            return entity
    return None''',
'''def get_entity_by_pid(pid: str) -> Optional[LocationEntity]:
    """Look up a LocationEntity by its PID-XXX identifier (case-insensitive)."""
    if not pid:
        return None
    pid_lower = pid.lower()
    for entity in PLATFORM_ENTITIES.values():
        if entity.pid and entity.pid.lower() == pid_lower:
            return entity
    return None''')

with open("src/entities/platform.py", "w") as f:
    f.write(content)
