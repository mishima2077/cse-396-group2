"""Rover — Raspberry Pi side package.

Fire-detection rover software, split by responsibility:

    config      all tunable constants (the one place to fine-tune)
    protocol    Arduino wire format: command builders + sensor parsing
    state       thread-safe shared state between threads
    serial_link Arduino serial I/O
    camera      camera discovery + capture
    vision      YOLO fire detection + frame annotation
    autonomy    the alignment/approach FSM (pure logic)
    controller  manual/auto mode policy — decides who drives
    web         Flask + SocketIO dashboard
    app         orchestration / entry point
"""
