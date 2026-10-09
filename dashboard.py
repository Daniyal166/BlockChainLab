"""Optional read-only live evidence viewer. No third-party dependencies."""
import argparse, html, json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from trust_lab import collect, load

def page(e, view='overview'):
    esc=lambda x:html.escape(str(x))
    head='''<!doctype html><meta charset="utf-8"><title>MultiChain Vehicle Trust Lab</title>
    <style>body{font:19px Arial,sans-serif;max-width:1000px;margin:30px auto;padding:0 24px;color:#17212b;background:#fff}
    h1{font-size:29px;margin-bottom:6px}h2{font-size:22px;margin-top:28px}p{line-height:1.45}
    .meta{color:#465462}nav{margin:20px 0}a{color:#195179;margin-right:20px}table{border-collapse:collapse;width:100%;margin:16px 0}
    th,td{border:1px solid #ccd1d6;padding:12px;text-align:left}th{background:#edf0f2}
    code{font-size:15px;overflow-wrap:anywhere}small{font-size:16px}.yes{font-weight:bold}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:15px}</style>'''
    body=f'<h1>MultiChain Vehicle Trust Lab</h1><p class="meta">Live RPC evidence | Chain {esc(e["chain"])} | MultiChain 2.3.3</p>'
    body+='<nav><a href="/">Overview</a><a href="/decisions">Decisions</a><a href="/permissions">Permissions</a><a href="/evidence.json">Raw JSON</a></nav>'
    if view=='overview':
        body+='<h2>Two connected nodes</h2><table><tr><th>Node</th><th>Blocks</th><th>Peers</th><th>Errors</th></tr>'
        for label,k in [('Authority and miner','admin_info'),('RSU evaluator','rsu_info')]:
            d=e[k];body+=f'<tr><td>{label}</td><td>{d["blocks"]}</td><td>{d["connections"]}</td><td>{esc(d["errors"] or "None")}</td></tr>'
        body+='</table><h2>Trust and actual asset balances</h2><table><tr><th>Vehicle</th><th>Trust</th><th>TrustPoint</th><th>Revoked</th></tr>'
        for v,s in e['state'].items():
            q=sum(x['qty'] for x in e['balances'][v] if x.get('name')=='TrustPoint')
            body+=f'<tr><td>{v}</td><td>{s["trust"]}</td><td>{q:g}</td><td>{s["revoked"]}</td></tr>'
        body+='</table><p>Three decisions replicated on both nodes: '+str(e['node1_decision_count'])+' / '+str(e['node2_decision_count'])+'</p>'
        body+='<small>Synthetic vehicle readings; real on-chain transactions. One authorized miner; one trusted Python evaluator.</small>'
    elif view=='decisions':
        for item in e['decisions']:
            d=item['data']['json']
            body+=f'<h2>{esc(d["session"])}: {"Misbehavior confirmed" if d["accepted"] else "No penalty"}</h2>'
            body+=f'<p>Checks: {esc(", ".join(d["reasons"]) or "All passed")}<br>Positive votes: {d["yes_votes"]}/{d["reporters"]}; V5 trust: {d["state"]["V5"]["trust"]}<br>Rewards: {esc(d["rewards"])}</p>'
            body+=f'<code>{esc(item["txid"])}</code><br><small>Confirmations: {item["confirmations"]}. Decision and rewards share this transaction.</small>'
    else:
        body+='<h2>Restricted streams</h2><table><tr><th>Stream</th><th>Open to all writers</th><th>Items</th></tr>'
        for s in e['streams']:
            if s['name']=='root':continue
            body+=f'<tr><td>{esc(s["name"])}</td><td>{not s["restrict"]["write"]}</td><td>{s["items"]}</td></tr>'
        body+='</table><h2>Active write permissions by vehicle</h2><table><tr><th>Vehicle</th><th>Telemetry</th><th>Reports</th><th>Decisions</th></tr>'
        regs={x['data']['json']['vehicle']:x['data']['json']['address'] for x in e['registry']}
        for v,addr in regs.items():
            def allowed(stream):
                return any(p['address']==addr and p.get('type')=='write' and p.get('startblock',0)<=e['admin_info']['blocks']<p.get('endblock',4294967295) for p in e['stream_permissions'][stream])
            body+=f'<tr><td>{v}</td>'+''.join(f'<td>{allowed(s)}</td>' for s in ('telemetry','reports','decisions'))+'</tr>'
        body+='</table><p>V5 keeps its address and asset ownership. Revocation removes its telemetry and report writing rights.</p>'
    return (head+body).encode()

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--run-dir');args=p.parse_args()
    root=Path(__file__).resolve().parent
    folder=Path(args.run_dir or (root/'runs/latest.txt').read_text().strip()); cfg=load(folder/'config.json')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                e=collect(cfg)
                content=json.dumps(e,indent=2).encode() if self.path=='/evidence.json' else page(e,self.path.strip('/') or 'overview')
                self.send_response(200);self.send_header('Content-Type','application/json' if self.path=='/evidence.json' else 'text/html; charset=utf-8');self.end_headers();self.wfile.write(content)
            except Exception as exc:
                self.send_response(503);self.end_headers();self.wfile.write(('Nodes unavailable: '+str(exc)).encode())
    print(f'Open http://127.0.0.1:{args.port} (Ctrl+C to stop viewer)',flush=True)
    HTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
if __name__=='__main__':main()
