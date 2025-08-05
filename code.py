#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# GNOME-style GUI for OpenAI-compatible APIs
# Features:
# - API key input and persistence
# - Base URL input and persistence (e.g., https://api.openai.com/ or http://localhost:11434/)
# - Model picker with Fetch Models button
# - Prompt input and Send button
# - Response view
# - Non-blocking network calls using threads
# - GNOME HIG styling with HeaderBar, Adwaita theme colors, and dark/light mode following system
# - Settings view separated from Chat view, accessible via a settings button in the HeaderBar
#
# Requirements:
#   - Python 3
#   - PyGObject (GTK 3):
#       sudo apt install python3-gi gir1.2-gtk-3.0
#   - requests:
#       pip install requests
#
# Run:
#   python3 ollama_gui/code.py

import os
import json
import threading
from urllib.parse import urljoin

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib, Gdk

import requests

APP_NAME = "OpenAI-compatible Client"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "openai_gtk_client")
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")


def ensure_config_dir():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
    except Exception:
        pass


def load_settings():
    ensure_config_dir()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_settings(data):
    ensure_config_dir()
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_NAME)
        self.set_default_size(900, 720)
        self.set_border_width(0)

        self.settings = load_settings()

        # Root container
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)

        # HeaderBar (single, GNOME-style) + StackSwitcher
        header = Gtk.HeaderBar(show_close_button=True)
        header.set_title(APP_NAME)
        self.set_titlebar(header)

        # Main stack: Chat view and Settings view
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=250)

        # StackSwitcher centered in HeaderBar
        self.stack_switcher = Gtk.StackSwitcher()
        self.stack_switcher.set_stack(self.stack)
        header.set_custom_title(self.stack_switcher)

        # Keep active tab using GNOME accent on active button
        self.stack.connect("notify::visible-child-name", self._update_stackswitcher_accent)
        GLib.idle_add(self._update_stackswitcher_accent, self.stack, None)

        # Pack content stack into main area
        outer.pack_start(self.stack, True, True, 0)

        # Chat view (GNOME-style bubbles)
        self.chat_page = self._build_chat_page()
        self.stack.add_titled(self.chat_page, "chat", "Chat")

        # Settings view
        self.settings_page = self._build_settings_page()
        self.stack.add_titled(self.settings_page, "settings", "Settings")

        # Footer info bar
        self.info_bar = Gtk.InfoBar()
        self.info_bar.set_message_type(Gtk.MessageType.OTHER)
        self.info_bar.set_show_close_button(False)
        self.info_label = Gtk.Label(label="", xalign=0)
        content = self.info_bar.get_content_area()
        content.pack_start(self.info_label, False, False, 0)
        outer.pack_end(self.info_bar, False, False, 0)
        self.info_bar.show_all()
        self.set_info("Ready")

        # Keyboard shortcuts
        self.add_accel_group(self._build_accel_group())

        # Follow GNOME dark/light mode and style
        self._apply_gnome_style()

        # Restore saved model to the chat picker (if already present in settings)
        saved_model = self.settings.get("model", "")
        if saved_model and hasattr(self, "model_store"):
            self.model_store.append([saved_model])
            self.combo_model.set_active(0)

    def _build_accel_group(self):
        accel_group = Gtk.AccelGroup()
        # Ctrl+Enter to Send (bind to the Send button)
        key, mod = Gtk.accelerator_parse("<Control>Return")
        self.btn_send.add_accelerator("clicked", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        # Global key handler manages Ctrl+Comma (open settings)
        self.add_accel_group(accel_group)
        self.connect("key-press-event", self._on_keypress_accel)
        return accel_group

    def _on_keypress_accel(self, widget, event):
        # Map Ctrl+, to open settings and Ctrl+Enter to send
        try:
            keyval = event.keyval
            state = event.state
            ctrl = state & Gdk.ModifierType.CONTROL_MASK
            if ctrl and keyval in (Gdk.KEY_comma,):
                self.on_open_settings(None)
                return True
            if ctrl and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                if self.btn_send.get_sensitive():
                    self.on_send_clicked(None)
                    return True
        except Exception:
            pass
        return False

    def _apply_gnome_style(self):
        # Follow GNOME Adwaita automatically and honor GNOME dark preference.
        # Priority:
        # 1) GTK_PREFER_DARK env override (for testing)
        # 2) org.gnome.desktop.interface color-scheme = prefer-dark
        # 3) otherwise leave current session/theme as-is
        settings = Gtk.Settings.get_default()

        # 1) Environment override for easy testing
        try:
            val = os.environ.get("GTK_PREFER_DARK", "").strip().lower()
            if val in ("1", "true", "yes"):
                settings.set_property("gtk-application-prefer-dark-theme", True)
            elif val in ("0", "false", "no"):
                settings.set_property("gtk-application-prefer-dark-theme", False)
        except Exception:
            pass

        # 2) Read GNOME interface color-scheme via GSettings if available
        try:
            schema = "org.gnome.desktop.interface"
            key = "color-scheme"
            if Gio.Settings.list_schemas() and schema in Gio.Settings.list_schemas():
                gsettings = Gio.Settings.new(schema)
                cs = gsettings.get_string(key)
                if cs == "prefer-dark":
                    settings.set_property("gtk-application-prefer-dark-theme", True)
        except Exception:
            pass

        # Minimal CSS: spacing and radius only, no custom colors so theme can decide.
        css = b"""
        .chat-container { padding: 12px; }
        .bubble-user, .bubble-assistant, .bubble-system {
            border-radius: 12px;
            padding: 10px 12px;
            margin-top: 6px;
            margin-bottom: 6px;
        }
        .bubble-user { margin-left: 48px; }
        .bubble-assistant { margin-right: 48px; }
        .bubble-system { margin-left: 96px; margin-right: 96px; }
        .input-row { padding: 8px; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


    def _build_chat_page(self):
        # Vertical layout: scroll area with bubbles + input row
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.get_style_context().add_class("chat-container")

        # Scrollable conversation area
        self.chat_list_box = Gtk.ListBox()
        self.chat_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.add(self.chat_list_box)
        vbox.pack_start(scroller, True, True, 0)

        # Input row
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_row.get_style_context().add_class("input-row")

        # Model Combo and Fetch button
        self.model_store = Gtk.ListStore(str)
        self.combo_model = Gtk.ComboBox.new_with_model_and_entry(self.model_store)
        self.combo_model.set_entry_text_column(0)
        self.combo_model.set_hexpand(False)

        btn_fetch_models = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        btn_fetch_models.set_tooltip_text("Fetch models")
        btn_fetch_models.connect("clicked", self.on_fetch_models_clicked)

        # Text entry for chat (multi-line)
        self.entry_chat_buffer = Gtk.TextBuffer()
        self.entry_chat_view = Gtk.TextView(buffer=self.entry_chat_buffer)
        self.entry_chat_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.entry_chat_view.set_size_request(-1, 80)
        entry_scroll = Gtk.ScrolledWindow()
        entry_scroll.set_hexpand(True)
        entry_scroll.set_vexpand(False)
        entry_scroll.add(self.entry_chat_view)

        # Send button
        self.btn_send = Gtk.Button.new_from_icon_name("mail-send-symbolic", Gtk.IconSize.BUTTON)
        self.btn_send.set_label("Send")
        self.btn_send.set_always_show_image(True)
        self.btn_send.get_style_context().add_class("suggested-action")
        self.btn_send.connect("clicked", self.on_send_clicked)

        # Pack input row
        input_row.pack_start(self.combo_model, False, False, 0)
        input_row.pack_start(btn_fetch_models, False, False, 0)
        input_row.pack_start(entry_scroll, True, True, 0)
        input_row.pack_end(self.btn_send, False, False, 0)

        vbox.pack_end(input_row, False, False, 0)
        return vbox

    def _append_bubble(self, role, text):
        # Create a horizontal box to align bubbles left/right
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bubble_frame = Gtk.Frame()
        bubble_frame.set_shadow_type(Gtk.ShadowType.NONE)

        bubble_label = Gtk.Label()
        bubble_label.set_xalign(0)
        bubble_label.set_line_wrap(True)
        bubble_label.set_line_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        bubble_label.set_selectable(True)
        bubble_label.set_text(text)
        bubble_label.set_max_width_chars(60)
        bubble_label.set_width_chars(60)
        bubble_frame.add(bubble_label)

        # Let Adwaita theme dictate colors; only alignment and classes for spacing.
        if role == "user":
            bubble_frame.get_style_context().add_class("bubble-user")
            hb.pack_end(bubble_frame, False, False, 0)
        elif role == "assistant":
            bubble_frame.get_style_context().add_class("bubble-assistant")
            hb.pack_start(bubble_frame, False, False, 0)
        else:
            bubble_frame.get_style_context().add_class("bubble-system")
            hb.set_halign(Gtk.Align.CENTER)
            hb.pack_start(bubble_frame, False, False, 0)

        row = Gtk.ListBoxRow()
        row.add(hb)
        self.chat_list_box.add(row)
        self.chat_list_box.show_all()

        # Auto-scroll to bottom
        adj = self.chat_list_box.get_parent().get_vadjustment()
        GLib.idle_add(lambda: adj.set_value(adj.get_upper() - adj.get_page_size()))

    def _build_settings_page(self):
        grid = Gtk.Grid(column_spacing=12, row_spacing=12, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)

        row = 0
        lbl_api = Gtk.Label(label="API Key:", xalign=0)
        grid.attach(lbl_api, 0, row, 1, 1)
        self.entry_api = Gtk.Entry()
        self.entry_api.set_visibility(False)
        self.entry_api.set_placeholder_text("sk-... or leave empty if not required")
        self.entry_api.set_text(self.settings.get("api_key", ""))
        grid.attach(self.entry_api, 1, row, 2, 1)
        row += 1

        lbl_url = Gtk.Label(label="Base URL:", xalign=0)
        grid.attach(lbl_url, 0, row, 1, 1)
        self.entry_url = Gtk.Entry()
        self.entry_url.set_placeholder_text("https://api.openai.com/ or http://localhost:11434/")
        self.entry_url.set_text(self.settings.get("base_url", "https://api.openai.com/"))
        grid.attach(self.entry_url, 1, row, 2, 1)
        row += 1

        lbl_model = Gtk.Label(label="Default Model:", xalign=0)
        grid.attach(lbl_model, 0, row, 1, 1)
        self.model_store_settings = Gtk.ListStore(str)
        self.combo_model_settings = Gtk.ComboBox.new_with_model_and_entry(self.model_store_settings)
        self.combo_model_settings.set_entry_text_column(0)
        grid.attach(self.combo_model_settings, 1, row, 1, 1)
        btn_fetch_models_settings = Gtk.Button(label="Fetch Models")
        btn_fetch_models_settings.connect("clicked", self._fetch_models_into_settings)
        grid.attach(btn_fetch_models_settings, 2, row, 1, 1)
        row += 1

        btn_save = Gtk.Button(label="Save Settings")
        btn_save.connect("clicked", self.on_save_clicked)
        grid.attach(btn_save, 2, row, 1, 1)

        # Mirror model list to main combo when invoked from settings
        saved_model = self.settings.get("model", "")
        if saved_model:
            self.model_store_settings.append([saved_model])
            self.combo_model_settings.set_active(0)

        return grid

    def _update_stackswitcher_accent(self, stack, _param):
        # Apply GNOME accent only to the active tab button of the StackSwitcher
        if not hasattr(self, "stack_switcher"):
            return False
        try:
            # StackSwitcher in GTK3 is composed of ToggleButtons as children
            for child in self.stack_switcher.get_children():
                if isinstance(child, Gtk.ToggleButton):
                    ctx = child.get_style_context()
                    if child.get_active():
                        ctx.add_class("suggested-action")
                    else:
                        ctx.remove_class("suggested-action")
        except Exception:
            pass
        return False

    def on_save_clicked(self, _button):
        # Persist API settings and default model
        api_key = self.entry_api.get_text().strip() if hasattr(self, "entry_api") else ""
        base_url = self.entry_url.get_text().strip() if hasattr(self, "entry_url") else ""
        default_model = ""
        if hasattr(self, "combo_model_settings") and self.combo_model_settings:
            entry = self.combo_model_settings.get_child()
            if entry:
                default_model = entry.get_text().strip()
        elif hasattr(self, "combo_model") and self.combo_model:
            entry = self.combo_model.get_child()
            if entry:
                default_model = entry.get_text().strip()

        if base_url and not base_url.endswith("/"):
            base_url += "/"

        self.settings["api_key"] = api_key
        self.settings["base_url"] = base_url
        if default_model:
            self.settings["model"] = default_model

        save_settings(self.settings)

        # Mirror default model into chat picker if available
        if default_model and hasattr(self, "model_store"):
            exists = False
            for row in self.model_store:
                if row[0] == default_model:
                    exists = True
                    break
            if not exists:
                self.model_store.append([default_model])
            if hasattr(self, "combo_model"):
                self.combo_model.set_active(0)

        self.set_info("Settings saved")
        # Return to chat view after saving
        self.on_open_chat()

    def fetch_models(self):
        # Shared helper to fetch models from OpenAI-compatible /v1/models
        base_url = (self.entry_url.get_text().strip() if hasattr(self, "entry_url") else "") or "https://api.openai.com/"
        base_url = base_url.rstrip("/") + "/"
        api_key = self.entry_api.get_text().strip() if hasattr(self, "entry_api") else ""

        url = urljoin(base_url, "v1/models")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()

        models = []
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            for item in data["data"]:
                mid = item.get("id") or item.get("name")
                if mid:
                    models.append(mid)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    mid = item.get("id") or item.get("name")
                    if mid:
                        models.append(mid)
                elif isinstance(item, str):
                    models.append(item)

        # Deduplicate preserving order
        seen = set()
        unique = []
        for m in models:
            if m not in seen:
                unique.append(m)
                seen.add(m)
        return unique

    def _fetch_models_into_settings(self, _btn):
        # Use same fetch as chat; then update settings combo
        self.set_info("Fetching models...")

        def worker():
            try:
                models = self.fetch_models()

                def update():
                    if hasattr(self, "model_store_settings"):
                        self.model_store_settings.clear()
                    if hasattr(self, "model_store"):
                        self.model_store.clear()
                    for m in models:
                        if hasattr(self, "model_store_settings"):
                            self.model_store_settings.append([m])
                        if hasattr(self, "model_store"):
                            self.model_store.append([m])
                    if models:
                        if hasattr(self, "combo_model_settings"):
                            self.combo_model_settings.set_active(0)
                        if hasattr(self, "combo_model"):
                            self.combo_model.set_active(0)
                    self.set_info(f"Fetched {len(models)} model(s)")

                GLib.idle_add(update)
            except Exception as e:
                GLib.idle_add(self.set_info, f"Error fetching models: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def on_open_settings(self, _btn):
        # Switch to settings page (StackSwitcher provides the UX in HeaderBar)
        if hasattr(self, "stack"):
            self.stack.set_visible_child_name("settings")

    def on_open_chat(self, _btn=None):
        # Switch back to chat view (StackSwitcher provides the UX in HeaderBar)
        if hasattr(self, "stack"):
            self.stack.set_visible_child_name("chat")

    def on_fetch_models_clicked(self, _button):
        self.set_info("Fetching models...")
        self.model_store.clear()

        def worker():
            try:
                models = self.fetch_models()
                GLib.idle_add(self.populate_models, models)
                GLib.idle_add(self.set_info, f"Fetched {len(models)} model(s)")
            except Exception as e:
                GLib.idle_add(self.set_info, f"Error fetching models: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def populate_models(self, models):
        self.model_store.clear()
        for m in models:
            self.model_store.append([m])
        if len(models) > 0:
            self.combo_model.set_active(0)

    def set_info(self, text):
        if hasattr(self, "info_label") and self.info_label:
            self.info_label.set_text(text)

    def get_selected_model(self):
        # Prefer the chat combo entry text
        entry = None
        if hasattr(self, "combo_model") and self.combo_model:
            entry = self.combo_model.get_child()
            if entry:
                val = entry.get_text().strip()
                if val:
                    return val
        # Fallback to settings combo
        if hasattr(self, "combo_model_settings") and self.combo_model_settings:
            entry2 = self.combo_model_settings.get_child()
            if entry2:
                return entry2.get_text().strip()
        return ""

    def on_send_clicked(self, _button):
        model = self.get_selected_model()
        if not model:
            self.set_info("Please select or enter a model")
            return

        start, end = self.entry_chat_buffer.get_bounds()
        user_text = self.entry_chat_buffer.get_text(start, end, True).strip()
        if not user_text:
            self.set_info("Please enter a message")
            return

        self._append_bubble(role="user", text=user_text)
        self.entry_chat_buffer.set_text("")

        self.btn_send.set_sensitive(False)
        self.set_info("Sending request...")

        def worker():
            try:
                response_text = self.send_chat_completion(model, user_text)
                GLib.idle_add(self._append_bubble, "assistant", response_text)
                GLib.idle_add(self.set_info, "Done")
            except requests.HTTPError as http_err:
                try:
                    err_json = http_err.response.json()
                    pretty = json.dumps(err_json, indent=2)
                    GLib.idle_add(self._append_bubble, "system", f"HTTP error {http_err.response.status_code}:\n{pretty}")
                except Exception:
                    GLib.idle_add(self._append_bubble, "system", f"HTTP error {getattr(http_err.response, 'status_code', '?')}: {http_err}")
                GLib.idle_add(self.set_info, "Failed")
            except Exception as e:
                GLib.idle_add(self._append_bubble, "system", f"Error: {e}")
                GLib.idle_add(self.set_info, "Failed")
            finally:
                GLib.idle_add(self.btn_send.set_sensitive, True)

        threading.Thread(target=worker, daemon=True).start()

    def set_response(self, text):
        self._append_bubble(role="assistant", text=text)

    def send_chat_completion(self, model, prompt):
        base_url = (self.entry_url.get_text().strip() or "https://api.openai.com/").rstrip("/") + "/"
        api_key = self.entry_api.get_text().strip()

        url = urljoin(base_url, "v1/chat/completions")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
        }

        r = requests.post(url, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()

        choices = data.get("choices") or []
        if not choices:
            return json.dumps(data, indent=2)

        first = choices[0]
        if isinstance(first, dict):
            if "message" in first and isinstance(first["message"], dict):
                content = first["message"].get("content")
                if content:
                    return content
            if "text" in first and isinstance(first["text"], str):
                return first["text"]

        return json.dumps(data, indent=2)


def main():
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
