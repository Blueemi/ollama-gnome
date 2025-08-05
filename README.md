# OpenAI-compatible GNOME Chat Client

A GNOME-style desktop client for OpenAI-compatible APIs (e.g., OpenAI, local Ollama with OpenAI compatibility). It follows GNOME Human Interface Guidelines (HIG), supports system dark/light mode, and uses your GNOME accent color for primary/UI highlights.

This app provides a clean chat interface with message “bubbles”, a model picker, a settings page for API configuration, and persistence of your settings.

## Features

- GNOME-native UI
  - Single HeaderBar with a centered tab switcher (Chat / Settings)
  - Follows system dark/light appearance using GNOME settings
  - Uses your GNOME accent color (suggested-action) for the “Send” button and active tab
  - Minimal CSS only for spacing and rounded message bubbles; theme controls colors

- OpenAI-compatible API
  - Fetch models from `/v1/models`
  - Send chat completions to `/v1/chat/completions`
  - Works with OpenAI or any OpenAI-compatible backend (e.g., local Ollama server running OpenAI endpoints)

- Settings & Persistence
  - API Key, Base URL, Default Model
  - Saved under `~/.config/openai_gtk_client/settings.json`
  - Settings page separated from chat; saves and returns you to chat

- UX Details
  - Non-blocking network calls via background threads
  - Status InfoBar at the bottom (Ready, Fetching models..., Done, Failed)
  - Chat view with selectable, wrapped text bubbles
  - Keyboard shortcuts

## Requirements

- Linux with GNOME (GTK 3 environment)
- Python 3.x
- PyGObject (GTK 3 bindings)
- Requests (HTTP client)

Install dependencies (Debian/Ubuntu-based):
```bash
sudo apt update
sudo apt install -y python3-gi gir1.2-gtk-3.0
pip3 install --user requests
```

On Fedora:
```bash
sudo dnf install -y python3-gobject gtk3
pip3 install --user requests
```

On Arch:
```bash
sudo pacman -S --needed python-gobject gtk3
pip3 install --user requests
```

## Installation

Clone or place the project directory where you want. The primary file is:
- `ollama_gui/code.py`

No build step is required.

## Run

From the project root:
```bash
python3 ollama_gui/code.py
```

Optional (for testing dark mode forcibly):
```bash
GTK_PREFER_DARK=1 python3 ollama_gui/code.py
```

## Configuration

Settings are accessible via the “Settings” tab in the HeaderBar. They are persisted to:
- `~/.config/openai_gtk_client/settings.json`

Fields:
- API Key: Your OpenAI (or other provider) API key. Leave empty for servers that don’t require it (e.g., some local setups).
- Base URL: The base HTTP endpoint (e.g., `https://api.openai.com/` or `http://localhost:11434/`).
- Default Model: Preferred model ID (fetched via the “Fetch Models” button).

Notes:
- The Base URL should end with a slash; the app normalizes this automatically.
- The model list is fetched from `/v1/models` and parsed to extract `id` or `name` fields.

## Usage

1) Settings
   - Go to “Settings” in the HeaderBar.
   - Enter your API Key (if required), Base URL, and Default Model.
   - Click “Fetch Models” to populate available models.
   - Click “Save Settings” to persist and return to the Chat tab.

2) Chat
   - In the Chat tab, use the model picker and refresh button to choose a model.
   - Type your message in the multiline input field.
   - Press “Send” to get a response in the conversation area.

3) Status
   - Status messages are shown on the InfoBar at the bottom.

## Keyboard Shortcuts

- Ctrl+Enter: Send message
- Ctrl+Comma: Switch to Settings tab

## Dark/Light Mode and Accent Color

- The app follows GNOME’s appearance preferences automatically.
- Dark mode:
  - Reads `org.gnome.desktop.interface color-scheme` (when available).
  - Accepts `GTK_PREFER_DARK=1` to force dark (useful for testing).
- Accent color:
  - The “Send” button and the active tab get the system accent via the `suggested-action` style class.
  - Requires an Adwaita-based theme that supports accent colors (GNOME 45+).

## OpenAI-compatible API Expectations

- Models endpoint: `GET {base_url}/v1/models`
  - Should return either `{ data: [ { id: "...", ... }, ... ] }` or a list with `id`/`name` fields.
- Chat endpoint: `POST {base_url}/v1/chat/completions`
  - Request JSON example:
    ```json
    {
      "model": "gpt-3.5-turbo",
      "messages": [{ "role": "user", "content": "Hello" }],
      "temperature": 0.7
    }
    ```
  - Response is expected to include `choices[0].message.content` (OpenAI chat format), or fallback to `choices[0].text`.

## Files and Structure

- `ollama_gui/code.py` — Main application code
- `~/.config/ollama_gui/settings.json` — User settings (created on first save)

## Troubleshooting

- Fontconfig warning: “using without calling FcInit()”
  - This is generally harmless in GTK apps; GTK initializes Fontconfig internally. You can ignore it unless fonts fail to render.

- Indentation or Python errors
  - Ensure you’re running Python 3. Reinstall dependencies if needed.

- Cannot fetch models
  - Check Base URL, network connectivity, and API Key (if required).
  - Some local servers may not expose `/v1/models` exactly like OpenAI; ensure compatibility mode is enabled.

- “Unauthorized” or 401
  - Ensure your API key is correct and valid for the chosen endpoint.
  - The Authorization header is sent as `Bearer {API_KEY}` if provided.

- Dark mode not applied
  - Confirm GNOME Appearance is set to Dark.
  - Try: `GTK_PREFER_DARK=1 python3 ollama_gui/code.py`.

- Accent color not applied
  - Requires GNOME with accent color support and Adwaita-based theme.
  - The app uses the GNOME `suggested-action` class for accents; custom themes may not support accents.

## Security

- API keys are stored in plaintext JSON at `~/.config/openai_gtk_client/settings.json` for convenience. If this is a concern, prefer a secrets manager or environment variables in a modified build.

## Roadmap / Ideas

- Streaming responses
- Markdown rendering and code block formatting tools
- Sidebar for chat history
- Export/import conversations
- About dialog and shortcuts help window
- GTK4 port with libadwaita widgets
