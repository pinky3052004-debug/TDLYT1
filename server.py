"""Static server + /state POST (index.html က snapshot/ကီးဂဏန်း သိမ်းရန်)"""
import http.server, json, os

class H(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path.split("?")[0] != "/state":
            self.send_error(404); return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            json.loads(body)
        except ValueError:
            self.send_error(400); return
        os.makedirs("state", exist_ok=True)
        with open("state/state.json", "wb") as f:
            f.write(body)
        self.send_response(204); self.end_headers()
    def log_message(self, *a):
        pass

http.server.ThreadingHTTPServer(("127.0.0.1", 8080), H).serve_forever()
