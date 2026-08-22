import sys

def patch_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    old_code = """        import concurrent.futures
"""

    new_code = """"""

    if old_code in content:
        content = content.replace(old_code, new_code)
        with open(filepath, 'w') as f:
            f.write(content)
        print("Patched successfully")
    else:
        print("Could not find old code")

patch_file('src/cryptex/cve_scanner.py')
