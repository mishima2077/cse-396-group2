#!/usr/bin/env python3
"""Flask + SocketIO dashboard layer.

Thin: HTTP routes and socket handlers only *delegate* to the controller and
read from shared state. No motor/mode policy lives here.
"""

from __future__ import annotations

import time

from flask import Flask, Response, render_template, request, jsonify
from flask_socketio import SocketIO

from rover.config import PI_DIR

TEMPLATES_DIR = PI_DIR / "templates"
STATIC_DIR    = PI_DIR / "static"


def create_app(state):
    """Build the Flask app + SocketIO server with the HTTP routes wired.

    Socket handlers are registered separately (see register_socket_handlers)
    because they need the controller, which is built after the logger that
    depends on this socketio instance.
    """
    app = Flask(__name__, template_folder=str(TEMPLATES_DIR),
                static_folder=str(STATIC_DIR))
    app.config["SECRET_KEY"] = "rover-dash"
    socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/video_feed")
    def video_feed():
        return Response(_mjpeg_generate(state),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/sensors")
    def sensors():
        return jsonify(state.get_sensors().as_dict())

    return app, socketio


def register_socket_handlers(socketio, controller):
    """Wire the WebSocket events to the controller."""

    @socketio.on("connect")
    def on_connect():
        # Sync the newly connected client's toggle to the server's mode.
        socketio.emit("mode_changed", {"manual": controller.is_manual}, to=request.sid)

    @socketio.on("set_mode")
    def on_set_mode(data):
        controller.set_mode(bool(data.get("manual", False)))

    @socketio.on("command")
    def on_command(data):
        if not controller.is_manual:
            socketio.emit("log", {"msg": "⚠ Enable Manual mode to send commands", "cls": "warn"},
                          to=request.sid)
            return
        controller.manual_command(str(data.get("cmd", "")), data.get("speed"))


def _mjpeg_generate(state):
    while True:
        frame = state.get_frame()
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        time.sleep(0.033)   # ~30 fps cap
