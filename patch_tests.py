import re

with open('tests/test_core_systems.py', 'r') as f:
    content = f.read()

# Replace hardcoded absolute paths to relative or correct absolute paths
content = content.replace('"/home/user/Tranc3/src/event_bus/reactive_stream.py"', '"src/event_bus/reactive_stream.py"')
content = content.replace('"/home/user/Tranc3/src/agent_orchestrator/mapek.py"', '"src/agent_orchestrator/mapek.py"')

with open('tests/test_core_systems.py', 'w') as f:
    f.write(content)
