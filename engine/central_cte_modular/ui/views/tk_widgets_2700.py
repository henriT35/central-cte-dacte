# -*- coding: utf-8 -*-
"""Widgets Tk compartilhados da vista modular 2.7.0.

O código visual foi separado da camada histórica e é composto somente quando
a aplicação é criada. As dependências são fornecidas pela fábrica de vistas.
"""
def _fit_photo_asset(name, max_width=26, max_height=26):
    """Reduz ativos externos grandes antes de colocá-los em caixas compactas."""
    image = photo_asset(name)
    try:
        width = max(int(image.width() or 1), 1)
        height = max(int(image.height() or 1), 1)
        factor = max(
            1,
            (width + int(max_width) - 1) // int(max_width),
            (height + int(max_height) - 1) // int(max_height),
        )
        return image.subsample(factor, factor) if factor > 1 else image
    except Exception:
        return image


class ImageButton(tk.Frame):
    def __init__(self, parent, icon_name, text, command, danger=False, width=156, height=46):
        super().__init__(
            parent,
            bg="#ffffff",
            highlightbackground="#d5e4f5",
            highlightcolor="#77a9ea",
            highlightthickness=1,
            width=width,
            height=height,
            cursor="hand2"
        )
        self.command = command
        self.enabled = True
        self.normal_border = "#d5e4f5"
        self.hover_border = "#5898e6"
        self.danger = danger
        self.pack_propagate(False)

        self.icon_img = _fit_photo_asset(icon_name, 26, 26)
        fg = RED if danger else BLUE_DARK

        icon_wrap = tk.Frame(self, bg="#ffffff", width=34, height=34)
        icon_wrap.pack(side="left", padx=(10, 7), pady=6)
        icon_wrap.pack_propagate(False)
        icon_lbl = tk.Label(icon_wrap, image=self.icon_img, bg="#ffffff", bd=0)
        icon_lbl.pack(expand=True)

        text_lbl = tk.Label(
            self,
            text=text,
            bg="#ffffff",
            fg=fg,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            justify="left",
            wraplength=max(width - 55, 60)
        )
        text_lbl.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.widgets = [self, icon_wrap, icon_lbl, text_lbl]
        for w in self.widgets:
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _click(self, _=None):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled=True, tooltip=""):
        self.enabled = bool(enabled)
        fg = (RED if self.danger else BLUE_DARK) if self.enabled else "#9aa8b8"
        bg = "#ffffff" if self.enabled else "#f2f5f8"
        self.configure(cursor="hand2" if self.enabled else "arrow", bg=bg, highlightbackground=self.normal_border)
        for widget in self.widgets[1:]:
            try:
                widget.configure(bg=bg)
            except Exception:
                pass
        try:
            self.widgets[-1].configure(fg=fg)
        except Exception:
            pass
        if tooltip:
            self._disabled_tooltip = tooltip
        return self

    def _enter(self, _=None):
        if not self.enabled:
            return
        self.configure(highlightbackground=self.hover_border, bg="#f7fbff")
        for w in self.widgets[1:]:
            w.configure(bg="#f7fbff")

    def _leave(self, _=None):
        if not self.enabled:
            return
        self.configure(highlightbackground=self.normal_border, bg="#ffffff")
        for w in self.widgets[1:]:
            w.configure(bg="#ffffff")


class StatCard(tk.Frame):
    def __init__(self, parent, icon_name, value, title, subtitle, color=BLUE):
        super().__init__(parent, bg="#ffffff", highlightbackground="#c9d9ec", highlightthickness=1, height=98)
        self.pack_propagate(False)
        self.color = color

        self.icon_img = _fit_photo_asset(icon_name, 28, 28)
        icon_bg = tk.Frame(self, bg="#eaf4ff", width=48, height=48)
        icon_bg.pack(side="left", padx=(12, 10), pady=18)
        icon_bg.pack_propagate(False)

        icon_lbl = tk.Label(icon_bg, image=self.icon_img, bg="#eaf4ff")
        icon_lbl.pack(expand=True)

        text_box = tk.Frame(self, bg="#ffffff")
        text_box.pack(side="left", fill="both", expand=True, pady=(10, 8))

        self.value_lbl = tk.Label(text_box, text=value, bg="#ffffff", fg=color, font=("Segoe UI", 15, "bold"), anchor="w")
        self.value_lbl.pack(anchor="w")

        self.title_lbl = tk.Label(text_box, text=title, bg="#ffffff", fg="#143a75", font=("Segoe UI", 10), anchor="w")
        self.title_lbl.pack(anchor="w", pady=(0, 0))

        self.subtitle_lbl = tk.Label(text_box, text=subtitle, bg="#ffffff", fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.subtitle_lbl.pack(anchor="w", pady=(2, 0))

    def set_values(self, value, subtitle=None):
        self.value_lbl.config(text=value)
        if subtitle is not None:
            self.subtitle_lbl.config(text=subtitle)
