# PokerMeow Network Setup

## Same Wi-Fi / Same LAN

Host runs:

```powershell
python server.py
```

The server will print one or more commands like:

```powershell
python client.py 192.168.1.23 --port 8765
```

Friends run that command from the folder containing the poker files.

## Different Houses

Use a private VPN/mesh network such as Tailscale, ZeroTier, or Hamachi.

Recommended simple path:

1. Everyone installs Tailscale.
2. Everyone joins the same Tailscale network.
3. Host runs:

```powershell
python server.py
```

4. Friends connect to the host's Tailscale IP:

```powershell
python client.py HOST_TAILSCALE_IP --port 8765
```

## Notes

- The host must keep `server.py` running.
- Everyone needs the same Python files.
- If Windows Firewall asks, allow Python on private networks.
- Do not expose this directly to the public internet yet; use LAN or a private VPN.
