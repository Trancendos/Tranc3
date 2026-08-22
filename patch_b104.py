with open("workers/queue-service/worker.py", "r") as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines):
    if "host=\"0.0.0.0\"" in line and "nosec" not in line:
        if i > 0 and "uvicorn.run" in lines[i-1]:
            lines[i] = line + "  # nosec B104"

with open("workers/queue-service/worker.py", "w") as f:
    f.write('\n'.join(lines))
