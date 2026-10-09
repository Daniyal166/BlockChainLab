"""Basic MultiChain adaptation of Singh et al. DOI 10.1109/TITS.2020.3004041.
Python 3.10+, standard library only. Separate local wallets; one trusted evaluator.
"""
import argparse, copy, json, math, os, re, secrets, subprocess, sys, time
from pathlib import Path
from node_utils import RPC, LabError, executable, free_port, save, load, wait_tx

STREAMS = ('registry', 'telemetry', 'reports', 'decisions')
RULES = {'max_speed_kmh': 180, 'position_tolerance_m': 20,
         'min_reporters': 4, 'soft_block_seconds': 60, 'version': 'lab-v1'}

def check_sample(s):
    """Two consecutive positions on a straight road; synthetic seconds/metres."""
    fields = ('t0', 't1', 'x0', 'x1', 'speed_kmh')
    if any(type(s.get(k)) not in (int, float) or not math.isfinite(s[k]) for k in fields):
        raise LabError('All sample values must be finite numbers.')
    dt = s['t1'] - s['t0']
    if dt <= 0:
        raise LabError('t1 must be greater than t0.')
    reasons = []
    if not 0 <= s['speed_kmh'] <= RULES['max_speed_kmh']:
        reasons.append('speed_out_of_range')
    if abs(s['x1'] - s['x0']) > RULES['max_speed_kmh'] / 3.6 * dt + RULES['position_tolerance_m']:
        reasons.append('impossible_displacement')
    return reasons

def evaluate(state, suspect, reports, sample, now):
    if suspect not in state or state[suspect]['revoked']:
        raise LabError('Unknown or revoked suspect.')
    seen = set()
    for r in reports:
        v = r['vehicle']
        if v not in state or v == suspect or v in seen:
            raise LabError('Unknown, self or duplicate reporter.')
        if state[v]['revoked'] or state[v]['blocked_until'] > now:
            raise LabError('Reporter is revoked or temporarily blocked.')
        if type(r['suspicious']) is not bool:
            raise LabError('Vote must be a Boolean.')
        seen.add(v)
    reasons = check_sample(sample)
    yes = sum(r['suspicious'] for r in reports)
    # Majority alone cannot punish a plausible sample in this extension.
    accepted = len(reports) >= 4 and yes > len(reports)/2 and bool(reasons)
    new = copy.deepcopy(state)
    rewards = {}
    if accepted:
        new[suspect]['trust'] -= 1
        new[suspect]['blocked_until'] = now + 60
        new[suspect]['revoked'] = new[suspect]['trust'] < 0
        honest = [r['vehicle'] for r in reports if r['suspicious']]
        for i, v in enumerate(honest):
            new[v]['trust'] += 1
            rewards[v] = 7 if i == 0 else 5
    return {'accepted': accepted, 'yes_votes': yes, 'reporters': len(reports),
            'reasons': reasons, 'rewards': rewards, 'state': new}

def launch(cfg, seed=None):
    root = Path(cfg['datadir'])
    with (root / 'daemon.log').open('ab') as f:
        kw = {'stdout': f, 'stderr': subprocess.STDOUT, 'stdin': subprocess.DEVNULL}
        if os.name == 'nt': kw['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else: kw['start_new_session'] = True
        return subprocess.Popen([cfg['daemon'], seed or cfg['chain'],
              '-datadir='+str(root), '-port='+str(cfg['p2pport']),
              '-rpcport='+str(cfg['rpcport']), '-rpcbind=127.0.0.1',
              '-bind=127.0.0.1', '-miningrequirespeers=0', '-mineemptyrounds=-1'], **kw)

def ready(cfg, seconds=50):
    rpc = RPC(cfg)
    for _ in range(seconds):
        try:
            if rpc('getinfo')['chainname'] == cfg['chain']: return rpc
        except (OSError, LabError): pass
        time.sleep(1)
    raise LabError('Node did not start: '+str(Path(cfg['datadir'])/'daemon.log'))

def node_config(folder, chain, daemon):
    folder.mkdir(parents=True)
    (folder/chain).mkdir()
    cfg = dict(chain=chain, daemon=daemon, datadir=str(folder.resolve()),
               rpcport=free_port(), p2pport=free_port(), rpcuser='multichainrpc',
               rpcpassword=secrets.token_urlsafe(24))
    (folder/chain/'multichain.conf').write_text(
        f"rpcuser={cfg['rpcuser']}\nrpcpassword={cfg['rpcpassword']}\nrpcport={cfg['rpcport']}\n", encoding='utf-8')
    return cfg

def setup(args):
    chain = 'trust'+secrets.token_hex(4)
    folder = Path(args.root).resolve()/chain
    folder.mkdir(parents=True)
    daemon = executable(args.bin_dir, 'multichaind')
    util = executable(args.bin_dir, 'multichain-util')
    # util needs the base directory but creates the chain subdirectory itself.
    admin_dir = folder/'admin'; admin_dir.mkdir()
    subprocess.run([util, 'create', chain, '-datadir='+str(admin_dir),
        '-target-block-time=2', '-mining-diversity=0', '-anyone-can-connect=false',
        '-anyone-can-send=false', '-anyone-can-receive=false',
        '-anyone-can-create=false', '-anyone-can-issue=false', '-anyone-can-mine=false'], check=True)
    cfg_a = dict(chain=chain, daemon=daemon, datadir=str(admin_dir),
                 rpcport=free_port(), p2pport=free_port(), rpcuser='multichainrpc',
                 rpcpassword=secrets.token_urlsafe(24))
    (admin_dir/chain/'multichain.conf').write_text(
        f"rpcuser={cfg_a['rpcuser']}\nrpcpassword={cfg_a['rpcpassword']}\nrpcport={cfg_a['rpcport']}\n")
    launch(cfg_a); a=ready(cfg_a)
    cfg_b=node_config(folder/'rsu',chain,daemon)
    cfg={'chain':chain,'admin':cfg_a,'rsu':cfg_b,'folder':str(folder),'rules':RULES}
    save(folder/'config.json',cfg)  # retain diagnostics if join fails
    seed=f"{chain}@127.0.0.1:{cfg_a['p2pport']}"
    proc=launch(cfg_b,seed)
    address=None
    for _ in range(50):
        log=(folder/'rsu'/'daemon.log').read_text(errors='replace')
        match=re.search(r'grant\s+([A-Za-z0-9]+)\s+connect',log)
        if match: address=match.group(1); break
        time.sleep(1)
    if not address: raise LabError('Cannot find joining address; see rsu/daemon.log.')
    print('RSU join address:',address,flush=True)
    tx=a('grant',address,'connect,send,receive'); wait_tx(a,tx)
    proc.wait(timeout=20)
    launch(cfg_b,seed); b=ready(cfg_b)
    cfg['authority']=a('getaddresses')[0]; cfg['evaluator']=address
    cfg['vehicles']={f'V{i}':a('getnewaddress') for i in range(1,6)}
    save(folder/'config.json',cfg)
    for stream in STREAMS:
        wait_tx(a,a('create','stream',stream,False)); a('subscribe',stream); b('subscribe',stream)
    for v,addr in cfg['vehicles'].items():
        wait_tx(a,a('grant',addr,'send,receive'))
        
        for stream in ('telemetry','reports'):
            wait_tx(a,a('grant',addr,stream+'.write'))
    wait_tx(a,a('grant',address,'decisions.write'))
    # Permissioned mining remains with the authority for a minimal two-node lab.
    wait_tx(a,a('issue',address,'TrustPoint',10000,1))
    for v,addr in cfg['vehicles'].items():
        record={'vehicle':v,'address':addr,'trust':1 if v=='V5' else 5,
                'revoked':False,'blocked_until':0}
        wait_tx(a,a('publishfrom',cfg['authority'],'registry',v,{'json':record}))
    save(folder/'config.json',cfg)
    Path(args.root).mkdir(exist_ok=True)
    (Path(args.root)/'latest.txt').write_text(str(folder))
    print('SETUP COMPLETE\nRun directory:',folder,'\nChain:',chain,flush=True)
    status(cfg)
    return cfg

def items(rpc,stream,key=None):
    result=[]; start=0
    while True:
        page=(rpc('liststreamkeyitems',stream,key,False,100,start)
              if key is not None else rpc('liststreamitems',stream,False,100,start))
        result.extend(x for x in page if x.get('confirmations',0)>0)
        if len(page)<100: return result
        start+=100

def synchronize(cfg):
    a,b=RPC(cfg['admin']),RPC(cfg['rsu'])
    height=a('getblockcount')
    for _ in range(60):
        if b('getblockcount') >= height: return
        time.sleep(0.5)
    raise LabError('RSU synchronization timed out; retry after checking peers.')

def ledger_state(cfg):
    synchronize(cfg)
    b=RPC(cfg['rsu']); state={}
    for item in items(b,'registry'):
        if cfg['authority'] not in item['publishers']: continue
        d=item['data']['json']; v=d['vehicle']
        if v in state: raise LabError('Duplicate registry entry.')
        state[v]={k:d[k] for k in ('trust','revoked','blocked_until')}
    if len(state)!=5: raise LabError('Wait for registry synchronization.')
    for item in items(b,'decisions'):
        if cfg['evaluator'] in item['publishers']:
            state=item['data']['json']['state']
    return state

def signed_item(cfg,rpc,stream,key,expected):
    found=[x for x in items(rpc,stream,key) if expected in x['publishers']]
    if len(found)!=1: raise LabError(f'Expected one authenticated {stream} item for {key}.')
    return found[0]

def recover_pending(cfg):
    path=Path(cfg['folder'])/'pending.json'
    if not path.exists(): return
    p=load(path); b=RPC(cfg['rsu'])
    try: known=b('getwallettransaction',p['txid'],True)
    except LabError: known=None
    if known is None: b('sendrawtransaction',p['hex'])
    wait_tx(b,p['txid']); path.unlink()
    print('Recovered the same signed decision:',p['txid'])

def enforce_revocation(cfg):
    a=RPC(cfg['admin'])
    for v,s in ledger_state(cfg).items():
        if s['revoked']:
            addr=cfg['vehicles'][v]
            for stream in ('reports','telemetry'):
                if a('listpermissions',stream+'.write',addr):
                    tx=a('revoke',addr,stream+'.write'); wait_tx(a,tx)
                    print('On-chain write permission revoked:',v,stream,tx)

def run_event(cfg,sample,votes,session=None):
    a,b=RPC(cfg['admin']),RPC(cfg['rsu'])
    session=session or 'event'+secrets.token_hex(4)
    if items(b,'decisions',session): raise LabError('Session already decided; no second reward.')
    state=ledger_state(cfg)
    if state['V5']['revoked']: raise LabError('V5 revoked; create a new lab to start again.')
    check_sample(sample)
    print('\nSESSION',session,'sample=',json.dumps(sample),flush=True)
    key=session+':sample'
    tx=a('publishfrom',cfg['vehicles']['V5'],'telemetry',key,{'json':sample})
    wait_tx(a,tx); print('Telemetry TXID:',tx,flush=True)
    report_refs=[]
    for i,vote in enumerate(votes,1):
        v=f'V{i}'; key=session+':'+v
        rec={'session':session,'vehicle':v,'suspect':'V5','suspicious':vote,'sample_txid':tx}
        rtx=a('publishfrom',cfg['vehicles'][v],'reports',key,{'json':rec})
        wait_tx(a,rtx); report_refs.append(rtx)
        print(f'Report {v}: suspicious={vote}; TXID={rtx}',flush=True)
    # Read confirmed, signed evidence back from the independent RSU node.
    synchronize(cfg)
    sample_item=signed_item(cfg,b,'telemetry',session+':sample',cfg['vehicles']['V5'])
    reports=[]
    for i in range(1,len(votes)+1):
        v=f'V{i}'
        it=signed_item(cfg,b,'reports',session+':'+v,cfg['vehicles'][v]); d=it['data']['json']
        if (d['vehicle']!=v or d['session']!=session or d['suspect']!='V5'
                or d['sample_txid']!=sample_item['txid']): raise LabError('Report binding mismatch.')
        reports.append(d)
    outcome=evaluate(state,'V5',reports,sample_item['data']['json'],int(time.time()))
    outcome.update(session=session,suspect='V5',sample_txid=tx,report_txids=report_refs,rules=RULES)
    outputs={cfg['vehicles'][v]:{'TrustPoint':q} for v,q in outcome['rewards'].items()}
    metadata=[{'for':'decisions','key':session,'data':{'json':outcome}}]
    signed=b('createrawsendfrom',cfg['evaluator'],outputs,metadata,'sign')
    if not signed['complete']: raise LabError('Decision signing incomplete.')
    txid=b('decoderawtransaction',signed['hex'])['txid']
    save(Path(cfg['folder'])/'pending.json',{'hex':signed['hex'],'txid':txid})
    b('sendrawtransaction',signed['hex']); wait_tx(b,txid)
    (Path(cfg['folder'])/'pending.json').unlink()
    print('DECISION:', 'MISBEHAVIOR CONFIRMED' if outcome['accepted'] else 'NO PENALTY',flush=True)
    print('Checks:',outcome['reasons'],'Votes:',outcome['yes_votes'],'/',outcome['reporters'])
    print('Rewards:',outcome['rewards'],'V5 trust:',outcome['state']['V5']['trust'])
    print('Atomic decision + rewards TXID:',txid,flush=True)
    enforce_revocation(cfg)
    return txid,outcome

def status(cfg):
    a,b=RPC(cfg['admin']),RPC(cfg['rsu'])
    print('\n=== LIVE NODE STATUS ===')
    for label,rpc in [('Authority',a),('RSU',b)]:
        info=rpc('getinfo')
        print(label,json.dumps({k:info[k] for k in ('version','chainname','blocks','connections','errors')}))
    print('=== TRUST AND ASSET BALANCES ===')
    state=ledger_state(cfg)
    for v,addr in cfg['vehicles'].items():
        bal=a('getaddressbalances',addr,1)
        qty=sum(x['qty'] for x in bal if x.get('name')=='TrustPoint')
        print(v,'trust=',state[v]['trust'],'revoked=',state[v]['revoked'],'TrustPoint=',qty)
    return state

def demo(cfg):
    if items(RPC(cfg['rsu']),'decisions'): raise LabError('Demo requires a fresh setup (protects against repeat rewards).')
    a=RPC(cfg['admin'])
    try: a('publishfrom',cfg['vehicles']['V1'],'decisions','forged',{'json':{'forged':True}})
    except LabError as e: print('PASS unauthorized decision writer rejected:',e,flush=True)
    else: raise LabError('SECURITY CHECK FAILED: vehicle wrote decision.')
    run_event(cfg,dict(t0=0,t1=10,x0=0,x1=100,speed_kmh=36),[True]*4,'normal')
    run_event(cfg,dict(t0=10,t1=20,x0=100,x1=200,speed_kmh=250),[True]*4,'speed')
    run_event(cfg,dict(t0=20,t1=30,x0=200,x1=5000,speed_kmh=36),[True]*4,'position')
    try: run_event(cfg,dict(t0=0,t1=10,x0=0,x1=100,speed_kmh=36),[True]*4,'speed')
    except LabError as e: print('PASS repeat session blocked:',e)
    else: raise LabError('Duplicate session accepted.')
    try: a('publishfrom',cfg['vehicles']['V5'],'reports','after-revocation',{'json':{'test':True}})
    except LabError as e: print('PASS revoked vehicle write rejected:',e)
    else: raise LabError('Revocation not effective.')
    state=status(cfg)
    assert state['V5']['trust']==-1 and state['V5']['revoked']
    evidence=collect(cfg)
    save(Path(cfg['folder'])/'evidence.json',evidence)
    print('Evidence saved:',Path(cfg['folder'])/'evidence.json')

def collect(cfg):
    synchronize(cfg)
    a,b=RPC(cfg['admin']),RPC(cfg['rsu'])
    decisions=items(b,'decisions')
    return {'environment':'REAL MultiChain 2.3.3 execution', 'chain':cfg['chain'],
        'admin_info':a('getinfo'),'rsu_info':b('getinfo'), 'params':a('getblockchainparams'),
        'permissions':a('listpermissions'),
        'stream_permissions':{s:a('listpermissions',s+'.write') for s in STREAMS},
        'streams':a('liststreams'),
        'decisions':decisions,'registry':items(b,'registry'), 'reports':items(b,'reports'),
        'telemetry':items(b,'telemetry'),'state':ledger_state(cfg),
        'balances':{v:a('getaddressbalances',addr,1) for v,addr in cfg['vehicles'].items()},
        'transactions':{x['txid']:b('getrawtransaction',x['txid'],1) for x in decisions},
        'node2_decision_count':len(decisions),'node1_decision_count':len(items(a,'decisions'))}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['setup','demo','interactive','status','recover','start','stop','evidence'])
    p.add_argument('--bin-dir',default=str(Path.home()/'Downloads'/'multichain-windows-2.3.32'))
    p.add_argument('--root',default=str(Path(__file__).resolve().parent/'runs'))
    p.add_argument('--run-dir')
    args=p.parse_args()
    if args.command=='setup': setup(args); return
    folder=Path(args.run_dir or (Path(args.root)/'latest.txt').read_text().strip())
    cfg=load(folder/'config.json')
    if args.command=='stop':
        for node in ['rsu','admin']: print(RPC(cfg[node])('stop'))
        time.sleep(3)  # let databases flush before the parent shell exits
        return
    if args.command=='start':
        for node in ['admin','rsu']:
            try: RPC(cfg[node])('getinfo')
            except (OSError,LabError): launch(cfg[node]); ready(cfg[node])
        synchronize(cfg)
        for node in ['admin','rsu']:
            for stream in STREAMS: RPC(cfg[node])('subscribe',stream)
        return
    if args.command=='status': status(cfg); return
    if args.command=='evidence': save(folder/'evidence.json',collect(cfg)); return
    lock=folder/'writer.lock'
    try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError: raise LabError('Another writer or stale writer.lock exists. See README recovery instructions.')
    os.close(fd)
    try:
        recover_pending(cfg); enforce_revocation(cfg)
        if args.command=='demo': demo(cfg)
        elif args.command=='interactive':
            print('Enter a synthetic V5 movement. Positions are metres; time is seconds.')
            sample={k:float(input(label)) for k,label in [('t0','Start time: '),('t1','End time: '),
              ('x0','Start position: '),('x1','End position: '),('speed_kmh','Claimed speed km/h: ')]}
            print('Detector flags:',check_sample(sample))
            votes=[]
            for i in range(1,5):
                answer=input(f'V{i}: report suspicious? y/n: ').strip().lower()
                if answer not in ('y','n'): raise LabError('Enter y or n.')
                votes.append(answer=='y')
            run_event(cfg,sample,votes); status(cfg)
    finally: lock.unlink(missing_ok=True)

if __name__=='__main__':
    try: main()
    except (LabError, OSError, ValueError, subprocess.SubprocessError) as e:
        print('\nSTOPPED:',e,'\nPreviously confirmed transactions remain on-chain.',file=sys.stderr)
        sys.exit(1)
