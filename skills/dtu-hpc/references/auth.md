# Authentication

Source: <https://www.hpc.dtu.dk/?page_id=4317> (DTU DCC).

## What DTU requires from outside the DTU network

- SSH key **plus the key passphrase** **plus the DTU password**.
- Key-only or password-only is not enough outside campus/VPN.
- From campus or VPN, the key step is not required — this is why an always-on on-campus relay would remove the password prompt, but that requires hardware and policy approval.
- Login nodes: `login1..N.hpc.dtu.dk` (e.g. `login9.hpc.dtu.dk`). Check host fingerprints against <https://www.hpc.dtu.dk/fp.txt> on first connect.
- `linuxsh` gives a shared interactive shell; GPU dev nodes are `a100sh`, `voltash`, `sxm2sh`.

## One authentication per session

`~/.ssh/config` (copy `templates/ssh_config`):

```sshconfig
Host dtu
  HostName login9.hpc.dtu.dk
  User sXXXXXX
  IdentityFile ~/.ssh/gbar
  IdentitiesOnly yes
  ControlMaster auto
  ControlPath ~/.ssh/cm-%r@%h:%p
  ControlPersist 12h
  ServerAliveInterval 30
  ServerAliveCountMax 3
  TCPKeepAlive yes
```

- `hpc init` detects this `Host` block and writes `~/.config/dtu-hpc/config.ini`; use `--ssh-host <alias>` if the parser misses an included file.
- `ssh-add --apple-use-keychain ~/.ssh/gbar` stores the **key passphrase** in the macOS Keychain (Touch ID/unlock). The DTU password is still typed once.
- The first `ssh dtu` asks passphrase + DTU password. All later `ssh`, `scp`, `rsync`, `bsub` calls reuse the socket with no prompt.
- macOS sleep or a network change can leave a stale socket. `hpc login`/`hpc ensure` run a bounded `BatchMode=yes` remote probe; if it fails, the stale master is closed and authentication is reopened, or you get the exact `ssh -O exit ... && hpc login` command. `hpc doctor` never prompts: a dead or stale master tells you to run `hpc login`.
- Do **not** use `autossh` with a stored password or `sshpass`: it turns a secure second factor into a file on disk.

## Interactive work

- Use `tmux` on the cluster: `hpc shell` attaches/creates `hpc`; `hpc gpu a100` creates `gpu-a100`.
- If SSH drops, reconnect and `tmux attach -t hpc`; the shell and running commands are intact.
- Interactive GPU nodes are shared. Check `nvidia-smi`, prefer idle GPUs, and keep sessions short. Heavy work goes to batch.

## Security checklist

- Never commit or paste the DTU password; never put it in a script or environment file.
- Keep `ControlPath` under `~/.ssh` (mode 600), not `/tmp`.
- Do not enable agent forwarding to the cluster unless a task truly needs it; prefer read-only deploy keys or HF tokens scoped to one repo.
- Verify host fingerprints before trusting a new login node.
