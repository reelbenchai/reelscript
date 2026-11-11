"""Sequential JSONL transport for a caller-reviewed child process, with no sockets."""
import json
import queue
import subprocess
import threading


class BackendSession:
    def __init__(self, command, timeout=900):
        self.command = command
        self.timeout = timeout
        self.process = None
        self.responses = queue.Queue(maxsize=2)
        self.sequence = 0

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(65537)
                if not line or len(line) > 65536:
                    self.responses.put(None, timeout=1)
                    return
                self.responses.put(line, timeout=1)
        except (OSError, ValueError, queue.Full):
            try:
                self.responses.put_nowait(None)
            except queue.Full:
                pass

    def request(self, episode_id, output):
        if self.process is None:
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                encoding='utf-8', bufsize=1)
            threading.Thread(target=self._read, daemon=True).start()
        if self.process.poll() is not None:
            raise ValueError('backend_session_closed')
        self.sequence += 1
        request = {'request_id': self.sequence, 'episode_id': episode_id, 'output': str(output)}
        try:
            self.process.stdin.write(json.dumps(request) + '\n')
            self.process.stdin.flush()
            line = self.responses.get(timeout=self.timeout)
        except queue.Empty:
            self.close()
            raise ValueError('backend_session_timeout') from None
        except (BrokenPipeError, OSError):
            raise ValueError('backend_session_closed') from None
        try:
            report = json.loads(line) if line else None
        except (ValueError, TypeError):
            report = None
        if not isinstance(report, dict) or type(report.get('request_id')) is not int or report['request_id'] != self.sequence:
            self.close()
            raise ValueError('backend_session_invalid_response')
        return report

    def close(self):
        if self.process is None:
            return
        try:
            self.process.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
