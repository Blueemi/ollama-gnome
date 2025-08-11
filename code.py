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
from gi.repository import Gtk, Gio, GLib, Gdk, Pango

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
        margin: 4px 4px 4px 4px;
        border: 1px solid #b2ebf2;
        color: #006064;
        font-size: 13px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .chat-bubble-assistant {
        background: #f1f8e9;
        border-radius: 12px;
        padding: 6px 12px;
        margin: 4px 4px 4px 4px;
        border: 1px solid #c5e1a5;
        color: #33691e;
        font-size: 13px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .chat-bubble-system {
        background: #eeeeee;
        border-radius: 10px;
        padding: 5px 10px;
        margin: 4px 4px 4px 4px;
        border: 1px solid #bdbdbd;
        color: #424242;
        font-size: 12px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .chat-list-box {
        background: transparent;
        padding: 2px;
    }
    .chat-input-area {
        background: rgba(255, 255, 255, 0.02);
        border-top: 1px solid rgba(0, 0, 0, 0.1);
        padding: 8px;
    }
    .chat-input-row {
        min-height: 36px;
    }
    .chat-input-row entry,
    .chat-input-row combobox,
    .chat-input-row button {
        min-height: 36px;
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

        # --- Square dark/light mode toggle button ---
        self._manual_dark_mode = None  # None = follow GNOME, True/False = manual override

        self.dark_toggle_btn = Gtk.Button()
        self.dark_toggle_btn.set_size_request(36, 36)
        self.dark_toggle_btn.set_can_focus(False)
        self.dark_toggle_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.dark_toggle_btn.set_tooltip_text("Toggle dark/light mode")
        self._update_dark_toggle_icon()
        self.dark_toggle_btn.connect("clicked", self._on_dark_toggle_clicked)
        header.pack_start(self.dark_toggle_btn)

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
        if os.path.exists(models_path):
            try:
                with open(models_path, "r", encoding="utf-8") as f:
                    models = json.load(f)
                self.model_store_settings.clear()
                for m in models:
                    self.model_store_settings.append([m])
                # Also populate display model if it exists
                if hasattr(self, 'display_model'):
                    self.display_model.clear()
                    for m in models:
                        self.display_model.append([m])
                print(f"[DEBUG] Loaded {len(models)} models from models.json")
            except Exception as e:
                print(f"Error loading models.json: {e}")

        # Settings view
        self.settings_page = self._build_settings_page()
        self.stack.add_titled(self.settings_page, "settings", "Settings")

        # Synchronize model selection between chat and settings tabs
        def sync_model_combo(source_combo, target_combo):
            if hasattr(self, '_updating_combo') and self._updating_combo:
                return  # Prevent recursion during programmatic updates
            # Sync selection by active index, not by entry text
            idx = source_combo.get_active()
            if idx is not None and idx >= 0:
                self._updating_combo = True
                target_combo.set_active(idx)
                self._updating_combo = False
        self.combo_model_settings.connect("changed", lambda combo: sync_model_combo(self.combo_model_settings, self.combo_model))

        # Save last picked model to settings.json whenever selection changes
        def save_last_model(combo):
            if hasattr(self, '_updating_combo') and self._updating_combo:
                return  # Prevent recursion during programmatic updates
            idx = combo.get_active()
            if idx is not None and idx >= 0:
                model_val = None
                # Get model from display model for chat combo
                if combo == self.combo_model and hasattr(self, 'display_model'):
                    if idx < len(self.display_model):
                        model_val = self.display_model[idx][0]
                # Get model from settings store for settings combo
                elif combo == self.combo_model_settings:
                    if idx < len(self.model_store_settings):
                        model_val = self.model_store_settings[idx][0]
                else:
                    return

                # Update settings and save only if we have a valid model
                if model_val:
                    self.settings["model"] = model_val
                    save_settings(self.settings)
                    print(f"[DEBUG] Saved model to settings: {model_val}")

        self.combo_model.connect("changed", lambda combo: save_last_model(combo))
        self.combo_model_settings.connect("changed", lambda combo: save_last_model(combo))

        # Initialize update flag to prevent recursion
        self._updating_combo = False

        # Keyboard shortcuts
        self.add_accel_group(self._build_accel_group())

        # Follow GNOME dark/light mode and style
        self._apply_gnome_style()
        # Apply saved accent color (if any)
        self._apply_accent_color(self.settings.get("accent_color", "blue"))

        # Listen for theme changes to update accent if 'default' is selected
        settings = Gtk.Settings.get_default()
        def on_theme_changed(settings, param):
            if self.settings.get("accent_color", "blue") == "default":
                self._apply_accent_color("default")
        settings.connect("notify::gtk-application-prefer-dark-theme", on_theme_changed)

        # Set last picked model from settings.json after UI is fully built
        GLib.idle_add(self._load_and_set_saved_model)

        # Also populate display model with initial models if we have them
        if len(self.model_store_settings) > 0:
            if hasattr(self, 'display_model'):
                self.display_model.clear()
                for row in self.model_store_settings:
                    self.display_model.append([row[0]])

    def _set_model_picker_text(self, model_name):
        """Set the model picker selection to the specified model name"""
        if hasattr(self, "combo_model") and self.combo_model:
            # Set the active ComboBox row to the model_name if present
            for idx, row in enumerate(self.display_model):
                if row[0] == model_name:
                    self.combo_model.set_active(idx)
                    break
        return False  # Remove from GLib.idle_add queue

    def _load_and_set_saved_model(self):
        """Load saved model from settings.json and set it in both combo boxes"""
        try:
            saved_model = self.settings.get("model", None)
            print(f"[DEBUG] _load_and_set_saved_model: saved_model={saved_model}")

            if saved_model:
                self._updating_combo = True

                # Set in chat combo box
                if hasattr(self, "combo_model") and hasattr(self, "display_model"):
                    print(f"[DEBUG] Chat combo exists, display_model has {len(self.display_model)} items")
                    found_chat = False
                    for idx, row in enumerate(self.display_model):
                        if row[0] == saved_model:
                            print(f"[DEBUG] Setting chat combo to index {idx}: {saved_model}")
                            self.combo_model.set_active(idx)
                            # Force UI refresh
                            self.combo_model.queue_draw()
                            found_chat = True
                            break
                    if not found_chat:
                        print(f"[DEBUG] Model '{saved_model}' not found in display_model")

                # Set in settings combo box
                if hasattr(self, "combo_model_settings") and hasattr(self, "model_store_settings"):
                    print(f"[DEBUG] Settings combo exists, model_store has {len(self.model_store_settings)} items")
                    found_settings = False
                    for idx, row in enumerate(self.model_store_settings):
                        if row[0] == saved_model:
                            print(f"[DEBUG] Setting settings combo to index {idx}: {saved_model}")
                            self.combo_model_settings.set_active(idx)
                            # Force UI refresh
                            self.combo_model_settings.queue_draw()
                            found_settings = True
                            break
                    if not found_settings:
                        print(f"[DEBUG] Model '{saved_model}' not found in model_store_settings")

                self._updating_combo = False
                print(f"[DEBUG] Loaded saved model: {saved_model}")
            else:
                print("[DEBUG] No saved model found in settings")
        except Exception as e:
            print(f"[DEBUG] Error loading saved model: {e}")
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
        # 1) Manual override (via square button)
        # 2) GTK_PREFER_DARK env override (for testing)
        # 3) org.gnome.desktop.interface color-scheme = prefer-dark
        # 4) otherwise leave current session/theme as-is
        settings = Gtk.Settings.get_default()

        # 1) Manual override (via button)
        if hasattr(self, "_manual_dark_mode") and self._manual_dark_mode is not None:
            settings.set_property("gtk-application-prefer-dark-theme", self._manual_dark_mode)
            # If accent is 'default', update it to match theme
            if self.settings.get("accent_color", "blue") == "default":
                self._apply_accent_color("default")
            return

        # 2) Environment override for easy testing
        try:
            val = os.environ.get("GTK_PREFER_DARK", "").strip().lower()
            if val in ("1", "true", "yes"):
                settings.set_property("gtk-application-prefer-dark-theme", True)
            elif val in ("0", "false", "no"):
                settings.set_property("gtk-application-prefer-dark-theme", False)
            # If accent is 'default', update it to match theme
            if self.settings.get("accent_color", "blue") == "default":
                self._apply_accent_color("default")
        except Exception:
            pass

        # 3) Read GNOME interface color-scheme via GSettings if available
        try:
            schema = "org.gnome.desktop.interface"
            key = "color-scheme"
            if Gio.Settings.list_schemas() and schema in Gio.Settings.list_schemas():
                gsettings = Gio.Settings.new(schema)
                cs = gsettings.get_string(key)
                if cs == "prefer-dark":
                    settings.set_property("gtk-application-prefer-dark-theme", True)
            # If accent is 'default', update it to match theme
            if self.settings.get("accent_color", "blue") == "default":
                self._apply_accent_color("default")
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
            allowed = {"blue", "red", "green", "default"}
            color = (color_name or "blue").lower()
            if color not in allowed:
                color = "blue"

            # Handle 'default' accent: auto-switch black/white based on theme
            resolved_color = color
            if color == "default":
                settings = Gtk.Settings.get_default()
                dark = settings.get_property("gtk-application-prefer-dark-theme")
                resolved_color = "white" if dark else "black"

            # Apply to Send button
            ctx = self.btn_send.get_style_context()
            for cls in ["accent-blue", "accent-red", "accent-black", "accent-white", "accent-green"]:
                ctx.remove_class(cls)
            ctx.add_class(f"accent-{resolved_color}")

            # Update active tab immediately
            self._update_stackswitcher_accent(self.stack, None)
        except Exception:
            pass


    def _build_chat_page(self):
        # Add custom CSS for chat bubbles
        add_chat_css()
        # Vertical layout: scroll area with bubbles + input area
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
        self.model_search_entry = Gtk.Entry()
        self.model_search_entry.set_placeholder_text("Search models...")
        self.model_search_entry.set_hexpand(True)

        # Use a TreeModelFilter for filtering the model list
        self.model_store = self.model_store_settings  # Underlying store
        self.model_filter = self.model_store.filter_new()
        self.model_filter.set_visible_func(self._model_filter_func)

        # Create a temporary limited model for display (prevents empty gaps)
        self.display_model = Gtk.ListStore(str)
        # Initialize display model with all items from model store
        for row in self.model_store:
            self.display_model.append([row[0]])
        print(f"[DEBUG] Initialized display_model with {len(self.display_model)} models")

        # Non-editable ComboBox with CellRendererText, using the display model
        self.combo_model = Gtk.ComboBox.new_with_model(self.display_model)
        renderer_text = Gtk.CellRendererText()
        renderer_text.set_property("ellipsize", 3)  # Pango.EllipsizeMode.END
        self.combo_model.pack_start(renderer_text, True)
        self.combo_model.add_attribute(renderer_text, "text", 0)
        self.combo_model.set_hexpand(True)
        self.combo_model.set_halign(Gtk.Align.FILL)

        # Synchronize model selection between chat and settings tabs
        def sync_model_combo(source_combo, target_combo):
            if hasattr(self, '_updating_combo') and self._updating_combo:
                return  # Prevent recursion during programmatic updates
            idx = source_combo.get_active()
            if idx is not None and idx >= 0:
                self._updating_combo = True
                target_combo.set_active(idx)
                self._updating_combo = False

        # Connect both combos to sync each other
        self.combo_model.connect("changed", lambda combo: sync_model_combo(self.combo_model, self.combo_model_settings))
        self.combo_model.connect("changed", self._on_combo_model_changed)
        self.combo_model_settings.connect("changed", lambda combo: sync_model_combo(self.combo_model_settings, self.combo_model))

        # --- Model Search Logic ---
        self.model_search_entry.connect("changed", self._on_model_search_changed)

        # Create fetch models button
        btn_fetch_models = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        btn_fetch_models.set_tooltip_text("Fetch models")
        btn_fetch_models.connect("clicked", self.on_fetch_models_clicked)

        # Input area with consistent spacing and alignment
        input_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        input_area.get_style_context().add_class("chat-input-area")
        input_area.set_margin_top(8)
        input_area.set_margin_bottom(8)
        input_area.set_margin_start(8)
        input_area.set_margin_end(8)

        # Model search row
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_row.get_style_context().add_class("chat-input-row")
        search_row.pack_start(self.model_search_entry, True, True, 0)
        input_area.pack_start(search_row, False, False, 0)

        # Model selection and controls row
        model_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        model_row.get_style_context().add_class("chat-input-row")
        model_row.pack_start(self.combo_model, True, True, 0)
        model_row.pack_start(btn_fetch_models, False, False, 0)
        input_area.pack_start(model_row, False, False, 0)

        # Chat input row
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_row.get_style_context().add_class("chat-input-row")

        # Chat entry (expands)
        self.entry_chat = Gtk.Entry()
        self.entry_chat.set_hexpand(True)
        self.entry_chat.set_placeholder_text("Type your message here")
        input_row.pack_start(self.entry_chat, True, True, 0)

        # Send button
        self.btn_send = Gtk.Button.new_from_icon_name("mail-send-symbolic", Gtk.IconSize.BUTTON)
        self.btn_send.set_label("Send")
        self.btn_send.set_always_show_image(True)
        self.btn_send.get_style_context().add_class("suggested-action")
        accent = self.settings.get("accent_color", "blue").lower()
        resolved_accent = accent
        if accent == "default":
            settings = Gtk.Settings.get_default()
            dark = settings.get_property("gtk-application-prefer-dark-theme")
            resolved_accent = "white" if dark else "black"
        for cls in ["accent-blue", "accent-red", "accent-black", "accent-white", "accent-green"]:
            self.btn_send.get_style_context().remove_class(cls)
        self.btn_send.get_style_context().add_class(f"accent-{resolved_accent}")
        self.btn_send.connect("clicked", self.on_send_clicked)
        input_row.pack_start(self.btn_send, False, False, 0)

        input_area.pack_start(input_row, False, False, 0)
        vbox.pack_start(input_area, False, False, 0)

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
        bubble_label.set_line_wrap(True)
        bubble_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        bubble_label.set_xalign(0)
        bubble_label.set_hexpand(True)
        bubble_label.set_justify(Gtk.Justification.LEFT)

        # Style for user and assistant bubbles
        if role == "user":
            bubble_box.get_style_context().add_class("chat-bubble-user")
            bubble_label.set_xalign(1)
            hb.pack_start(bubble_box, True, True, 0)
        elif role == "assistant":
            bubble_box.get_style_context().add_class("chat-bubble-assistant")
            bubble_label.set_xalign(0)
            hb.pack_start(bubble_box, True, True, 0)
        else:
            bubble_box.get_style_context().add_class("chat-bubble-system")
            bubble_label.set_xalign(0.5)
            hb.set_halign(Gtk.Align.CENTER)
            hb.pack_start(bubble_box, True, True, 0)

        print(f"[DEBUG] _append_bubble: role={role}, text={repr(text)}")  # Debug output

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
        for color in ["blue", "red", "green", "default"]:
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
                        # Resolve 'default' to 'white' or 'black' based on theme
                        if accent == "default":
                            settings = Gtk.Settings.get_default()
                            dark = settings.get_property("gtk-application-prefer-dark-theme")
                            accent = "white" if dark else "black"
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
                self._populate_display_model()
                # Auto-select the MIDDLE model in the list for optimal visibility
                if len(self.display_model) > 0:
                    middle_index = len(self.display_model) // 2
                    self.combo_model.set_active(middle_index)

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
                            self._populate_display_model()
                            # Auto-select the MIDDLE model in the list for optimal visibility
                            if len(self.display_model) > 0:
                                middle_index = len(self.display_model) // 2
                                self.combo_model.set_active(middle_index)
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

        # Also update the settings model store and display model
        self.model_store_settings.clear()
        for m in models:
            self.model_store_settings.append([m])

        # Update display model used by chat combo
        if hasattr(self, 'display_model'):
            self.display_model.clear()
            for m in models:
                self.display_model.append([m])

        if len(models) > 0:
            print(f"[DEBUG] Populated models, loading saved model...")
            # Load and set saved model from settings.json with a slight delay to ensure UI is ready
            GLib.timeout_add(100, self._load_and_set_saved_model)
        else:
            print("[DEBUG] No models available to set")

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
            if idx is not None and idx >= 0 and idx < len(self.display_model):
                return self.display_model[idx][0]
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
        if idx is not None and idx >= 0 and idx < len(self.display_model):
            settings["model"] = self.display_model[idx][0]
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
        print(f"[DEBUG] send_chat_completion: response data={repr(data)}")  # Debug output
        if not choices:
            return json.dumps(data, indent=2)

        # Extract assistant message content robustly
        first = choices[0]
        content = None
        if isinstance(first, dict):
            if "message" in first and isinstance(first["message"], dict):
                content = first["message"].get("content")
            elif "text" in first and isinstance(first["text"], str):
                content = first["text"]
        if not content:
            content = json.dumps(data, indent=2)
        return content

    def _on_model_search_changed(self, entry):
        """Update the filter for the model picker as the user types."""
        # Prevent recursion during programmatic updates
        if hasattr(self, '_updating_combo') and self._updating_combo:
            return

        text = entry.get_text().strip().lower()
        self._model_search_text = text
        if hasattr(self, "model_filter"):
            # Store current selection before filtering
            current_model = None
            idx = self.combo_model.get_active()
            if idx >= 0 and idx < len(self.display_model):
                current_model = self.display_model[idx][0]

            # Apply filter to the main model
            self.model_filter.refilter()

            # Update the display model with filtered results
            self._populate_display_model()

            # Set flag to prevent recursion
            self._updating_combo = True

            # Reset selection first
            self.combo_model.set_active(-1)

            # Always select the MIDDLE item in the list for optimal visibility
            if len(self.display_model) > 0:
                middle_index = len(self.display_model) // 2
                self.combo_model.set_active(middle_index)

            # Clear flag
            self._updating_combo = False

    def _model_filter_func(self, model, iter_, data=None):
        """Filter function for model picker based on search entry."""
        if not hasattr(self, "_model_search_text"):
            return True
        search = self._model_search_text
        if not search:
            return True
        value = model[iter_][0].lower()
        return search in value

    def _populate_display_model(self):
        """Populate the display model with filtered results only."""
        # Clear the display model
        self.display_model.clear()

        # Get search text for prioritization
        search_text = getattr(self, '_model_search_text', '').lower()

        # Collect all filtered items
        filtered_items = []
        for row in self.model_filter:
            filtered_items.append(row[0])

        if search_text:
            # Sort filtered items: exact matches first, then starts with, then contains
            exact_matches = []
            starts_with = []
            contains = []

            for item in filtered_items:
                item_lower = item.lower()
                if item_lower == search_text:
                    exact_matches.append(item)
                elif item_lower.startswith(search_text):
                    starts_with.append(item)
                else:
                    contains.append(item)

            # Add items in priority order: exact matches at top
            for item in exact_matches + starts_with + contains:
                self.display_model.append([item])
        else:
            # No search text, add all filtered items in original order
            for item in filtered_items:
                self.display_model.append([item])

    def _on_combo_model_changed(self, combo):
        """Handle combo box model changes - simplified to prevent recursion."""
        # Only act if a valid model is picked and we're not updating programmatically
        if hasattr(self, '_updating_combo') and self._updating_combo:
            return

        idx = self.combo_model.get_active()
        if idx is not None and idx >= 0 and idx < len(self.display_model):
            # Get the selected model name from the display model
            selected_model = self.display_model[idx][0]

            # Sync with settings combo
            if hasattr(self, "combo_model_settings"):
                entry = self.combo_model_settings.get_child()
                if entry:
                    entry.set_text(selected_model)

    # Using middle item auto-selection approach for optimal list visibility

    def _on_dark_toggle_clicked(self, btn):
        settings = Gtk.Settings.get_default()
        # Toggle manual override
        current = settings.get_property("gtk-application-prefer-dark-theme")
        self._manual_dark_mode = not current
        settings.set_property("gtk-application-prefer-dark-theme", self._manual_dark_mode)
        self._update_dark_toggle_icon()

    def _update_dark_toggle_icon(self):
        settings = Gtk.Settings.get_default()
        dark = settings.get_property("gtk-application-prefer-dark-theme")
        # Use Unicode icons for simplicity (can be replaced with Gtk.Image if desired)
        if dark:
            self.dark_toggle_btn.set_label("☾")  # Moon for dark
        else:
            self.dark_toggle_btn.set_label("☀")  # Sun for light

def main():
    win = MainWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()

# --- Add handler for Enter key to send message ---
# Moved into MainWindow class below


if __name__ == "__main__":
    main()
 # type: ignore