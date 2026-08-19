# Project Kei Raspberry Pi Client

This client records audio on the Raspberry Pi, sends it to the PC Project Kei API, downloads streamed reply WAV parts, and plays them with `aplay`.

## PC Side

Start all services on the PC:

```powershell
server\start_all_services.bat
```

Find the PC LAN IP:

```powershell
ipconfig
```

Use the IPv4 address, for example `192.168.1.23`.

If the Pi cannot connect, allow Python/Uvicorn through Windows Firewall for port `8000`.

## Pi Side

Install audio tools and Python dependency:

```bash
sudo apt update
sudo apt install -y alsa-utils python3-venv
cd project-kei/pi_client
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Test microphone and speaker:

```bash
arecord -l
aplay -l
arecord -f S16_LE -r 16000 -c 1 -d 3 test.wav
aplay test.wav
```

Run the client:

```bash
python voice_client.py --api http://192.168.1.23:8000
```

Fixed 5 second recording:

```bash
python voice_client.py --api http://192.168.1.23:8000 --seconds 5
```

Use a specific ALSA input device:

```bash
python voice_client.py --api http://192.168.1.23:8000 --device plughw:1,0
```

Disable playback but keep printing events:

```bash
python voice_client.py --api http://192.168.1.23:8000 --no-play
```
