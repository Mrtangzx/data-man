import signal
import time

from .db import init_db
from .services.bootstrap import seed_defaults
from .services.jobs import LocalDispatcher
from .db import SessionLocal


def main() -> None:
    init_db()
    with SessionLocal() as db:
        seed_defaults(db)
    dispatcher = LocalDispatcher()
    dispatcher.start()

    running = True

    def stop(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        time.sleep(1)
    dispatcher.stop()


if __name__ == "__main__":
    main()

