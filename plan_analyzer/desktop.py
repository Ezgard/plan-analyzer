"""Десктопный лаунчер для Анализатора учебных планов на базе pywebview и FastAPI/Uvicorn."""

import logging
import socket
import sys
import threading
import time
from typing import Optional

import uvicorn
import webview

from plan_analyzer.web.app import app

logger = logging.getLogger("plan_analyzer.desktop")


def find_free_port(start_port: int = 8000) -> int:
    """Поиск свободного порта для локального веб-сервера."""
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(port: int, timeout: float = 10.0) -> bool:
    """Ожидание готовности локального сервера к приему соединений."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.1)
    return False


class DesktopApp:
    def __init__(self, host: str = "127.0.0.1", port: Optional[int] = None):
        self.host = host
        self.port = port or find_free_port()
        self.server: Optional[uvicorn.Server] = None
        self.server_thread: Optional[threading.Thread] = None

    def start_server(self):
        """Запуск uvicorn в фоновом потоке."""
        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(config)

        def run_uvicorn():
            try:
                self.server.run()
            except Exception as e:
                logger.error(f"Ошибка в потоке uvicorn: {e}")

        self.server_thread = threading.Thread(target=run_uvicorn, daemon=True)
        self.server_thread.start()

    def stop_server(self):
        """Остановка uvicorn сервера."""
        if self.server:
            self.server.should_exit = True

    def run(self):
        """Запуск десктопного приложения с нативным окном."""
        self.start_server()

        if not wait_for_server(self.port, timeout=10.0):
            print(f"Ошибка: Не удалось запустить локальный сервер на порту {self.port}")
            self.stop_server()
            sys.exit(1)

        url = f"http://{self.host}:{self.port}"
        print(f"Анализатор учебных планов запущен: {url}")

        window = webview.create_window(
            title="Анализатор учебных планов (Шахтинские планы .plx / .xml)",
            url=url,
            width=1320,
            height=880,
            min_size=(960, 640),
            confirm_close=False,
        )

        try:
            # webview.start блокирует главный поток (Cocoa run loop на macOS)
            webview.start(debug=False)
        finally:
            self.stop_server()


def main():
    app_runner = DesktopApp()
    app_runner.run()


if __name__ == "__main__":
    main()
