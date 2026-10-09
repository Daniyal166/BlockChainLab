"""Print concise live verification views. Used for the reference screenshots."""
import sys, json
from pathlib import Path
from trust_lab import collect, load
root=Path(__file__).resolve().parent
cfg=load(Path((root/'runs/latest.txt').read_text().strip())/'config.json')
e=collect(cfg)
view=sys.argv[1] if len(sys.argv)>1 else 'overview'
print('MULTICHAIN VEHICLE TRUST LAB - LIVE RPC VERIFICATION')
print('Chain:',e['chain'],'| Real MultiChain 2.3.3 nodes on Linux')
print('Synthetic vehicle inputs; real confirmed transactions.\n')
if view=='overview':
    for name,k in [('Authority / miner','admin_info'),('RSU / evaluator','rsu_info')]:
        info=e[k]; print(name)
        print(json.dumps({x:info[x] for x in ('chainname','version','blocks','connections','errors')},indent=2))
    print('\nVEHICLE    TRUST    TRUSTPOINT    REVOKED')
    for v,s in e['state'].items():
        qty=sum(x['qty'] for x in e['balances'][v] if x.get('name')=='TrustPoint')
        print(f'{v:10} {s["trust"]:5} {qty:13g}    {s["revoked"]}')
    print('\nDecision records on authority / RSU:',e['node1_decision_count'],'/',e['node2_decision_count'])
elif view=='decisions':
    for item in e['decisions']:
        d=item['data']['json']
        print('SESSION:',d['session'].upper())
        print('Result:', 'MISBEHAVIOR CONFIRMED' if d['accepted'] else 'NO PENALTY')
        print('Checks:',', '.join(d['reasons']) or 'all passed')
        print('Positive votes:',d['yes_votes'],'/',d['reporters'],'| V5 trust:',d['state']['V5']['trust'])
        print('Rewards:',d['rewards'])
        print('Atomic decision and reward transaction:')
        print(item['txid'])
        print('Confirmations:',item['confirmations'],'\n')
else:
    print('RESTRICTED STREAMS\n')
    for s in e['streams']:
        if s['name']!='root':print(f'{s["name"]:12} open_write={not s["restrict"]["write"]}  items={s["items"]}')
    print('\nACTIVE VEHICLE WRITE PERMISSIONS\n')
    print('Vehicle    Telemetry     Reports       Decisions')
    for r in e['registry']:
        d=r['data']['json']; v=d['vehicle'];addr=d['address']
        flags=[]
        for stream in ('telemetry','reports','decisions'):
            flags.append(any(p['address']==addr and p['type']=='write' and p['startblock']<=e['admin_info']['blocks']<p['endblock'] for p in e['stream_permissions'][stream]))
        print(f'{v:10} {str(flags[0]):13} {str(flags[1]):13} {flags[2]}')
    print('\nV5 retains its address and asset ownership.')
    print('V5 cannot publish telemetry or reports after revocation.')
    print('Vehicles cannot publish authoritative decisions.')
print('\nSource: getinfo, liststreamitems, listpermissions, getaddressbalances')
if '--hold' in sys.argv:
    (root/'evidence'/('ready_'+view)).write_text('ready')
    input('\nLive evidence captured. Press Enter to close. ')
