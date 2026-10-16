"""Worker entry point (`python -m app.worker`). Placeholder until T022 adds the job loop."""

import time


def main() -> None:
    print("worker: no job loop yet (T022)", flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
