import base64, json, os, secrets, shutil, socket, subprocess, time, urllib.error, urllib.request
from pathlib import Path


def canonical(obj):
    return json.dumps(obj, sort_keys=False, separators=(',', ':')).encode()

def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    if os.name != 'nt':
        path.chmod(0o600)

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

class LabError(Exception):
    pass

class RPC:
    """JSON-RPC client that raises actual errors instead of returning None."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.url = f"http://127.0.0.1:{cfg['rpcport']}/"
        auth = f"{cfg['rpcuser']}:{cfg['rpcpassword']}".encode()
        self.auth = 'Basic ' + base64.b64encode(auth).decode()

    def __call__(self, method, *params):
        request = urllib.request.Request(self.url, canonical({
            'jsonrpc': '1.0', 'id': 'ecash-lab',
            'method': method, 'params': list(params),
        }), headers={'Authorization': self.auth, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
        try:
            response = json.loads(raw)
        except (ValueError, UnboundLocalError) as exc:
            raise LabError(f'{method}: invalid RPC response') from exc
        if response.get('error'):
            raise LabError(f"{method}: {response['error']}")
        return response['result']

def wait_tx(rpc, txid, timeout=180):
    if not isinstance(txid, str) or len(txid) != 64:
        raise LabError(f'Invalid transaction ID: {txid!r}')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        tx = rpc('getwallettransaction', txid, True)
        if tx.get('confirmations', 0) >= 1:
            return
        time.sleep(1)
    raise LabError(f'Confirmation timeout for {txid}; transaction may still confirm.')

def executable(folder, name):
    filename = name + ('.exe' if os.name == 'nt' else '')
    local = Path(folder) / filename
    if local.is_file():
        return str(local.resolve())
    found = shutil.which(filename)
    if not found:
        raise LabError(f'Missing {filename}. Use --bin-dir with your MultiChain binaries folder.')
    return found

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def start_node(cfg, folder):
    log_path = Path(folder) / 'node.log'
    with log_path.open('ab') as log:
        kwargs = {'stdout': log, 'stderr': subprocess.STDOUT, 'stdin': subprocess.DEVNULL}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs['start_new_session'] = True
        subprocess.Popen([cfg['daemon'], cfg['chain'], f"-datadir={cfg['datadir']}",
                          '-miningrequirespeers=0', '-listen=0'], **kwargs)
    rpc = RPC(cfg)
    for _ in range(90):
        try:
            if rpc('getinfo')['chainname'] == cfg['chain']:
                return rpc
        except (LabError, OSError):
            pass
        time.sleep(1)
    raise LabError(f'Node not ready. Inspect {log_path}')
