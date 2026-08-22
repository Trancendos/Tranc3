🎯 **What:** The code health issue addressed
Replaced the `pass` statements in the `except Exception:` blocks of the lifecycle hooks (emit_lifecycle and emit_lifecycle_sync) with logging.

💡 **Why:** How this improves maintainability
The previous implementation swallowed any exceptions thrown by lifecycle listeners completely silently. This change ensures any unexpected errors are logged properly along with the exception stack trace. This improves observability and aids in debugging without changing the behavior of the application (as the error is still caught).

✅ **Verification:** How you confirmed the change is safe
Ran python compilation checks, created a simple isolated test that raises an exception from an event hook and confirmed it correctly output the exception as an error without crashing the main application.

✨ **Result:** The improvement achieved
Lifecycle event hook bugs and failures are no longer hidden and are now available in the application logs.
