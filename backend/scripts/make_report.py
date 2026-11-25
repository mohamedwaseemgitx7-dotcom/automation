"""Build reports/Smartech_Agent_100_Question_Test.pdf from the JSON results."""
import html, json, pathlib, re, subprocess
R = pathlib.Path(__file__).resolve().parents[2] / "reports"
style = re.search(r"<style>.*?</style>", open(r"D:\D drive\Smartech WhatsApp Bot Plan\plan.html", encoding="utf-8").read(), re.S).group(0)
r4 = json.load(open(R / "test100_qwen3_4b-instruct.json", encoding="utf-8"))
r17 = json.load(open(R / "test100_qwen3_1.7b.json", encoding="utf-8"))
def stats(rows):
    lat = sorted(x["ms"] for x in rows)
    return sum(x["ok"] for x in rows), sum(bool(x["invented"]) for x in rows), sum(x["leak"] for x in rows), lat[49], lat[94]
s4, s17 = stats(r4), stats(r17)
cats = {}
for x in r4:
    c = cats.setdefault(x["category"], [0, 0]); c[0] += x["ok"]; c[1] += 1
e = html.escape
rows = "".join(f'<tr><td>{x["id"]}</td><td>{e(x["category"])}</td><td>{e(x["question"])}</td><td>{e(x["expect"])}</td><td><span class="pill {"v" if x["ok"] else "x"}">{"PASS" if x["ok"] else "FAIL"}</span> {e(x["decision"])}</td><td>{e(x["reply"])}</td><td>{x["ms"]/1000:.1f}s</td></tr>' for x in r4)
fails = "".join(f'<li><b>{x["id"]}</b> {e(x["question"])} → {e(x["decision"])} ({e(x["reason"] or "answered")}): <i>{e(x["reply"][:160])}</i></li>' for x in r4 if not x["ok"])
catrow = "".join(f"<tr><td>{k}</td><td>{v[0]}/{v[1]}</td></tr>" for k, v in cats.items())
doc = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>100-question test</title>{style}
<style>td{{font-size:8.2pt}} .cover{{height:auto;padding:16mm 14mm;break-after:auto}}</style></head><body>
<section class="cover"><div class="tag">SMARTECH · LOCAL AI WHATSAPP AGENT</div><h1>100-question test report</h1>
<div class="sub">25 November 2026 · RTX 3050 4 GB laptop · Smartech knowledge ZIP v2 · no external AI</div></section>
<h2>Result</h2>
<table><tr><th>Model</th><th>Passed</th><th>Invented facts</th><th>Leaked reasoning</th><th>Typical reply time</th><th>Slowest 5%</th></tr>
<tr><td><b>Qwen3 4B Instruct (chosen)</b></td><td><b>{s4[0]}/100</b></td><td>{s4[1]}</td><td>{s4[2]}</td><td>{s4[3]/1000:.1f} s</td><td>{s4[4]/1000:.1f} s</td></tr>
<tr><td>Qwen3 1.7B (first run, older prompt and ZIP v1)</td><td>{s17[0]}/100</td><td>{s17[1]}</td><td>{s17[2]}</td><td>{s17[3]/1000:.1f} s</td><td>{s17[4]/1000:.1f} s</td></tr></table>
<div class="box ok"><b class="t">What this means</b>In 100 questions the bot never invented a price, phone, email, time, or a "we don't offer" claim. When unsure it sends the owner-handoff message instead of guessing. On WhatsApp the customer sees the message read and "typing…" for 2–9 seconds, so a 4 s answer feels natural.</div>
<div class="box warn"><b class="t">Weak spots before real customers</b><ul><li>Tanglish questions are mostly handed to the owner (1/4 answered). Adding Tanglish FAQ lines to the ZIP will help.</li><li>Opening hours: knowledge says only "9 to 10"; owner must confirm "9 am – 10 pm".</li><li>No prices yet: price questions get "team will quote". A price-list CSV in the ZIP enables the catalogue.</li></ul></div>
<h3>By category (4B Instruct)</h3><table style="width:50%"><tr><th>Category</th><th>Pass</th></tr>{catrow}</table>
<h3>Failures (all are safe handoffs or a missing keyword)</h3><ul class="small">{fails}</ul>
<h3>Method</h3><p class="small">Questions are proposed examples, not real customer messages. Each runs through the same pipeline WhatsApp uses: language detection, normalisation, local BGE-M3 search, role check, Qwen3 answer, fact and "not offered" checks. A question fails if the decision is wrong, a required word is missing, any fact or negative claim is not in the knowledge, or the reply mentions documents/AI.</p>
<h2>All 100 questions and replies</h2>
<table><tr><th>ID</th><th>Cat.</th><th>Question</th><th>Expect</th><th>Result</th><th>Reply sent</th><th>Time</th></tr>{rows}</table></body></html>'''
(R / "test100_report.html").write_text(doc, encoding="utf-8")
subprocess.run([r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={R / 'Smartech_Agent_100_Question_Test.pdf'}", (R / "test100_report.html").as_uri()], capture_output=True)
print("report written")
