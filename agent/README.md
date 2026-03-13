# Gemini Telemetry Wrapper

This is a lightweight Python wrapper script that intercepts the input and output of the Gemini CLI and streams it to the central Agent Dashboard via Socket.IO.

## Prerequisites
- Python 3.9+
- A running instance of the central Dashboard Backend.

## Installation
1. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration
The wrapper relies on two environment variables:
- `MACHINE_TOKEN`: (Required) The pre-shared API key for this specific machine, obtained from the Dashboard.
- `DASHBOARD_URL`: (Optional) The URL of the central Dashboard Backend. Defaults to `http://localhost:8000`.

## Containerized Usage (Podman / Docker)

You can also run the agent as a container so that all dependencies are included without polluting your local environment.

1. Build the container image:
   ```bash
   cd agent/
   podman build -t agent-dashboard-agent -f Containerfile .
   ```

2. Run the agent container interactively:
   ```bash
   podman run -it --rm \
     -e DASHBOARD_URL="http://<HOST_IP>:8000/terminal" \
     -e MACHINE_TOKEN="your-secret-token" \
     agent-dashboard-agent bash
   ```
   *(Note: Use your actual host IP address for `DASHBOARD_URL` instead of `localhost` since `localhost` inside the container refers to the container itself.)*

## Usage (Local)
Simply prepend the wrapper script to your normal `gemini` CLI commands:
```bash
export MACHINE_TOKEN="your-secret-token"
./gemini_telemetry_wrapper.py gemini --help
```
If you run the wrapper without arguments, it defaults to executing a standard `bash` shell for testing purposes.
