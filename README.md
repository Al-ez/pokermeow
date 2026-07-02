# PokerMeow

PokerMeow is a multiplayer poker server/client app. The server is authoritative:
all game state, betting, table seating, reconnects, and showdown results live on
the server.

## Desktop GUI

The PySide6 desktop client is an additional presentation layer. The original
CLI client remains available for development and debugging.

Install the GUI dependency:

```powershell
py -m pip install -r requirements-gui.txt
```

Start the existing server:

```powershell
py server.py
```

Then start one GUI client per player:

```powershell
py gui.py
```

Choose **Host Game** to create a table on the connected server, or enter an
existing table ID and choose **Join Game**. "Host" means the player creating
the table; the authoritative `server.py` process must already be running.

The current server starts hands automatically when at least two players are
seated, so seated players are shown as ready and the host-only start control is
informational. The server protocol does not currently define player chat;
server and game messages are shown in the Chat/Table feed panel, while message
sending stays disabled.

GUI modules are separated by responsibility:

```text
pokermeow_gui/views.py        PySide6 widgets
pokermeow_gui/main_window.py  Qt event binding and dialogs
pokermeow_gui/controller.py   Client workflow and protocol decisions
pokermeow_gui/networking.py   Socket JSON transport
```

## Start The Server

On the host computer:

```powershell
python server.py
```

By default the server listens on all interfaces:

```text
0.0.0.0:8765
```

To use another port:

```powershell
python server.py --port 9000
```

## Find The Host's Local IP

On the host computer:

```powershell
ipconfig
```

Look for `IPv4 Address`, usually something like:

```text
192.168.1.23
```

Players on the same Wi-Fi/LAN connect with:

```powershell
python client.py 192.168.1.23 --port 8765
```

## Router Port Forwarding For Internet Play

For friends outside your house, your router must forward traffic to the host PC.

In your router admin page, add a port-forward rule:

```text
Protocol: TCP
External port: 8765
Internal IP: host computer local IPv4, for example 192.168.1.23
Internal port: 8765
```

If you start the server with a different port, use that same port in the router
rule and client command.

Your friend connects using your public IP:

```powershell
python client.py YOUR_PUBLIC_IP --port 8765
```

You can find your public IP by searching "what is my IP" in a browser.

## Windows Firewall

When Windows asks whether to allow Python through the firewall, allow it on
private networks.

If you need to add the rule manually:

1. Open `Windows Defender Firewall`.
2. Click `Advanced settings`.
3. Click `Inbound Rules`.
4. Click `New Rule`.
5. Choose `Port`.
6. Choose `TCP` and enter `8765`.
7. Choose `Allow the connection`.
8. Enable at least `Private`.
9. Name it `PokerMeow Server`.

## Client Usage

Same computer:

```powershell
python client.py 127.0.0.1 --port 8765
```

Same LAN:

```powershell
python client.py HOST_LOCAL_IP --port 8765
```

Different Internet connections:

```powershell
python client.py HOST_PUBLIC_IP --port 8765
```

## Testing

Two clients on one computer:

1. Terminal 1: `python server.py`
2. Terminal 2: `python client.py 127.0.0.1`
3. Terminal 3: `python client.py 127.0.0.1`

Two computers on the same LAN:

1. Host runs `python server.py`.
2. Host finds local IP with `ipconfig`.
3. Friend runs `python client.py HOST_LOCAL_IP --port 8765`.

Two computers on different Internet connections:

1. Host runs `python server.py --port 8765`.
2. Host forwards TCP port `8765` to the host computer's local IPv4.
3. Host allows TCP port `8765` through Windows Firewall.
4. Friend runs `python client.py HOST_PUBLIC_IP --port 8765`.

Disconnect and reconnect:

1. Join a table and start a hand.
2. Close one client window.
3. Reopen the client and connect to the same server.
4. Join the same table and use the same player name.

## Troubleshooting

If same-computer testing fails, the server is probably not running or the port is
wrong.

If LAN testing fails, check Windows Firewall and confirm both computers are on
the same Wi-Fi/LAN.

If Internet testing fails, check:

- Router port forwarding uses TCP.
- External and internal ports match the server port.
- Internal IP matches the host computer's current IPv4.
- Windows Firewall allows inbound TCP on the server port.
- Your friend is using your public IP, not your local `192.168.x.x` IP.
- Your ISP may use CGNAT, which can prevent normal port forwarding.
