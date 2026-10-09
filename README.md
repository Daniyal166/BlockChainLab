# MultiChain vehicle trust midterm

Selected paper: Singh et al., *Blockchain-Based Adaptive Trust Management in Internet of Vehicles Using Smart Contract*, DOI https://doi.org/10.1109/TITS.2020.3004041.

This is a small teaching adaptation, not a full reproduction of Ethereum, vehicle networking or sharding. It adds speed and position plausibility checks, addressing part of the conclusion's proposed misbehavior-detection work. Python runs the decision rules; MultiChain stores signed evidence, enforces stream permissions and transfers actual TrustPoint assets.

## Windows quick start

Requirements: working MultiChain 2.3.3 binaries and Python 3.10 or later. No pip packages are needed for the lab. Extract this ZIP first; do not run from inside the ZIP.

Open PowerShell in the extracted `midterm_trust` folder:

```powershell
python .\trust_lab.py setup --bin-dir "$env:USERPROFILE\Downloads\multichain-windows-2.3.32"
python .\trust_lab.py demo
python .\trust_lab.py status
```

If `python` is not recognized, use `py -3` or your full Python executable path. The working binary folder in your earlier lab was `multichain-windows-2.3.32`; change `--bin-dir` if yours differs. Setup takes roughly one or two minutes because it waits for confirmations. Existing ecash and chain2 data are untouched. Each setup creates a new `trustXXXXXXXX` chain under `runs` with two data directories and random ports. `runs/latest.txt` identifies the latest run.

`demo` prints each input, report, decision and transaction ID. It runs these scenarios:

1. Normal movement, 36 km/h and 100 m in 10 s: four false accusations are overridden by the plausibility check; no penalty and no reward.
2. Claimed speed 250 km/h: four positive votes plus failed check cause a one-point penalty and 7/5/5/5 TrustPoint rewards.
3. Movement of 4,800 m in 10 s: four positive votes plus failed check cause a second penalty. V5 starts at trust 1 for a short demo, so its trust becomes -1 and it is revoked.
4. A repeat decision is rejected; a direct publication from the revoked address is rejected by MultiChain.

Expected final values (verify your own TXIDs, which will differ):

| Vehicle | Trust | TrustPoint balance | Revoked |
|---|---:|---:|---|
| V1 | 7 | 14 | No |
| V2 | 7 | 10 | No |
| V3 | 7 | 10 | No |
| V4 | 7 | 10 | No |
| V5 | -1 | 0 | Yes |

The demo cannot be rerun on the same chain, to avoid repeated rewards. Use another `setup` if you want a fresh run.

## Enter your own input

Make a fresh chain, then run interactive instead of demo:

```powershell
python .\trust_lab.py setup --bin-dir "$env:USERPROFILE\Downloads\multichain-windows-2.3.32"
python .\trust_lab.py interactive
```

Enter `0`, `10`, `0`, `100`, `250` for start time, end time, start position, end position and speed. Enter `y` for all four reporters. You should see a speed flag, V5 trust 0 and 22 total reward points distributed. Repeat interactive with an impossible position to demonstrate revocation. Use `n` for at least two votes to show that a tie does not penalize even a flagged sample. Inputs model a straight road in metres and seconds; they are synthetic sensor readings.

## Verify directly using the MultiChain CLI

Run these PowerShell commands in the package directory. The configuration is loaded from your own current run; no example chain name or TXID needs replacing.

```powershell
$run = (Get-Content .\runs\latest.txt -Raw).Trim()
$c = Get-Content "$run\config.json" -Raw | ConvertFrom-Json
$cli = "$env:USERPROFILE\Downloads\multichain-windows-2.3.32\multichain-cli.exe"
& $cli $c.chain "-datadir=$($c.admin.datadir)" getinfo
& $cli $c.chain "-datadir=$($c.rsu.datadir)" getinfo
& $cli $c.chain "-datadir=$($c.admin.datadir)" getblockchainparams
& $cli $c.chain "-datadir=$($c.admin.datadir)" listpermissions
& $cli $c.chain "-datadir=$($c.rsu.datadir)" liststreams
& $cli $c.chain "-datadir=$($c.rsu.datadir)" liststreamitems decisions false 100
& $cli $c.chain "-datadir=$($c.admin.datadir)" getaddressbalances $c.vehicles.V1
& $cli $c.chain "-datadir=$($c.admin.datadir)" getaddressbalances $c.vehicles.V5
```

For raw transaction verification, copy your printed **Atomic decision + rewards TXID**:

```powershell
$txid = Read-Host "Paste the speed decision TXID"
& $cli $c.chain "-datadir=$($c.rsu.datadir)" getrawtransaction $txid 1
```

You will see actual TrustPoint outputs and a `decisions` stream item in the same transaction. Trust values are JSON state, not transferable assets; reward points are actual assets.

## Parameters and underlying setup commands

The Python program performs these operations with absolute data paths and generated credentials. Parameters are set before genesis and recorded in `admin/<chain>/params.dat`.

```text
multichain-util create <chain> -datadir=<admin-directory> -target-block-time=2 -mining-diversity=0 -anyone-can-connect=false -anyone-can-send=false -anyone-can-receive=false -anyone-can-create=false -anyone-can-issue=false -anyone-can-mine=false
multichaind <chain> -datadir=<admin-directory> -port=<p2p-A> -rpcport=<rpc-A> -bind=127.0.0.1 -rpcbind=127.0.0.1 -miningrequirespeers=0 -mineemptyrounds=-1
multichaind <chain>@127.0.0.1:<p2p-A> -datadir=<rsu-directory> -port=<p2p-B> -rpcport=<rpc-B> -bind=127.0.0.1 -rpcbind=127.0.0.1 -miningrequirespeers=0 -mineemptyrounds=-1
multichain-cli <chain> -datadir=<admin-directory> grant <joining-address> connect,send,receive
```

Then the joining node is restarted using the same seed address. Four restricted streams are created and both nodes subscribe. Each vehicle gets `send,receive`, `telemetry.write` and `reports.write` (one stream-specific grant call at a time). RSU gets `decisions.write`. The initial admin address retains administration, creation, issuance and mining authority. `issue <rsu-address> TrustPoint 10000 1` funds rewards. A `registry` item binds each vehicle ID to its address and initial trust. The code is the executable reference for the full RPC sequence.

`target-adjust-freq` remains the default -1. `mining-diversity=0` and `miningrequirespeers=0` deliberately support one authorized miner in a two-node local lab. This is not a decentralized fault-tolerant deployment or PBFT/PoW experiment. Do not edit chain-defining params.dat after genesis. Recreate the chain if you want different genesis parameters.

## Optional live viewer

Run `python dashboard.py` after starting the nodes and open http://127.0.0.1:8765. It displays live node status, decisions and permissions. Ctrl+C stops only the viewer. The reference screenshots use `capture_console.py`, a read-only RPC verification script, inside a Linux verification viewer.

## Files and evidence

- `trust_lab.py`: setup, demo, interactive inputs, status, restart, recovery and shutdown.
- `node_utils.py`: strict JSON-RPC error handling and disk helpers.
- `test_rules.py`: ten local rule tests (`python -m unittest discover -s . -p test_rules.py`).
- `Midterm_Report.docx` and `Midterm_Report.pdf`: one report in editable and reading formats, covering all eight required sections.
- `evidence/`: real Linux MultiChain 2.3.3 run, raw JSON, original console logs, params.dat and live verification-viewer screenshots. These are not screenshots from your Windows PC. The readings are synthetic; the blockchain transactions are real.
- `verify.ps1`: the CLI checks above, loaded dynamically from your latest run.
- `run_lab.bat`: creates a fresh chain and runs the automatic demo.

Do not submit runtime config.json, wallet.dat or RPC passwords as screenshots. The distributed package excludes wallets and credentials. For your own submission, use Win+Shift+S to capture (1) both getinfo outputs, (2) permissions and streams, (3) normal/abnormal decisions, (4) raw reward outputs and balances, (5) revoked publication failure. The report already contains accurately labelled evidence from the supplied reference run; replace it if your professor requires your own Windows run.

## Recovery and shutdown

```powershell
python .\trust_lab.py stop
python .\trust_lab.py start
python .\trust_lab.py recover
python .\trust_lab.py evidence
```

`--run-dir <path>` can select an older run. Keep each run folder at its original location: config.json contains absolute data paths. `start` expects the original MultiChain binary location.

One local application writer is allowed. A writer.lock prevents concurrent local evaluations. If the process crashed, first ensure no trust_lab process is running, then delete only that run's writer.lock and run `recover`. Do not delete `pending.json`. A pending signed decision is rebroadcast as the same transaction, not rebuilt with another payout. Never run a second copy with a separate config pointing to the same chain. This is an application-level single-writer assumption, not a distributed lock.

A crash before the decision was prepared can leave valid telemetry and reports without a decision; they remain as evidence. The current simple CLI does not resume such partially collected sessions. Use a new session/interactive run after inspecting the chain. Setup failures can leave partial chains; preserve logs, stop that run with `--run-dir`, and create a new one. No rollback of confirmed transactions is claimed.
