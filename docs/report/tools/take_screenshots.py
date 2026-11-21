"""Takes the report screenshots (docs/screenshots/*.png) from a freshly seeded throw-away copy of the app.

It starts its own server on port 8123 with a temporary database (your real data/ folder is never touched),
signs in as the demo users, walks one incident through its whole life, and saves one PNG per page listed in
docs/screenshots/README.md. Needs internet (Bootstrap is loaded from a CDN) and Microsoft Edge.

Run from the repository root (Windows):
    .venv\\Scripts\\python.exe docs\\report\\tools\\take_screenshots.py
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from cdp import Edge  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "docs" / "screenshots"
PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"
PASSWORD = "Password@123"
WIDTH = 1000


class Site:
    def __init__(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="iitsm-shots-"))
        env = {**os.environ, "DATABASE_PATH": str(self.tmp / "shots.db"), "EMAIL_LOG_PATH": str(self.tmp / "emails.log"),
               "ENABLE_SCHEDULER": "false", "SEED_DEMO_DATA": "true", "SIMULATED_TIME": "true"}
        self.log = open(self.tmp / "server.log", "w")
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
                                     cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(120):
            try:
                if httpx.get(f"{BASE}/health", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise RuntimeError("the server did not start; see " + str(self.tmp / "server.log"))

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


class Users:
    """Signed-in httpx clients (used for the actions that do not need a picture) and their cookies."""

    def __init__(self):
        self._clients: dict[str, httpx.Client] = {}

    def client(self, username: str) -> httpx.Client:
        if username not in self._clients:
            client = httpx.Client(base_url=BASE, follow_redirects=True, timeout=30)
            response = client.post("/login", data={"username": username, "password": PASSWORD})
            assert client.cookies.get("session"), f"login failed for {username}: {response.status_code}"
            self._clients[username] = client
        return self._clients[username]

    def cookie(self, username: str) -> str:
        return self.client(username).cookies.get("session")

    def post(self, username: str, path: str, **data):
        response = self.client(username).post(path, data=data)
        assert response.status_code == 200, f"{username} POST {path} -> {response.status_code}"
        return response

    def get(self, username: str, path: str) -> str:
        return self.client(username).get(path).text


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    site, users = Site(), Users()
    edge = Edge(width=WIDTH, height=900)
    taken: list[str] = []
    current = {"w": WIDTH}

    def open_page(user: str | None, path: str):
        edge.clear_cookies()
        if user:
            edge.set_cookie("session", users.cookie(user), BASE)
        current["w"] = 1280 if user and user.startswith("admin") else WIDTH     # the admin menu needs more room
        edge.viewport(current["w"], 900, 1.5)
        edge.goto(BASE + path, settle=1.0)

    def shot(name: str, full: bool = True, height: int = 760):
        width = current["w"]
        edge.evaluate("window.scrollTo(0,0)")
        if full:
            edge.viewport(width, 420, 1.5)                 # a short window, so short pages are not padded with blank space
            time.sleep(0.4)
            total = int(edge.evaluate("Math.ceil(document.documentElement.scrollHeight)"))
            edge.viewport(width, max(total, 600), 1.5)
            time.sleep(0.3)
            edge.screenshot(str(OUT / f"{name}.png"), clip={"x": 0, "y": 0, "width": width, "height": max(total, 600)})
            edge.viewport(width, 900, 1.5)
        else:
            edge.screenshot(str(OUT / f"{name}.png"), clip={"x": 0, "y": 0, "width": width, "height": height})
        taken.append(name)
        print("shot", name)

    def page(user, path, name, **kw):
        open_page(user, path)
        shot(name, **kw)

    try:
        # Reports first: the "probable service problem" depends on the clock, so do it before anything moves it.
        page("admin1", "/admin/reports", "19_reports")
        page(None, "/login", "01_login")
        open_page(None, "/register")
        edge.evaluate("document.querySelectorAll('[required]').forEach(e=>e.removeAttribute('required'));"
                      "document.querySelector('main form').submit()")
        time.sleep(1.5)
        edge.wait_for("document.readyState==='complete'")
        shot("02_register")

        page("emp1", "/employee/dashboard", "03_employee_dashboard")
        page("emp1", "/incidents/new", "04_report_form")

        # Report "Payment page is down" through the form, as an employee would.
        fill = """(()=>{const f=document.querySelector('main form');
          const set=(n,v)=>{f.elements[n].value=v};
          const pick=(n,t)=>{const e=f.elements[n];for(const o of e.options){if(o.text.toLowerCase().includes(t.toLowerCase())){e.value=o.value;return}}
            throw new Error(n+': no option containing '+t+' in '+Array.from(e.options).map(o=>o.text).join(' | '))};
          set('title','Payment page is down');
          set('description','Customers get an error at checkout and cannot pay.');
          pick('service_id','Payment'); pick('category_id','Application'); pick('impact','High'); pick('urgency','High');
          set('affected_users','120'); f.submit(); return true})()"""
        open_page("emp1", "/incidents/new")
        edge.evaluate(fill)
        edge.wait_for("/^\\/incidents\\/\\d+$/.test(location.pathname) && document.readyState==='complete'")
        time.sleep(0.8)
        incident_id = int(edge.evaluate("location.pathname.split('/').pop()"))
        shot("05_incident_created", full=False, height=820)
        page("emp1", f"/incidents/{incident_id}", "06_incident_detail")
        ticket = re.search(r"INC-\d+", users.get("admin1", f"/incidents/{incident_id}")).group(0)
        print("created", ticket, "id", incident_id)

        # Which technician got it?
        tech = next(t for t in (f"tech{i}" for i in range(1, 7)) if ticket in users.get(t, "/tech/dashboard"))
        print("assigned to", tech)
        page(tech, "/tech/dashboard", "07_technician_dashboard")
        users.post(tech, f"/incidents/{incident_id}/acknowledge")
        users.post(tech, f"/incidents/{incident_id}/start")
        users.post(tech, f"/incidents/{incident_id}/note", text="Checked the gateway logs: the card service times out.")
        page(tech, f"/incidents/{incident_id}", "08_technician_actions")
        page("admin1", f"/incidents/{incident_id}", "12_admin_incident_tools")
        page("admin1", f"/incidents/{incident_id}/recommend", "13_recommend_technician")

        users.post(tech, f"/incidents/{incident_id}/request-info", question="Since when does the checkout page fail?")
        page("emp1", f"/incidents/{incident_id}", "09_reply_box")
        page("emp1", "/notifications", "10_notifications")
        users.post("emp1", f"/incidents/{incident_id}/respond", answer="Since about ten minutes ago, for every customer.")
        users.post(tech, f"/incidents/{incident_id}/resolve", summary="Restarted the payment gateway",
                   details="The gateway had run out of connections; restarted it and raised the pool size.")
        # The scheduler is off in this run. Its next 30-second tick would mark the resolved incident as MET,
        # so run that check now, while the incident is resolved and before it is closed.
        users.post("admin1", "/admin/demo/run-sla")
        users.post("emp1", f"/incidents/{incident_id}/verify")
        users.post("emp1", f"/incidents/{incident_id}/close")
        users.post("emp1", f"/incidents/{incident_id}/feedback", rating="5", comment="Fixed quickly, thank you.")
        page("emp1", f"/incidents/{incident_id}", "25_closed_incident")

        page("admin1", "/admin/dashboard", "11_admin_dashboard")
        page("admin1", "/incidents/search?priority=P1", "14_search")
        page("admin1", "/admin/users", "15_users")
        page("admin1", "/admin/services", "16_services")
        page("admin1", "/admin/categories", "16_categories")
        page("admin1", "/admin/sla-policies", "17_sla_policies")
        page("admin1", "/admin/strategies", "18_strategies")
        page("admin1", f"/admin/audit?incident_id={incident_id}", "20_audit_log")

        # Time-dependent pages: move the demo clock and run the checks.
        users.post("admin1", "/admin/demo/advance", minutes="5")
        users.post("admin1", "/admin/demo/run-escalation")
        users.post("admin1", "/admin/demo/advance", minutes="15")
        users.post("admin1", "/admin/demo/run-sla")
        page("admin1", "/admin/sla-violations", "21_sla_violations")
        page("admin1", "/admin/demo", "22_demo_controls")
        page("emp1", "/admin/dashboard", "23_error_403", full=False, height=520)

        edge.clear_cookies()
        edge.set_cookie("session", users.cookie("emp1"), BASE)
        edge.viewport(390, 844, 2.0, mobile=True)
        edge.goto(BASE + "/employee/dashboard", settle=1.2)
        total = int(edge.evaluate("Math.ceil(document.documentElement.scrollHeight)"))
        edge.screenshot(str(OUT / "24_mobile_view.png"), clip={"x": 0, "y": 0, "width": 390, "height": min(total, 1400)})
        taken.append("24_mobile_view")
        print("shot 24_mobile_view")
    finally:
        edge.close()
        site.stop()
    print(f"done: {len(taken)} screenshots in {OUT}")


if __name__ == "__main__":
    main()
