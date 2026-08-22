import sys

def patch_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Add import to the top
    old_imports = """import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional"""

    new_imports = """import concurrent.futures
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional"""

    if old_imports in content:
        content = content.replace(old_imports, new_imports)
        print("Patched imports successfully")
    else:
        print("Could not find old imports")

    # Remove inline import
    old_code = """        all_items: List[Any] = []
        import concurrent.futures

        if ingestors:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(ingestors)) as executor:
                futures = [executor.submit(ingestor.fetch) for ingestor in ingestors]
                for ingestor, future in zip(ingestors, futures, strict=False):"""

    new_code = """        all_items: List[Any] = []

        if ingestors:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(ingestors)) as executor:
                futures = [executor.submit(ingestor.fetch) for ingestor in ingestors]
                for ingestor, future in zip(ingestors, futures, strict=True):"""

    if old_code in content:
        content = content.replace(old_code, new_code)
        print("Patched code successfully")
    else:
        print("Could not find old code")

    with open(filepath, 'w') as f:
        f.write(content)

patch_file('src/cryptex/cve_scanner.py')
