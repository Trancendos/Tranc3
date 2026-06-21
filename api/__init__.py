def __getattr__(name: str):
    if name == "app":
        import importlib.util
        from pathlib import Path

        _api_py = Path(__file__).parent.parent / "api.py"
        _spec = importlib.util.spec_from_file_location("_api_root", str(_api_py))
        if _spec is None or _spec.loader is None:
            raise ImportError(f"Could not load api.py from {_api_py}")
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        val = _mod.app
        globals()["app"] = val
        return val
    raise AttributeError(name)
