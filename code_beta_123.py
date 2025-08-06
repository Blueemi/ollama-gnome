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
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "ollama_gui")
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")

def add_chat_css():
    css = b"""
    .chat-bubble-user {
        background: #e0f7fa;
        border-radius: 12px;
        padding: 6px 12px;
        margin: 4px 0 4px 32px;
        border: 1px solid #b2ebf2;
        color: #006064;
        font-size: 13px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .chat-bubble-assistant {
        background: #f1f8e9;
        border-radius: 12px;
        padding: 6px 12px;
        margin: 4px 32px 4px 0;
        border: 1px solid #c5e1a5;
        color: #33691e;
        font-size: 13px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .chat-bubble-system {
        background: #eeeeee;
        border-radius: 10px;
        padding: 5px 10px;
        margin: 4px 48px 4px 48px;
        border: 1px solid #bdbdbd;
        color: #424242;
        font-size: 12px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .chat-list-box {
        background: transparent;
        padding: 6px;
    }
    """
    style_provider = Gtk.CssProvider()
    style_provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

def markdown_to_markup(text):
    """Convert basic markdown to Pango markup"""
    import re

    if text is None:
        return ""
    # Escape existing markup
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Code blocks (```code```)
    text = re.sub(r'```([^`]+)```', r'<span font_family="monospace" background="#f5f5f5" foreground="#333333">\1</span>', text, flags=re.DOTALL)

    # Inline code (`code`)
    text = re.sub(r'`([^`]+)`', r'<span font_family="monospace" background="#f5f5f5" foreground="#333333">\1</span>', text)

    # Bold (**text**)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)

    # Italic (*text*)
    text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)

    return text

def add_chat_css():
    css = b"""
    .chat-bubble-user {
        background: #e0f7fa;
        border-radius: 16px;
        padding: 12px 18px;
        margin: 8px 0 8px 48px;
        border: 1px solid #b2ebf2;
        color: #006064;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .chat-bubble-assistant {
        background: #f1f8e9;
        border-radius: 16px;
        padding: 12px 18px;
        margin: 8px 48px 8px 0;
        border: 1px solid #c5e1a5;
        color: #33691e;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .chat-bubble-system {
        background: #eeeeee;
        border-radius: 12px;
        padding: 10px 16px;
        margin: 8px 64px 8px 64px;
        border: 1px solid #bdbdbd;
        color: #424242;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .chat-list-box {
        background: transparent;
        padding: 12px;
    }
    """
    style_provider = Gtk.CssProvider()
    style_provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


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
        self._model_search_text = ""
        self._model_search_text = ""

        self.settings = load_settings()

        # Root container
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)

        # HeaderBar (single, GNOME-style) + StackSwitcher
        header = Gtk.HeaderBar(show_close_button=True)
        header.set_title(APP_NAME)
        self.set_titlebar(header)

        # Shared model store and combo for both tabs
        self.model_store_settings = Gtk.ListStore(str)
        self.combo_model_settings = Gtk.ComboBox.new_with_model_and_entry(self.model_store_settings)
        self.combo_model_settings.set_entry_text_column(0)
        self.combo_model_settings.set_hexpand(False)

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

        # Automatically load models from models.json and populate model picker
        models_path = os.path.join(CONFIG_DIR, "models.json")
        settings_path = os.path.join(CONFIG_DIR, "settings.json")
        last_model = None
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                last_model = settings.get("model", None)
            except Exception as e:
                print(f"Error loading settings.json: {e}")
        if os.path.exists(models_path):
            try:
                with open(models_path, "r", encoding="utf-8") as f:
                    models = json.load(f)
                self.model_store_settings.clear()
                for m in models:
                    self.model_store_settings.append([m])
            except Exception as e:
                print(f"Error loading models.json: {e}")
        # Store last model to set later when UI is ready
        self._last_model_to_set = last_model

        # Settings view
        self.settings_page = self._build_settings_page()
        self.stack.add_titled(self.settings_page, "settings", "Settings")

        # Synchronize model selection between chat and settings tabs
        def sync_model_combo(source_combo, target_combo):
            source_entry = source_combo.get_child()
            target_entry = target_combo.get_child()
            if source_entry and target_entry:
                val = source_entry.get_text().strip()
                if val != target_entry.get_text().strip():
                    target_entry.set_text(val)
        self.combo_model_settings.connect("changed", lambda combo: sync_model_combo(self.combo_model_settings, self.combo_model_settings))

        # Save last picked model to settings.json whenever selection changes
        def save_last_model(combo):
            entry = combo.get_child()
            if entry:
                model_val = entry.get_text().strip()
                settings_path = os.path.join(CONFIG_DIR, "settings.json")
                try:
                    with open(settings_path, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                except Exception:
                    settings = {}
                settings["model"] = model_val
                try:
                    with open(settings_path, "w", encoding="utf-8") as f:
                        json.dump(settings, f, indent=2)
                except Exception as e:
                    print(f"Error saving last model to settings.json: {e}")
            idx = combo.get_active()
            if idx is not None and idx >= 0:
                model_iter = self.model_filter.get_iter(Gtk.TreePath(idx))
                if model_iter:
                    model_val = self.model_filter[model_iter][0]
                    settings_path = os.path.join(CONFIG_DIR, "settings.json")
                    try:
                        with open(settings_path, "r", encoding="utf-8") as f:
                            settings = json.load(f)
                    except Exception:
                        settings = {}
                    settings["model"] = model_val
                    try:
                        with open(settings_path, "w", encoding="utf-8") as f:
                            json.dump(settings, f, indent=2)
                    except Exception as e:
                        print(f"Error saving last model to settings.json: {e}")
        self.combo_model.connect("changed", lambda combo: save_last_model(combo))



        # Keyboard shortcuts
        self.add_accel_group(self._build_accel_group())

        # Follow GNOME dark/light mode and style
        self._apply_gnome_style()
        # Apply saved accent color (if any)
        self._apply_accent_color(self.settings.get("accent_color", "blue"))

        # Set last picked model from settings.json after UI is fully built
        if hasattr(self, '_last_model_to_set') and self._last_model_to_set:
            GLib.idle_add(self._set_model_picker_text, self._last_model_to_set)

    def _set_model_picker_text(self, model_name):
        """Set the model picker entry text to the specified model name"""
        if hasattr(self, "combo_model") and self.combo_model:
            entry = self.combo_model.get_child()
            if entry:
                entry.set_text(model_name)
            # Set the active ComboBox row to the model_name if present
            for idx, row in enumerate(self.model_filter):
                if row[0] == model_name:
                    self.combo_model.set_active(idx)
                    break
        return False  # Remove from GLib.idle_add queue

    def _build_accel_group(self):
        accel_group = Gtk.AccelGroup()
        # Ctrl+Enter to Send (bind to the Send button)
        key, mod = Gtk.accelerator_parse("<Control>Return")
        self.btn_send.add_accelerator("clicked", accel_group, key, mod, Gtk.AccelFlags.VISIBLE)
        # Global key handler manages Ctrl+Comma (open settings)
        self.connect("key-press-event", self._on_keypress_accel)
        return accel_group

    def _on_entry_keypress(self, widget, event):
        keyval = event.keyval
        state = event.state
        # Enter key without Shift sends message
        if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            if not (state & Gdk.ModifierType.SHIFT_MASK):
                self.on_send_clicked(self.btn_send)
                return True  # prevent newline
        return False  # allow normal behavior
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
        # Minimal CSS: spacing and radius only, plus dynamic accent hooks.
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
        /* Accent: fully override theme painting for buttons and StackSwitcher toggle buttons */
        /* Button accents (apply to GtkButton across states and its contents) */
        button.accent-blue,
        button.accent-blue:focus,
        button.accent-blue:hover,
        button.accent-blue:active,
        button.accent-blue:checked {
            background-color: #1c71d8;
            color: #ffffff;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        button.accent-red,
        button.accent-red:focus,
        button.accent-red:hover,
        button.accent-red:active,
        button.accent-red:checked {
            background-color: #c01c28;
            color: #ffffff;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        button.accent-black,
        button.accent-black:focus,
        button.accent-black:hover,
        button.accent-black:active,
        button.accent-black:checked {
            background-color: #000000;
            color: #ffffff;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        button.accent-white,
        button.accent-white:focus,
        button.accent-white:hover,
        button.accent-white:active,
        button.accent-white:checked {
            background-color: #ffffff;
            color: #000000;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        button.accent-green,
        button.accent-green:focus,
        button.accent-green:hover,
        button.accent-green:active,
        button.accent-green:checked {
            background-color: #2ec27e;
            color: #ffffff;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        /* Ensure label/icon inside inherits text color */
        button.accent-blue *:not(entry),
        button.accent-red *:not(entry),
        button.accent-black *:not(entry),
        button.accent-white *:not(entry),
        button.accent-green *:not(entry) {
            color: inherit;
        }
        /* StackSwitcher ToggleButton accents across states */
        stackswitcher > button.togglebutton.accent-blue,
        stackswitcher > button.togglebutton.accent-blue:focus,
        stackswitcher > button.togglebutton.accent-blue:hover,
        stackswitcher > button.togglebutton.accent-blue:active,
        stackswitcher > button.togglebutton.accent-blue:checked {
            background-color: #1c71d8;
            color: #ffffff;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        stackswitcher > button.togglebutton.accent-red,
        stackswitcher > button.togglebutton.accent-red:focus,
        stackswitcher > button.togglebutton.accent-red:hover,
        stackswitcher > button.togglebutton.accent-red:active,
        stackswitcher > button.togglebutton.accent-red:checked {
            background-color: #c01c28;
            color: #ffffff;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        stackswitcher > button.togglebutton.accent-black,
        stackswitcher > button.togglebutton.accent-black:focus,
        stackswitcher > button.togglebutton.accent-black:hover,
        stackswitcher > button.togglebutton.accent-black:active,
        stackswitcher > button.togglebutton.accent-black:checked {
            background-color: #000000;
            color: #ffffff;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        stackswitcher > button.togglebutton.accent-white,
        stackswitcher > button.togglebutton.accent-white:focus,
        stackswitcher > button.togglebutton.accent-white:hover,
        stackswitcher > button.togglebutton.accent-white:active,
        stackswitcher > button.togglebutton.accent-white:checked {
            background-color: #ffffff;
            color: #000000;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        stackswitcher > button.togglebutton.accent-green,
        stackswitcher > button.togglebutton.accent-green:focus,
        stackswitcher > button.togglebutton.accent-green:hover,
        stackswitcher > button.togglebutton.accent-green:active,
        stackswitcher > button.togglebutton.accent-green:checked {
            background-color: #2ec27e;
            color: #ffffff;
            background-image: none;
            border-image: none;
            box-shadow: none;
        }
        stackswitcher > button.togglebutton.accent-blue *,
        stackswitcher > button.togglebutton.accent-red *,
        stackswitcher > button.togglebutton.accent-black *,
        stackswitcher > button.togglebutton.accent-white *,
        stackswitcher > button.togglebutton.accent-green * {
            color: inherit;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # Use higher priority so our accent classes override theme colors immediately
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def _apply_accent_color(self, color_name):
        # Update Send button and active tab with selected accent color
        try:
            # Normalize to allowed colors
            allowed = {"blue", "red", "black", "white", "green"}
            color = (color_name or "blue").lower()
            if color not in allowed:
                color = "blue"
            # Update send button class
            if hasattr(self, "btn_send") and self.btn_send:
                ctx = self.btn_send.get_style_context()
                for cls in ["accent-blue", "accent-red", "accent-black", "accent-white", "accent-green"]:
                    ctx.remove_class(cls)
                ctx.add_class(f"accent-{color}")
            # Update active tab immediately
            self._update_stackswitcher_accent(self.stack, None)
        except Exception:
            pass


    def _build_chat_page(self):
        # Add custom CSS for chat bubbles
        add_chat_css()
        # Vertical layout: scroll area with bubbles + input row
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.get_style_context().add_class("chat-container")

        # Scrollable conversation area
        self.chat_list_box = Gtk.ListBox()
        self.chat_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.chat_list_box.get_style_context().add_class("chat-list-box")
        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.add(self.chat_list_box)
        vbox.pack_start(scroller, True, True, 0)

        # --- Model Search Entry and Filtered ComboBox ---
        # Create a search entry for filtering models
        # Create a search entry for filtering models (standalone row)
        self.model_search_entry = Gtk.Entry()
        self.model_search_entry.set_placeholder_text("Search models...")
        self.model_search_entry.set_hexpand(True)
        self.model_search_entry.set_width_chars(18)

        # Use a TreeModelFilter for filtering the model list
        self.model_store = self.model_store_settings  # Underlying store
        self.model_filter = self.model_store.filter_new()
        self.model_filter.set_visible_func(self._model_filter_func)

        # ComboBox with entry, using the filtered model
        self.combo_model = Gtk.ComboBox.new_with_model_and_entry(self.model_filter)
        self.combo_model.set_entry_text_column(0)
        # Non-editable ComboBox with CellRendererText, using the filtered model
        self.combo_model = Gtk.ComboBox.new_with_model(self.model_filter)
        renderer_text = Gtk.CellRendererText()
        renderer_text.set_property("ellipsize", 3)  # Pango.EllipsizeMode.END
        renderer_text.set_property("width-chars", 20)
        renderer_text.set_property("width", 200)  # Fixed pixel width for renderer
        self.combo_model.pack_start(renderer_text, True)
        self.combo_model.add_attribute(renderer_text, "text", 0)
        self.combo_model.set_hexpand(False)
        self.combo_model.set_halign(Gtk.Align.FILL)
        # Wrap ComboBox in a fixed-width box to prevent resizing
        combo_box_wrapper = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        combo_box_wrapper.set_size_request(220, -1)
        combo_box_wrapper.pack_start(self.combo_model, True, True, 0)

        # Synchronize model selection between chat and settings tabs
        def sync_model_combo(source_combo, target_combo):
            source_entry = source_combo.get_child()
            target_entry = target_combo.get_child()
            if source_entry and target_entry:
                val = source_entry.get_text().strip()
                if val != target_entry.get_text().strip():
                    target_entry.set_text(val)
            # Synchronize selection index between combos
            idx = source_combo.get_active()
            if idx is not None and idx >= 0:
                target_combo.set_active(idx)

        # Connect both combos to sync each other
        self.combo_model.connect("changed", lambda combo: sync_model_combo(self.combo_model, self.combo_model_settings))
        def on_combo_model_changed(combo):
            # Only act if a valid model is picked
            idx = self.combo_model.get_active()
            if idx is not None and idx >= 0:
                # Get the selected model name from the filtered model
                model_iter = self.model_filter.get_iter(Gtk.TreePath(idx))
                if model_iter:
                    selected_model = self.model_filter[model_iter][0]
                    # Clear the search entry and reset filter
                    if hasattr(self, "model_search_entry"):
                        self.model_search_entry.set_text("")
                        self._model_search_text = ""
                        if hasattr(self, "model_filter"):
                            self.model_filter.refilter()
                    # After resetting filter, re-select the chosen model in the full list
                    # (search field is now empty, so model_filter == model_store)
                    for i, row in enumerate(self.model_filter):
                        if row[0] == selected_model:
                            self.combo_model.set_active(i)
                            break
            sync_model_combo(self.combo_model, self.combo_model_settings)
        self.combo_model.connect("changed", on_combo_model_changed)
        self.combo_model_settings.connect("changed", lambda combo: sync_model_combo(self.combo_model_settings, self.combo_model))

        # --- Model Search Logic ---
        self.model_search_entry.connect("changed", self._on_model_search_changed)

        # Model picker row (search + combo + fetch)
        model_picker_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        model_picker_row.pack_start(self.model_search_entry, True, True, 0)
        model_picker_row.pack_start(self.combo_model, False, False, 0)
        # Layout: search entry row, then input row
        input_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        btn_fetch_models = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        btn_fetch_models.set_tooltip_text("Fetch models")
        btn_fetch_models.connect("clicked", self.on_fetch_models_clicked)
        model_picker_row.pack_start(btn_fetch_models, False, False, 0)
        # Search entry row (full width)
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        search_row.pack_start(self.model_search_entry, True, True, 0)
        input_area.pack_start(search_row, False, False, 0)

        vbox.pack_start(model_picker_row, False, False, 0)

        # Input row
        # Input row: picker, fetch, chat entry, send button
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_row.get_style_context().add_class("input-row")

        # Text entry for chat (single-line, GNOME look)
        # Model picker (fixed width, left-aligned, wrapped to prevent resizing)
        input_row.pack_start(combo_box_wrapper, False, False, 0)

        # Fetch models button (left of chat entry)
        btn_fetch_models = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        btn_fetch_models.set_tooltip_text("Fetch models")
        btn_fetch_models.connect("clicked", self.on_fetch_models_clicked)
        input_row.pack_start(btn_fetch_models, False, False, 0)

        # Chat entry (expands)
        self.entry_chat = Gtk.Entry()
        self.entry_chat.set_hexpand(True)
        self.entry_chat.set_placeholder_text("Type your message here")
        input_row.pack_start(self.entry_chat, True, True, 0)

        # Send button
        # Send button (right-aligned)
        self.btn_send = Gtk.Button.new_from_icon_name("mail-send-symbolic", Gtk.IconSize.BUTTON)
        self.btn_send.set_label("Send")
        self.btn_send.set_always_show_image(True)
        self.btn_send.get_style_context().add_class("suggested-action")
        accent = (self.settings.get("accent_color", "blue") or "blue").lower()
        for cls in ["accent-blue", "accent-red", "accent-black", "accent-white", "accent-green"]:
            self.btn_send.get_style_context().remove_class(cls)
        self.btn_send.get_style_context().add_class(f"accent-{accent}")
        self.btn_send.connect("clicked", self.on_send_clicked)

        # Pack input row
        input_row.pack_start(self.entry_chat, True, True, 0)
        input_row.pack_end(self.btn_send, False, False, 0)

        vbox.pack_end(input_row, False, False, 0)
        input_area.pack_start(input_row, False, False, 0)
        vbox.pack_end(input_area, False, False, 0)

        # Connect Enter key to send message
        self.entry_chat.connect("activate", self.on_send_clicked)
        return vbox

    def _append_bubble(self, role, text):
        # Create a horizontal box to align bubbles left/right
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bubble_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bubble_label = Gtk.Label()
        bubble_label.set_line_wrap(True)
        bubble_label.set_line_wrap_mode(Gtk.WrapMode.CHAR)
        bubble_label.set_selectable(True)
        # Convert markdown to Pango markup and set
        markup_text = markdown_to_markup(text)
        bubble_label.set_markup(markup_text)
        bubble_label.set_max_width_chars(80)
        bubble_label.set_width_chars(80)
        bubble_label.set_xalign(0)
        bubble_label.set_hexpand(True)
        bubble_label.set_justify(Gtk.Justification.LEFT)

        # Style for user and assistant bubbles
        if role == "user":
            bubble_box.get_style_context().add_class("chat-bubble-user")
            bubble_label.set_xalign(1)
            hb.pack_end(bubble_box, False, False, 8)
        elif role == "assistant":
            bubble_box.get_style_context().add_class("chat-bubble-assistant")
            bubble_label.set_xalign(0)
            hb.pack_start(bubble_box, False, False, 8)
        else:
            bubble_box.get_style_context().add_class("chat-bubble-system")
            bubble_label.set_xalign(0.5)
            hb.set_halign(Gtk.Align.CENTER)
            hb.pack_start(bubble_box, False, False, 8)

        bubble_box.pack_start(bubble_label, True, True, 8)
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

        # System prompt field (now uses Gtk.Entry for GNOME look)
        lbl_system = Gtk.Label(label="System Prompt:", xalign=0)
        grid.attach(lbl_system, 0, row, 1, 1)
        self.entry_system = Gtk.Entry()
        self.entry_system.set_hexpand(True)
        self.entry_system.set_placeholder_text("Enter system prompt here")
        self.entry_system.set_text(self.settings.get("system_prompt", ""))
        grid.attach(self.entry_system, 1, row, 2, 1)
        row += 1

        # Model picker removed from settings tab

        # Accent color picker (simple combo)
        lbl_color = Gtk.Label(label="Accent Color:", xalign=0)
        grid.attach(lbl_color, 0, row, 1, 1)
        self.color_store_settings = Gtk.ListStore(str)
        for color in ["blue", "red", "black", "white", "green"]:
            self.color_store_settings.append([color])
        self.combo_color_settings = Gtk.ComboBox.new_with_model(self.color_store_settings)
        renderer_text = Gtk.CellRendererText()
        self.combo_color_settings.pack_start(renderer_text, True)
        self.combo_color_settings.add_attribute(renderer_text, "text", 0)
        grid.attach(self.combo_color_settings, 1, row, 1, 1)
        # Restore saved color
        saved_color = self.settings.get("accent_color", "blue")
        def set_active_color_in_combo(combo, store, color):
            idx = 0
            found = False
            for row_it in store:
                if row_it[0] == color:
                    combo.set_active(idx)
                    found = True
                    break
                idx += 1
            if not found:
                combo.set_active(0)
        set_active_color_in_combo(self.combo_color_settings, self.color_store_settings, saved_color)
        # React on change: immediately apply accent and persist
        def on_color_changed(combo):
            idx = combo.get_active()
            if idx is None or idx < 0:
                return
            try:
                selected = self.color_store_settings[idx][0]
            except Exception:
                selected = "blue"
            self.settings["accent_color"] = selected
            save_settings(self.settings)
            self._apply_accent_color(selected)
        self.combo_color_settings.connect("changed", on_color_changed)

        btn_save = Gtk.Button(label="Save Settings")
        btn_save.connect("clicked", self.on_save_clicked)
        grid.attach(btn_save, 2, row, 1, 1)

        # Mirror model list to main combo when invoked from settings
        # Model picker removed from settings tab

        return grid

    def _update_stackswitcher_accent(self, stack, _param):
        # Apply GNOME accent only to the active tab button of the StackSwitcher
        if not hasattr(self, "stack_switcher"):
            return False
        try:
            # StackSwitcher in GTK3 is composed of ToggleButtons as children
            # First remove any previous custom accent classes
            for child in self.stack_switcher.get_children():
                if isinstance(child, Gtk.ToggleButton):
                    ctx = child.get_style_context()
                    for cls in ["accent-blue", "accent-red", "accent-black", "accent-white", "accent-green"]:
                        ctx.remove_class(cls)
                    if child.get_active():
                        ctx.add_class("suggested-action")
                        # Apply our accent color (no suggested-action)
                        accent = (self.settings.get("accent_color") or "blue").lower()
                        # Normalize to allowed colors
                        if accent not in {"blue", "red", "black", "white", "green"}:
                            accent = "blue"
                        ctx.add_class(f"accent-{accent}")
                    else:
                        ctx.remove_class("suggested-action")
                        # Ensure suggested-action is not applied
                        pass
        except Exception:
            pass
        return False

    def on_save_clicked(self, _button):
        # Persist API settings and default model
        api_key = self.entry_api.get_text().strip() if hasattr(self, "entry_api") else ""
        base_url = self.entry_url.get_text().strip() if hasattr(self, "entry_url") else ""
        system_prompt = ""
        if hasattr(self, "entry_system_buffer") and self.entry_system_buffer:
            start, end = self.entry_system_buffer.get_bounds()
            system_prompt = self.entry_system_buffer.get_text(start, end, True).strip()
        default_model = ""
        if hasattr(self, "combo_model_settings") and self.combo_model_settings:
            entry = self.combo_model_settings.get_child()
            if entry:
                default_model = entry.get_text().strip()
        elif hasattr(self, "combo_model") and self.combo_model:
            entry = self.combo_model.get_child()
            if entry:
                default_model = entry.get_text().strip()

        # Read accent color from combo
        accent_color = "blue"
        if hasattr(self, "combo_color_settings") and self.combo_color_settings:
            idx = self.combo_color_settings.get_active()
            if idx is not None and idx >= 0 and hasattr(self, "color_store_settings"):
                try:
                    accent_color = self.color_store_settings[idx][0]
                except Exception:
                    pass

        if base_url and not base_url.endswith("/"):
            base_url += "/"

        self.settings["api_key"] = api_key
        self.settings["base_url"] = base_url
        if default_model:
            self.settings["model"] = default_model
        if accent_color:
            self.settings["accent_color"] = accent_color
        if system_prompt:
            self.settings["system_prompt"] = system_prompt

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

        # Apply accent color immediately
        self._apply_accent_color(accent_color)

        self.set_info("Settings saved")
        # Return to chat view after saving
        self.on_open_chat()

    def fetch_models(self):
        # Try to read models from models.json in config dir
        models_path = os.path.join(CONFIG_DIR, "models.json")
        if os.path.exists(models_path):
            try:
                with open(models_path, "r", encoding="utf-8") as f:
                    models = json.load(f)
                # Deduplicate preserving order
                seen = set()
                unique = []
                for m in models:
                    if m not in seen:
                        unique.append(m)
                        seen.add(m)
                return unique
            except Exception as e:
                print(f"Error reading models.json: {e}")
                # fallback to fetching from API

        # If file not found or error, fetch from API and save
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
        # Save to models.json for future use
        try:
            with open(models_path, "w", encoding="utf-8") as f:
                json.dump(unique, f, indent=2)
        except Exception as save_err:
            print(f"Error saving models.json: {save_err}")
        return unique

    def _fetch_models_into_settings(self, _btn):
        # Use same fetch as chat; then update settings combo
        self.set_info("Fetching models...")

        def worker():
            try:
                models = self.fetch_models()
                # Save models to models.json in config dir
                try:
                    models_path = os.path.join(CONFIG_DIR, "models.json")
                    with open(models_path, "w", encoding="utf-8") as f:
                        json.dump(models, f, indent=2)
                except Exception as save_err:
                    print(f"Error saving models.json: {save_err}")

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
                # Save models to models.json in config dir
                try:
                    models_path = os.path.join(CONFIG_DIR, "models.json")
                    with open(models_path, "w", encoding="utf-8") as f:
                        json.dump(models, f, indent=2)
                except Exception as save_err:
                    print(f"Error saving models.json: {save_err}")
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
            # Set entry text to last used model from settings.json if available
            # Set ComboBox to last used model from settings.json if available
            settings_path = os.path.join(CONFIG_DIR, "settings.json")
            last_model = None
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                    last_model = settings.get("model", None)
                except Exception as e:
                    print(f"Error loading settings.json: {e}")
            entry = self.combo_model.get_child()
            if entry and last_model:
                entry.set_text(last_model)
            if last_model:
                for idx, row in enumerate(self.model_filter):
                    if row[0] == last_model:
                        self.combo_model.set_active(idx)
                        break
            else:
                self.combo_model.set_active(0)

    def set_info(self, text):
        if hasattr(self, "info_label") and self.info_label:
            self.info_label.set_text(text)

    def get_selected_model(self):
        # Prefer the chat combo entry text
        entry = None
        # Always use settings combo for selected model
        if hasattr(self, "combo_model_settings") and self.combo_model_settings:
            entry = self.combo_model_settings.get_child()
            if entry:
                val = entry.get_text().strip()
                if val:
                    return val
        return ""
        # Use the selected model from the non-editable ComboBox
        if hasattr(self, "combo_model") and self.combo_model:
            idx = self.combo_model.get_active()
            if idx is not None and idx >= 0:
                # Always get the model from the current filter (should be full list after clearing search)
                model_iter = self.model_filter.get_iter(Gtk.TreePath(idx))
                if model_iter:
                    return self.model_filter[model_iter][0]
        return ""

    def on_send_clicked(self, _button):
        model = self.get_selected_model()
        print(f"[DEBUG] Selected model for sending: '{model}'")
        if not model:
            self.set_info("Please select or enter a model")
            return

        user_text = self.entry_chat.get_text().strip()
        if not user_text:
            self.set_info("Please enter a message")
            return

        self._append_bubble(role="user", text=user_text)
        self.entry_chat.set_text("")
        # Save last chosen model to settings.json using settings combo
        settings_path = os.path.join(CONFIG_DIR, "settings.json")
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            settings = {}
        entry = self.combo_model_settings.get_child()
        if entry:
            settings["model"] = entry.get_text().strip()
        idx = self.combo_model.get_active()
        if idx is not None and idx >= 0:
            model_iter = self.model_filter.get_iter(Gtk.TreePath(idx))
            if model_iter:
                settings["model"] = self.model_filter[model_iter][0]
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error saving last model to settings.json: {e}")

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

        # Build user message with system prompt prepended if available
        system_prompt = self.settings.get("system_prompt", "").strip()
        user_content = prompt
        if system_prompt:
            user_content = system_prompt + "\n\n" + prompt

        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.7,
        }

        r = requests.post(url, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()

        choices = data.get("choices") or []
        if not choices:
            return json.dumps(data, indent=2)

    def _on_model_search_changed(self, entry):
        """Update the filter for the model picker as the user types."""
        text = entry.get_text().strip().lower()
        self._model_search_text = text
        if hasattr(self, "model_filter"):
            self.model_filter.refilter()
        # Reset ComboBox selection when filtering
        if hasattr(self, "combo_model"):
            self.combo_model.set_active(-1)

    def _model_filter_func(self, model, iter_, data=None):
        """Filter function for model picker based on search entry."""
        if not hasattr(self, "_model_search_text"):
            return True
        search = self._model_search_text
        if not search:
            return True
        value = model[iter_][0].lower()
        return search in value

# --- end of file ---

        def _on_model_search_changed(self, entry):
            """Update the filter for the model picker as the user types."""
            text = entry.get_text().strip().lower()
            self._model_search_text = text
            if hasattr(self, "model_filter"):
                self.model_filter.refilter()

        def _model_filter_func(self, model, iter_, data=None):
            """Filter function for model picker based on search entry."""
            if not hasattr(self, "_model_search_text"):
                return True
            search = self._model_search_text
            if not search:
                return True
            value = model[iter_][0].lower()
            return search in value

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
    ensure_config_dir()
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

# --- Add handler for Enter key to send message ---
# Moved into MainWindow class below


if __name__ == "__main__":
    main()
