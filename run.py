#!/usr/bin/python3
try:
    from umutron.app import main
except ImportError:
    from game_library.app import main
raise SystemExit(main())
