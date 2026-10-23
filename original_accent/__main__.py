import traceback

try:
    from .main import main
    main()
except SystemExit:
    raise
except BaseException:
    # Launched windowless (pythonw), so a crash would otherwise vanish. Leave it where it can be found.
    from .paths import LOGS, now
    with open(LOGS / "crash.log", "a", encoding="utf-8") as f:
        f.write(f"\n===== {now()}\n{traceback.format_exc()}")
    raise
