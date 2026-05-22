#!/usr/bin/env python3
"""Fix remaining f-string logger calls for CWE-117 (log injection) compliance.

Converts f-string logger calls to %-style formatting with sanitize_for_log()
wrapping on user-controlled data.
"""
import os

from shared_core.path_validation import validate_path

# Files and their fixes
FIXES = {
    "shared_core/bus.py": [
        # line 32: logger.info(f"EventBus started (node={self.node_id})")
        (
            'logger.info(f"EventBus started (node={self.node_id})")',
            'logger.info("EventBus started (node=%s)", sanitize_for_log(self.node_id))'
        ),
        # line 37: logger.info(f"EventBus stopped (node={self.node_id})")
        (
            'logger.info(f"EventBus stopped (node={self.node_id})")',
            'logger.info("EventBus stopped (node=%s)", sanitize_for_log(self.node_id))'
        ),
        # line 42: logger.debug(f"Subscribed to {event_type}: {handler.__name__}")
        (
            'logger.debug(f"Subscribed to {event_type}: {handler.__name__}")',
            'logger.debug("Subscribed to %s: %s", sanitize_for_log(event_type), sanitize_for_log(handler.__name__))'
        ),
        # line 94: logger.error(f"Replay handler error: {e}")
        (
            'logger.error(f"Replay handler error: {e}")',
            'logger.error("Replay handler error: %s", sanitize_for_log(e))'
        ),
    ],
    "shared_core/security.py": [
        # line 71: logger.warning(f"JWT verification failed: {e}")
        (
            'logger.warning(f"JWT verification failed: {e}")',
            'logger.warning("JWT verification failed: %s", sanitize_for_log(e))'
        ),
    ],
    "shared_core/registry.py": [
        # line 33: logger.info(f"Registered service: {service.name} @ {service.endpoint}")
        (
            'logger.info(f"Registered service: {service.name} @ {service.endpoint}")',
            'logger.info("Registered service: %s @ %s", sanitize_for_log(service.name), sanitize_for_log(service.endpoint))'
        ),
        # line 48: logger.info(f"Deregistered service: {name}")
        (
            'logger.info(f"Deregistered service: {name}")',
            'logger.info("Deregistered service: %s", sanitize_for_log(name))'
        ),
        # line 87: logger.info(f"Service {name}: {old_health.value} → {health.value}")
        (
            'logger.info(f"Service {name}: {old_health.value} → {health.value}")',
            'logger.info("Service %s: %s → %s", sanitize_for_log(name), old_health.value, health.value)'
        ),
        # line 100: logger.error(f"Watcher error: {e}")
        (
            'logger.error(f"Watcher error: {e}")',
            'logger.error("Watcher error: %s", sanitize_for_log(e))'
        ),
        # line 134: logger.error(f"Health check loop error: {e}")
        (
            'logger.error(f"Health check loop error: {e}")',
            'logger.error("Health check loop error: %s", sanitize_for_log(e))'
        ),
    ],
    "shared_core/optional_import.py": [
        # line 58: logger.debug(f"Lazy-loaded: {module_name}")
        (
            'logger.debug(f"Lazy-loaded: {module_name}")',
            'logger.debug("Lazy-loaded: %s", sanitize_for_log(module_name))'
        ),
    ],
    "main_2060.py": [
        # line 44: logger.warning(f"Config not found at {config_path}, using defaults")
        (
            'logger.warning(f"Config not found at {config_path}, using defaults")',
            'logger.warning("Config not found at %s, using defaults", sanitize_for_log(config_path))'
        ),
    ],
    "workers/api-gateway/worker.py": [
        # line 295: logger.info(f"http method={request.method} path=/{path} status={resp.status_code} ms={elapsed*1000:.0f}")
        (
            'logger.info(f"http method={request.method} path=/{path} status={resp.status_code} ms={elapsed*1000:.0f}")',
            'logger.info("http method=%s path=/%s status=%s ms=%.0f", sanitize_for_log(request.method), sanitize_for_log(path), resp.status_code, elapsed * 1000)'
        ),
        # line 304: logger.error(f"Proxy failed: path=/{path} error={e}")
        (
            'logger.error(f"Proxy failed: path=/{path} error={e}")',
            'logger.error("Proxy failed: path=/%s error=%s", sanitize_for_log(path), sanitize_for_log(e))'
        ),
    ],
    "workers/infinity-ws/worker.py": [
        # line 115: logger.info(f"ws_connected: user={user_id}, total={self.total_connections}")
        (
            'logger.info(f"ws_connected: user={user_id}, total={self.total_connections}")',
            'logger.info("ws_connected: user=%s, total=%s", sanitize_for_log(user_id), self.total_connections)'
        ),
        # line 129: logger.info(f"ws_disconnected: user={conn_info.get('user_id', 'unknown')}")
        (
            '''logger.info(f"ws_disconnected: user={conn_info.get('user_id', 'unknown')}")''',
            '''logger.info("ws_disconnected: user=%s", sanitize_for_log(conn_info.get('user_id', 'unknown')))'''
        ),
        # line 239: logger.warning(f"token_verification_failed: {e}")
        (
            'logger.warning(f"token_verification_failed: {e}")',
            'logger.warning("token_verification_failed: %s", sanitize_for_log(e))'
        ),
        # line 385: logger.error(f"ws_error: {e}")
        (
            'logger.error(f"ws_error: {e}")',
            'logger.error("ws_error: %s", sanitize_for_log(e))'
        ),
    ],
    "workers/infinity-auth/worker.py": [
        # line 344: logger.info(f"user_registered: username={user.username}")
        (
            'logger.info(f"user_registered: username={user.username}")',
            'logger.info("user_registered: username=%s", sanitize_for_log(user.username))'
        ),
        # line 398: logger.info(f"user_login: username={credentials.username}")
        (
            'logger.info(f"user_login: username={credentials.username}")',
            'logger.info("user_login: username=%s", sanitize_for_log(credentials.username))'
        ),
    ],
}

def fix_file(filepath, replacements):
    """Apply all replacements to a file."""
    validate_path(filepath, os.getcwd())
    with open(filepath, 'r') as f:
        content = f.read()

    changed = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            changed = True
            print(f"  Fixed: {old[:60]}...")
        else:
            print(f"  NOT FOUND: {old[:60]}...")

    if changed:
        # Add sanitize_for_log import if not already present
        if 'from shared_core.sanitize import sanitize_for_log' not in content:
            # Find the right place to add the import
            if 'import logging' in content:
                content = content.replace(
                    'import logging',
                    'import logging\n\nfrom shared_core.sanitize import sanitize_for_log'
                )
                print(f"  Added sanitize_for_log import")
            else:
                # Add at the top after any docstring/imports
                lines = content.split('\n')
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith('import ') or line.startswith('from '):
                        insert_idx = i + 1
                    elif insert_idx > 0 and not line.startswith('import ') and not line.startswith('from '):
                        break
                lines.insert(insert_idx, 'from shared_core.sanitize import sanitize_for_log')
                content = '\n'.join(lines)
                print(f"  Added sanitize_for_log import at line {insert_idx}")

    if changed:
        validate_path(filepath, os.getcwd())
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  Wrote {filepath}")
    return changed

def main():
    total_fixed = 0
    for filepath, replacements in FIXES.items():
        if not os.path.exists(filepath):
            print(f"SKIP: {filepath} not found")
            continue
        print(f"\nProcessing {filepath}...")
        if fix_file(filepath, replacements):
            total_fixed += 1

    print(f"\n=== Fixed {total_fixed} files ===")

if __name__ == "__main__":
    main()
