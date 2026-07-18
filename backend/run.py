"""Development server launcher, picks the first free port from 8000 up."""

import socket

import uvicorn

BASE_PORT = 8000
MAX_TRIES = 20


def find_free_port(start: int = BASE_PORT, tries: int = MAX_TRIES) -> int:
    """Return the first port in the range that accepts a bind."""
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("0.0.0.0", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free port between {start} and {start + tries - 1}")


if __name__ == "__main__":
    port = find_free_port()
    if port != BASE_PORT:
        print(f"Port {BASE_PORT} is busy, using {port} instead")
    print(f"SoftTrainer backend: http://localhost:{port} (the frontend finds this automatically)")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
