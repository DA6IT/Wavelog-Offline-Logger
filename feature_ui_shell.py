from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter import font as tkfont
from app_common import responsive_spacing_scale, responsive_ui_scale, write_startup_log
from logger_core import VERSION
from ui_preferences import translate_text
from ui_theme import theme

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None


class UiShellFeatureMixin:
    def _init_ui_shell_feature(self) -> None:
        self._ui_scale = 1.0
        self._responsive_resize_job = None
        self._responsive_fonts: list[tuple[tkfont.Font, int]] = []
        self._responsive_wraplengths: list[tuple[tk.Widget, int]] = []
        self._responsive_geometry_paddings: list[tuple[tk.Widget, str, str, tuple[int, ...]]] = []
        self._responsive_card_frames: list[ttk.Frame] = []
        self._settings_optional_help: list[tk.Widget] = []
        self._brand_logo_source = None
        self.current_page = ""

    def _tr(self, value: object) -> str:
        return translate_text(value, self.language)

    def _present_main_window(self):
        """Show the completed window and reliably bring it to the foreground."""
        if self.closing:
            return
        self.deiconify()
        self.update_idletasks()
        self._apply_responsive_scale(force=True)
        try:
            self.lift()
            # Windows may reject a normal foreground request from a freshly
            # spawned GUI process.  A short topmost pulse makes the window
            # visible without leaving it permanently above other programs.
            self.attributes("-topmost", True)
            self.focus_force()
        except tk.TclError:
            pass
        self.after(180, self._finish_window_presentation)

    def _show_adif_migration_report(self):
        report = self.pending_adif_migration_report
        self.pending_adif_migration_report = None
        if not report or self.closing:
            return
        messagebox.showinfo(
            "ADI-Logbuch zusammengeführt",
            f"{report.get('sources', 0)} bisherige ADI-Datei(en) wurden sicher in eine Datei "
            f"mit {report.get('records', 0)} QSO(s) zusammengeführt.\n\n"
            f"Neue Logdatei:\n{report.get('target', '')}\n\n"
            f"Wiederherstellungs-ZIP:\n{report.get('backup', '')}",
            parent=self,
        )

    def _finish_window_presentation(self):
        if self.closing:
            return
        try:
            self.attributes("-topmost", False)
            self.lift()
            self.focus_force()
            self.call_entry.focus_set()
        except (AttributeError, tk.TclError):
            pass

    def _window_configured(self, event=None):
        if self.closing or (event is not None and event.widget is not self):
            return
        if self._responsive_resize_job is not None:
            try:
                self.after_cancel(self._responsive_resize_job)
            except tk.TclError:
                pass
        self._responsive_resize_job = self.after(70, self._apply_responsive_scale)

    def _capture_responsive_widgets(self):
        """Remember original visual metrics so resizing can zoom without drift."""
        self._responsive_fonts.clear()
        self._responsive_wraplengths.clear()
        self._responsive_geometry_paddings.clear()

        def padding_values(value) -> tuple[int, ...]:
            try:
                parts = self.tk.splitlist(str(value))
                return tuple(int(round(float(part))) for part in parts)
            except (TypeError, ValueError, tk.TclError):
                return ()

        def visit(widget):
            try:
                children = widget.winfo_children()
            except tk.TclError:
                children = ()
            for child in children:
                visit(child)

            try:
                font_spec = widget.cget("font")
                if font_spec:
                    responsive_font = tkfont.Font(root=self, font=font_spec)
                    base_size = int(responsive_font.cget("size"))
                    if base_size:
                        widget.configure(font=responsive_font)
                        self._responsive_fonts.append((responsive_font, base_size))
            except (KeyError, TypeError, ValueError, tk.TclError):
                pass

            try:
                wraplength = int(float(widget.cget("wraplength")))
                if wraplength > 0:
                    self._responsive_wraplengths.append((widget, wraplength))
            except (KeyError, TypeError, ValueError, tk.TclError):
                pass

            try:
                manager = widget.winfo_manager()
                if manager == "grid":
                    info = widget.grid_info()
                elif manager == "pack":
                    info = widget.pack_info()
                else:
                    info = {}
                for option in ("padx", "pady", "ipadx", "ipady"):
                    values = padding_values(info.get(option, ""))
                    if values and any(values):
                        self._responsive_geometry_paddings.append((widget, manager, option, values))
            except (KeyError, TypeError, ValueError, tk.TclError):
                pass

        visit(self)

    def _apply_responsive_scale(self, force: bool = False):
        self._responsive_resize_job = None
        if self.closing:
            return
        scale = responsive_ui_scale(self.winfo_width(), self.winfo_height())
        if not force and abs(scale - self._ui_scale) < 0.001:
            self._apply_settings_responsive_layout()
            self._apply_xota_responsive_layout()
            return
        self._ui_scale = scale

        for responsive_font, base_size in self._responsive_fonts:
            magnitude = max(6, int(round(abs(base_size) * scale)))
            responsive_font.configure(size=(-magnitude if base_size < 0 else magnitude))
        for widget, base_wraplength in self._responsive_wraplengths:
            try:
                widget.configure(wraplength=max(80, int(round(base_wraplength * scale))))
            except tk.TclError:
                pass
        # Empty space must contract more quickly than text.  Otherwise a page
        # can be clipped even though every individual font was scaled down.
        spacing_scale = responsive_spacing_scale(scale)
        for widget, manager, option, base_values in self._responsive_geometry_paddings:
            try:
                scaled = tuple(max(0, int(round(value * spacing_scale))) for value in base_values)
                value = scaled[0] if len(scaled) == 1 else scaled
                if manager == "grid":
                    widget.grid_configure(**{option: value})
                elif manager == "pack":
                    widget.pack_configure(**{option: value})
            except tk.TclError:
                pass
        for card_frame in self._responsive_card_frames:
            try:
                card_frame.configure(padding=max(8, int(round(16 * scale))))
            except tk.TclError:
                pass

        self._setup_style(scale)
        if hasattr(self, "sidebar"):
            self.sidebar.configure(width=max(145, int(round(205 * scale))))
        if hasattr(self, "main"):
            self.main.configure(padding=(
                max(12, int(round(22 * scale))),
                max(9, int(round(16 * scale))),
            ))
        if hasattr(self, "clock_card"):
            self.clock_card.configure(
                width=max(150, int(round(178 * scale))),
                height=max(44, int(round(52 * scale))),
            )
        if hasattr(self, "log_page"):
            self.log_page.columnconfigure(1, minsize=max(255, int(round(370 * scale))))
        if hasattr(self, "callbook_image_frame"):
            self.callbook_image_frame.configure(height=104)
        if hasattr(self, "qso_history_frame") and hasattr(self, "call_var"):
            self._update_qso_worked_history(self.call_var.get().strip().upper())
        self._apply_settings_responsive_layout()
        self._apply_xota_responsive_layout()
        self._render_brand_logo()
        if self.callbook_image_bytes:
            self._render_callbook_image(self.callbook_image_bytes)

    def _apply_settings_responsive_layout(self):
        """Keep every settings action reachable without a scrolling page."""
        if not self._settings_optional_help:
            return
        compact = self.winfo_height() < 810
        for widget in self._settings_optional_help:
            try:
                if compact:
                    widget.grid_remove()
                else:
                    widget.grid()
            except tk.TclError:
                pass

    def _render_brand_logo(self):
        if self._brand_logo_source is None or not hasattr(self, "brand_label") or ImageTk is None:
            return
        try:
            image = self._brand_logo_source.copy()
            image.thumbnail(
                (max(105, int(round(170 * self._ui_scale))), max(42, int(round(70 * self._ui_scale)))),
                Image.Resampling.LANCZOS,
            )
            self.brand_logo_photo = ImageTk.PhotoImage(image)
            self.brand_label.configure(image=self.brand_logo_photo)
        except Exception as exc:
            write_startup_log("Logo konnte nicht responsiv skaliert werden: " + repr(exc))

    def _canonical_choice(self, value: str, canonical_values) -> str:
        for canonical in canonical_values:
            if value in {canonical, self._tr(canonical)}:
                return canonical
        return value

    def _install_dialog_translation(self):
        if self.language != "en" or getattr(messagebox, "_da6it_translated", False):
            return
        for name in ("showinfo", "showwarning", "showerror", "askquestion", "askokcancel", "askretrycancel", "askyesno", "askyesnocancel"):
            original = getattr(messagebox, name, None)
            if not original:
                continue
            def translated(title, message, *args, _original=original, **kwargs):
                return _original(self._tr(title), self._tr(message), *args, **kwargs)
            setattr(messagebox, name, translated)
        messagebox._da6it_translated = True
        original_askstring = simpledialog.askstring
        def translated_askstring(title, prompt, *args, **kwargs):
            return original_askstring(self._tr(title), self._tr(prompt), *args, **kwargs)
        simpledialog.askstring = translated_askstring

    def _localize_widget_tree(self, parent):
        if self.language != "en":
            return
        try:
            widgets = [parent, *parent.winfo_children()]
        except Exception:
            return
        for widget in widgets:
            if widget is not parent:
                self._localize_widget_tree(widget)
            try:
                if isinstance(widget, (tk.Tk, tk.Toplevel)):
                    current_title = widget.title()
                    translated_title = self._tr(current_title)
                    if translated_title != current_title:
                        widget.title(translated_title)
                if isinstance(widget, (tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton, tk.LabelFrame,
                                       ttk.Label, ttk.Button, ttk.Checkbutton, ttk.Radiobutton, ttk.LabelFrame)):
                    variable_name = str(widget.cget("textvariable") or "")
                    if variable_name:
                        current = widget.getvar(variable_name)
                        translated = self._tr(current)
                        if translated != current:
                            widget.setvar(variable_name, translated)
                    else:
                        current = widget.cget("text")
                        translated = self._tr(current)
                        if translated != current:
                            widget.configure(text=translated)
                if isinstance(widget, ttk.Notebook):
                    for tab_id in widget.tabs():
                        current = widget.tab(tab_id, "text")
                        translated = self._tr(current)
                        if translated != current:
                            widget.tab(tab_id, text=translated)
                if isinstance(widget, ttk.Treeview):
                    for column in widget["columns"]:
                        current = widget.heading(column, "text")
                        translated = self._tr(current)
                        if translated != current:
                            widget.heading(column, text=translated)
            except (tk.TclError, RuntimeError):
                pass

    def _localization_tick(self):
        if self.closing:
            return
        self._localize_widget_tree(self)
        self.after(700, self._localization_tick)

    def _open_da6it_website(self, _event=None):
        self._open_external_url("https://da6it.de/", "DA6IT.de")

    def _open_external_url(self, url: str, label: str):
        try:
            webbrowser.open_new_tab(url)
        except Exception as exc:
            self.status_var.set(f"{label} konnte nicht geöffnet werden")
            write_startup_log(f"{label} konnte nicht geöffnet werden: " + repr(exc))

    def _setup_style(self, scale: float = 1.0):
        def size(value: int, minimum: int = 6) -> int:
            return max(minimum, int(round(value * scale)))

        def padding(horizontal: int, vertical: int) -> tuple[int, int]:
            return (size(horizontal, 4), size(vertical, 3))

        style = ttk.Style(self)
        if not getattr(self, "_style_initialized", False):
            try:
                style.theme_use("clam")
            except Exception:
                pass
            self._style_initialized = True
        # Tk's option database also controls the classic widgets and the
        # otherwise native-looking Combobox drop-down list.  Without these
        # defaults Windows can render a white list or selection with light
        # text while the rest of the application is dark.
        for pattern, value in (
            ("*Listbox.background", theme.INPUT_BG), ("*Listbox.foreground", theme.TEXT),
            ("*Listbox.selectBackground", theme.ACTIVE_BG), ("*Listbox.selectForeground", theme.TEXT),
            ("*Listbox.highlightBackground", theme.BORDER), ("*Listbox.highlightColor", theme.ACCENT),
            ("*Text.background", theme.INPUT_BG), ("*Text.foreground", theme.TEXT),
            ("*Text.insertBackground", theme.TEXT), ("*Text.selectBackground", theme.ACTIVE_BG),
            ("*Text.selectForeground", theme.TEXT),
            ("*TCombobox*Listbox.background", theme.INPUT_BG),
            ("*TCombobox*Listbox.foreground", theme.TEXT),
            ("*TCombobox*Listbox.selectBackground", theme.ACTIVE_BG),
            ("*TCombobox*Listbox.selectForeground", theme.TEXT),
        ):
            self.option_add(pattern, value)
        style.configure("TFrame", background=theme.BG)
        style.configure("Card.TFrame", background=theme.CARD, relief="flat")
        style.configure("TLabel", background=theme.BG, foreground=theme.TEXT, font=("Segoe UI", size(10)))
        style.configure("Card.TLabel", background=theme.CARD, foreground=theme.TEXT, font=("Segoe UI", size(10)))
        style.configure("Muted.Card.TLabel", background=theme.CARD, foreground=theme.MUTED, font=("Segoe UI", size(9)))
        style.configure("Title.TLabel", background=theme.BG, foreground=theme.TEXT, font=("Segoe UI Semibold", size(20)))
        style.configure("CardTitle.TLabel", background=theme.CARD, foreground=theme.TEXT, font=("Segoe UI Semibold", size(12)))
        style.configure(
            "Call.TEntry", font=("Segoe UI Semibold", size(18)), padding=size(8, 4),
            fieldbackground=theme.INPUT_BG, foreground=theme.TEXT, insertcolor=theme.TEXT,
            bordercolor=theme.BORDER, lightcolor=theme.BORDER, darkcolor=theme.BORDER,
        )
        style.configure(
            "Worked.Call.TEntry", font=("Segoe UI Semibold", size(18)), padding=size(8, 4),
            fieldbackground=theme.OK_BADGE_BG, foreground=theme.OK,
        )
        style.map(
            "Worked.Call.TEntry",
            fieldbackground=[("readonly", theme.OK_BADGE_BG), ("disabled", theme.OK_BADGE_BG), ("focus", theme.OK_BADGE_BG)],
            foreground=[("readonly", theme.OK), ("disabled", theme.OK), ("focus", theme.OK)],
        )
        style.configure(
            "TEntry", padding=size(6, 3), fieldbackground=theme.INPUT_BG, foreground=theme.TEXT,
            insertcolor=theme.TEXT, bordercolor=theme.BORDER, lightcolor=theme.BORDER, darkcolor=theme.BORDER,
        )
        style.map(
            "TEntry",
            fieldbackground=[("disabled", theme.SURFACE), ("readonly", theme.INPUT_BG), ("focus", theme.INPUT_BG)],
            foreground=[("disabled", theme.MUTED), ("readonly", theme.TEXT)],
            bordercolor=[("focus", theme.ACCENT), ("!focus", theme.BORDER)],
        )
        style.configure(
            "TCombobox", padding=size(5, 3), fieldbackground=theme.INPUT_BG,
            background=theme.INPUT_BG, foreground=theme.TEXT, arrowcolor=theme.TEXT,
            bordercolor=theme.BORDER, lightcolor=theme.BORDER, darkcolor=theme.BORDER,
            selectbackground=theme.INPUT_BG, selectforeground=theme.TEXT,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("disabled", theme.SURFACE), ("readonly", theme.INPUT_BG), ("focus", theme.INPUT_BG)],
            background=[("disabled", theme.SURFACE), ("active", theme.ACTIVE_BG), ("readonly", theme.INPUT_BG)],
            foreground=[("disabled", theme.MUTED), ("readonly", theme.TEXT)],
            arrowcolor=[("disabled", theme.MUTED), ("readonly", theme.TEXT)],
            selectbackground=[("readonly", theme.INPUT_BG)],
            selectforeground=[("readonly", theme.TEXT)],
            bordercolor=[("focus", theme.ACCENT), ("!focus", theme.BORDER)],
        )
        style.configure("Primary.TButton", background=theme.ACCENT, foreground="white", padding=padding(14, 8), borderwidth=0, font=("Segoe UI Semibold", size(10)))
        style.map(
            "Primary.TButton",
            background=[("active", theme.ACCENT_DARK), ("disabled", theme.DISABLED)],
            foreground=[("disabled", theme.MUTED), ("!disabled", "white")],
        )
        style.configure("Secondary.TButton", padding=padding(12, 7), font=("Segoe UI", size(10)), background=theme.CARD, foreground=theme.TEXT)
        style.map(
            "Secondary.TButton",
            background=[("disabled", theme.SURFACE), ("active", theme.NAV_HOVER)],
            foreground=[("disabled", theme.MUTED), ("!disabled", theme.TEXT)],
        )
        style.configure("Tuning.TButton", padding=padding(12, 7), font=("Segoe UI Semibold", size(10)), background=theme.ERR, foreground="white")
        style.map("Tuning.TButton", background=[("disabled", theme.ERR), ("active", theme.ERR)], foreground=[("disabled", "white")])
        style.configure("Nav.TButton", background=theme.SIDEBAR, foreground=theme.SIDEBAR_TEXT, padding=padding(12, 9), anchor="w", borderwidth=0, font=("Segoe UI", size(9)))
        style.map("Nav.TButton", background=[("active", theme.NAV_HOVER)], foreground=[("active", theme.ACCENT)])
        style.configure("NavActive.TButton", background=theme.ACTIVE_BG, foreground=theme.ACCENT, padding=padding(12, 9), anchor="w", borderwidth=0, font=("Segoe UI Semibold", size(9)))
        style.map("NavActive.TButton", background=[("active", theme.NAV_ACTIVE_HOVER)], foreground=[("active", theme.ACCENT_DARK)])
        style.configure("Treeview", rowheight=size(30, 20), font=("Segoe UI", size(9)), background=theme.INPUT_BG, fieldbackground=theme.INPUT_BG, foreground=theme.TEXT, bordercolor=theme.BORDER)
        style.map("Treeview", background=[("selected", theme.ACTIVE_BG)], foreground=[("selected", theme.TEXT)])
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", size(9)), padding=size(5, 3), background=theme.CARD, foreground=theme.TEXT)
        style.map("Treeview.Heading", background=[("active", theme.NAV_HOVER)], foreground=[("active", theme.TEXT)])
        style.configure("Stats.Horizontal.TProgressbar", troughcolor=theme.PROGRESS_BG, background=theme.ACCENT, borderwidth=0, thickness=size(10, 6))
        style.configure("TLabelframe", background=theme.CARD, bordercolor=theme.BORDER, relief="solid")
        style.configure("TLabelframe.Label", background=theme.CARD, foreground=theme.TEXT, font=("Segoe UI Semibold", size(10)))
        style.configure("TRadiobutton", background=theme.CARD, foreground=theme.TEXT)
        style.map("TRadiobutton", background=[("active", theme.CARD), ("disabled", theme.CARD)], foreground=[("disabled", theme.MUTED)])
        style.configure("TCheckbutton", background=theme.CARD, foreground=theme.TEXT)
        style.map("TCheckbutton", background=[("active", theme.CARD), ("disabled", theme.CARD)], foreground=[("disabled", theme.MUTED)])
        style.configure("TNotebook", background=theme.BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=padding(16, 9), font=("Segoe UI", size(10)), background=theme.SURFACE, foreground=theme.TEXT)
        style.map("TNotebook.Tab", foreground=[("selected", theme.ACCENT), ("!selected", theme.TEXT)], background=[("selected", theme.CARD), ("active", theme.NAV_HOVER), ("!selected", theme.SURFACE)])
        style.configure("Settings.TNotebook", background=theme.BG, borderwidth=0)
        style.configure("Settings.TNotebook.Tab", padding=padding(10, 6), font=("Segoe UI", size(9)), background=theme.SURFACE, foreground=theme.TEXT)
        style.map(
            "Settings.TNotebook.Tab",
            foreground=[("selected", theme.ACCENT), ("!selected", theme.TEXT)],
            background=[("selected", theme.ACTIVE_BG), ("active", theme.NAV_HOVER), ("!selected", theme.SURFACE)],
        )

    def _load_brand_logo(self):
        if Image is None or ImageTk is None:
            return None
        try:
            resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            path = resource_root / "assets" / "da6it-logo.webp"
            self._brand_logo_source = Image.open(path).convert("RGB")
            image = self._brand_logo_source.copy()
            image.thumbnail((170, 70), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
        except Exception as exc:
            write_startup_log("Logo konnte nicht geladen werden: " + repr(exc))
            return None

    def _load_window_icon(self):
        """Use the square DA6IT brand mark for the window and taskbar."""
        try:
            resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            self.app_icon_photo = tk.PhotoImage(file=str(resource_root / "assets" / "da6it-icon.png"))
            self.iconphoto(True, self.app_icon_photo)
        except Exception as exc:
            write_startup_log("App-Icon konnte nicht geladen werden: " + repr(exc))

    def _build_shell(self):
        self._load_window_icon()
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=theme.SIDEBAR, width=205, highlightbackground=theme.BORDER, highlightthickness=1)
        side = self.sidebar
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        self.brand_logo_photo = self._load_brand_logo()
        if self.brand_logo_photo is not None:
            brand = tk.Label(side, image=self.brand_logo_photo, bg="#ffffff", cursor="hand2", padx=2, pady=2)
        else:
            brand = tk.Label(
                side, text="DA6IT.de", bg=theme.SIDEBAR, fg=theme.ACCENT,
                font=("Segoe UI Semibold", 19), cursor="hand2",
            )
        self.brand_label = brand
        brand.pack(anchor="w", padx=16, pady=(16, 0))
        brand.bind("<Button-1>", self._open_da6it_website)
        tk.Label(side, text="Wavelog Offline Logger", bg=theme.SIDEBAR, fg=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 17))
        self.nav_buttons: dict[str, ttk.Button] = {}
        nav_items = (
            ("log", "▣   Logbuch"),
            ("fast_log", "ϟ   Fast Log / DXpedition"),
            ("contest", "#   Contest Logging"),
            ("xota", "⌖   xOTA"),
            ("qsos", "☁   Logbuch & Sync"),
            ("stats", "▤   Statistiken"),
            ("dx_cluster", "◎   DX Cluster"),
            ("cat", "⌁   CAT Setup"),
            ("udp_log", "◉   UDP Logging"),
            ("settings", "⚙   Einstellungen"),
        )
        for page_name, label in nav_items:
            if "   " in label:
                icon, label_text = label.split("   ", 1)
                label = icon + "   " + self._tr(label_text)
            button = ttk.Button(side, text=label, style="Nav.TButton", command=lambda target=page_name: self._show_page(target))
            button.pack(fill="x", padx=8, pady=1)
            self.nav_buttons[page_name] = button

        local_card = tk.Frame(side, bg=theme.SURFACE, highlightbackground=theme.BORDER, highlightthickness=1)
        local_card.pack(side="bottom", fill="x", padx=14, pady=(8, 14))
        self.sidebar_mode_label = tk.Label(local_card, text="●  LOCAL ONLY", bg=theme.SURFACE, fg=theme.ACCENT, font=("Segoe UI Semibold", 9))
        self.sidebar_mode_label.pack(anchor="w", padx=12, pady=(10, 3))
        self.sidebar_mode_hint = tk.Label(local_card, text="Wavelog-Status wird geprüft.", bg=theme.SURFACE, fg=theme.MUTED, font=("Segoe UI", 8), justify="left")
        self.sidebar_mode_hint.pack(anchor="w", padx=12, pady=(0, 10))
        tk.Label(side, text=f"Version {VERSION}", bg=theme.SIDEBAR, fg=theme.MUTED, font=("Segoe UI", 8)).pack(side="bottom", anchor="w", padx=20, pady=(8, 0))

        self.main = ttk.Frame(self, padding=(22, 16))
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        header = ttk.Frame(self.main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        title_block = ttk.Frame(header)
        title_block.grid(row=0, column=0, sticky="w")
        self.page_title = ttk.Label(title_block, text="QSO loggen", style="Title.TLabel")
        self.page_title.pack(anchor="w")
        self.page_subtitle = ttk.Label(title_block, text="Schnell, lokal und unabhängig von einer Internetverbindung.", foreground=theme.MUTED)
        self.page_subtitle.pack(anchor="w", pady=(2, 0))

        profile_card = tk.Frame(header, bg=theme.CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        profile_card.grid(row=0, column=1, sticky="e", padx=(10, 10))
        tk.Label(profile_card, text="PROFIL", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(10, 6))
        self.active_profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(profile_card, textvariable=self.active_profile_var, state="readonly", width=22)
        self.profile_combo.pack(side="left", pady=5)
        self.profile_combo.bind("<<ComboboxSelected>>", self._profile_combo_changed)
        ttk.Button(profile_card, text="Verwalten", style="Secondary.TButton", command=self.manage_profiles).pack(side="left", padx=(6, 6), pady=4)
        self._refresh_profile_selector()

        self.clock_card = tk.Frame(header, bg=theme.CARD, width=178, height=52, highlightbackground=theme.BORDER, highlightthickness=1)
        self.clock_card.grid(row=0, column=2, sticky="e")
        self.clock_card.pack_propagate(False)
        self.clock_label = tk.Label(self.clock_card, text="--:--:--", width=8, anchor="center", bg=theme.CARD, fg=theme.TEXT, font=("Consolas", 18, "bold"), padx=8, pady=5)
        self.clock_label.pack(side="left")
        self.clock_zone_label = tk.Label(self.clock_card, text="UTC", width=5, anchor="center", bg=theme.CARD, fg=theme.MUTED, font=("Segoe UI Semibold", 9), padx=0, pady=5)
        self.clock_zone_label.pack(side="left", padx=(0, 12))

        self.page_container = ttk.Frame(self.main)
        self.page_container.grid(row=1, column=0, sticky="nsew")
        self.page_container.columnconfigure(0, weight=1)
        self.page_container.rowconfigure(0, weight=1)
        self.pages: dict[str, ttk.Frame] = {}

        footer = tk.Frame(self.main, bg=theme.BG, highlightbackground=theme.BORDER, highlightthickness=0)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.footer_mode_label = tk.Label(footer, text="●  LOCAL ONLY", bg=theme.BG, fg=theme.ACCENT, font=("Segoe UI Semibold", 9), anchor="w")
        self.footer_mode_label.pack(side="left")
        self.status_var = tk.StringVar(value="Bereit")
        tk.Label(footer, textvariable=self.status_var, bg=theme.BG, fg=theme.MUTED, font=("Segoe UI", 9), anchor="w").pack(side="left", padx=(14, 0))
        self.footer_qso_var = tk.StringVar(value="0 QSOs")
        self.footer_db_var = tk.StringVar(value="")
        support = tk.Frame(footer, bg=theme.BG)
        support.pack(side="right", padx=(18, 0))
        for text, url in (
            ("☕ Buy Me a Coffee", "https://buymeacoffee.com/da6it?new=1"),
            ("PayPal", "https://paypal.me/DA6IT"),
        ):
            link = tk.Label(
                support, text=self._tr(text), bg=theme.BG, fg=theme.MUTED,
                font=("Segoe UI", 8), cursor="hand2", padx=4,
            )
            link.pack(side="left")
            link.bind("<Button-1>", lambda _event, target=url, name=text: self._open_external_url(target, name))
            link.bind("<Enter>", lambda _event, widget=link: widget.configure(fg=theme.ACCENT))
            link.bind("<Leave>", lambda _event, widget=link: widget.configure(fg=theme.MUTED))
        tk.Label(footer, textvariable=self.footer_qso_var, bg=theme.BG, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="right", padx=(18, 0))
        tk.Label(footer, textvariable=self.footer_db_var, bg=theme.BG, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="right")

    def _new_page(self, name: str) -> ttk.Frame:
        f = ttk.Frame(self.page_container)
        f.grid(row=0, column=0, sticky="nsew")
        self.pages[name] = f
        return f

    def _show_page(self, name: str):
        titles = {"log": "QSO loggen", "fast_log": "Fast Log / DXpedition", "contest": "Contest Logging", "xota": "xOTA", "qsos": "Logbuch & Sync", "stats": "Statistiken", "cat": "CAT Setup", "dx_cluster": "DX Cluster", "udp_log": "UDP Logging", "settings": "Einstellungen"}
        subtitles = {
            "log": "Neues QSO erfassen und sicher lokal speichern.",
            "fast_log": "Pileups zügig abarbeiten: Rufzeichen und Enter.",
            "contest": "Seriennummern und Austauschdaten effizient protokollieren.",
            "xota": "Portable Aktivierungen offline vorbereiten, kombinieren und sicher protokollieren.",
            "qsos": "Lokale QSOs prüfen und Wavelog bewusst manuell synchronisieren.",
            "stats": "Das lokale Logbuch auf einen Blick.",
            "cat": "Funkgerät über das eingebettete Hamlib steuern.",
            "dx_cluster": "Live-Spots empfangen, filtern und an den TRX übergeben.",
            "udp_log": "QSOs von WSJT-X und kompatiblen Programmen empfangen.",
            "settings": "Stationsprofil, Online-Dienste und lokale Daten verwalten.",
        }
        self.page_title.configure(text=self._tr(titles[name]))
        self.page_subtitle.configure(text=self._tr(subtitles.get(name, "")))
        for page_name, button in self.nav_buttons.items():
            button.configure(style="NavActive.TButton" if page_name == name else "Nav.TButton")
        self.pages[name].tkraise()
        self.current_page = name
        if name == "fast_log":
            self.refresh_fast_log_page()
            self.fast_log_call_entry.focus_set()
        elif name == "contest":
            if not self._contest_session().get("running"):
                if self.language == "en":
                    reminder = (
                        "Please note: Every contest must be configured before it is started.\n\n"
                        "Select or create a contest preset and check its settings before starting the session."
                    )
                else:
                    reminder = (
                        "Bitte beachte: Jeder Contest muss vor dem Start passend eingestellt werden.\n\n"
                        "Wähle oder erstelle ein Contest-Preset und prüfe die Einstellungen, bevor du die Session startest."
                    )
                messagebox.showinfo("Contest Logging", reminder, parent=self)
            self.refresh_contest_page()
        elif name == "xota":
            self.refresh_xota_page()
        elif name == "qsos":
            # Showing the page must be instant. Reuse the cached rows if they
            # are current; otherwise the refresh runs asynchronously.
            self.refresh_qsos(force=False, immediate=True)
        elif name == "stats":
            self.refresh_stats()
        elif name == "cat":
            self._refresh_cat_ports()

    def _card(self, parent, **grid):
        outer = tk.Frame(parent, bg=theme.CARD, highlightbackground=theme.BORDER, highlightthickness=1)
        outer.grid(**grid)
        inner = ttk.Frame(outer, style="Card.TFrame", padding=16)
        inner.pack(fill="both", expand=True)
        self._responsive_card_frames.append(inner)
        return inner
